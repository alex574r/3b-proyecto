"""Analiza una carpeta de fotos con el mismo motor de /analizar (solo fotos, sin datos esperados).

Una captura son 3 fotos con el patrón de Validat3B_desarrollo_imagenes/imagenes:
<ID>_facade.jpg, <ID>_product.jpg, <ID>_shelf.jpg (también .jpeg/.png). Se busca en subcarpetas.
Guarda un JSON por captura (<salida>/<ID>.json, el mismo registro que devuelve la API) y el consolidado resultados.json.
"""
import json
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import auto, output, vision
from .local_checks import analyze

FOTO_RE = re.compile(r"^(?P<id>.+)_(?P<kind>facade|product|shelf)\.(?:jpe?g|png)$", re.IGNORECASE)
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
KINDS = ("facade", "product", "shelf")


def buscar_capturas(carpeta):
    """-> ({capture_id: {facade, product, shelf: Path}}, [avisos]). Solo grupos completos y con id válido."""
    grupos = {}
    for f in sorted(Path(carpeta).rglob("*")):
        m = f.is_file() and FOTO_RE.match(f.name)
        if m:
            grupos.setdefault(m["id"], {}).setdefault(m["kind"].lower(), f)
    capturas, avisos = {}, []
    for cid, fotos in grupos.items():
        if not ID_RE.match(cid):
            avisos.append(f"{cid}: id inválido (solo letras, números, - y _; máx. 64)")
        elif set(fotos) != set(KINDS):
            avisos.append(f"{cid}: faltan fotos ({', '.join(sorted(set(KINDS) - set(fotos)))})")
        else:
            capturas[cid] = fotos
    return capturas, avisos


def analizar_captura(cid, paths, carpeta, salida, client, catalog, reutilizar=True):
    """Analiza una captura y guarda su JSON en `salida`. Nunca lanza: ante error devuelve revision_manual / ERROR_PROCESAMIENTO."""
    out = Path(salida) / f"{cid}.json"
    if reutilizar and out.exists():
        try:
            return json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # archivo dañado: se vuelve a analizar
    cap = {"capture_id": cid}
    try:
        local = analyze(paths)
        vis = None if client is None else vision.extract(cap, paths, client, Path(salida) / "usage.jsonl", auto=True)
        res, datos = auto.completar(cap, local, vis, catalog)
        errs = output.validate(res)
        if errs:
            raise ValueError(f"salida inválida: {errs}")
    except Exception as e:  # noqa: BLE001
        res = output.fallback(cid, f"{type(e).__name__}: {e}")
        datos = auto.detectar(cap, [], None, catalog)
    fotos = {k: (Path(paths[k]).relative_to(carpeta).as_posix(), None) for k in KINDS}  # sin URL: son archivos locales
    registro = auto.registro(datos, res, fotos)
    out.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    return registro


def exportar(registros, destino, carpeta, usa_llm):
    """Un solo JSON con toda la información del análisis: datos de la corrida, resumen por decisión y motivo, y el
    registro completo de cada captura (el mismo que devuelve la API). -> el dict escrito en `destino`."""
    registros = sorted(registros, key=lambda r: r["capture_id"])
    datos = {
        "carpeta": str(carpeta),
        "generado": time.strftime("%Y-%m-%d %H:%M:%S"),
        "usa_haiku": bool(usa_llm),
        "total": len(registros),
        "resumen": {
            "por_decision": dict(Counter(r["decision_esperada"] for r in registros)),
            "por_motivo": dict(Counter(r["motivo_rechazo"] or r["reason_code"] for r in registros if r["decision_esperada"] != "aprobada")),
            "por_tienda": dict(Counter(r["capture_store_name"] or "(sin dato)" for r in registros)),
        },
        "capturas": registros,
    }
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return datos


def analizar_carpeta(carpeta, salida, client, catalog, workers=2, reutilizar=True, on_result=None, stop=None):
    """Analiza todas las capturas de la carpeta. on_result(registro, hechas, total) se llama desde hilos de trabajo.
    stop: threading.Event; al activarse no se empiezan capturas nuevas. -> lista de registros (los analizados)."""
    carpeta, salida = Path(carpeta), Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    capturas, _ = buscar_capturas(carpeta)
    total, hechas, lock = len(capturas), [0], threading.Lock()

    def uno(item):
        cid, paths = item
        if stop is not None and stop.is_set():
            return None
        r = analizar_captura(cid, paths, carpeta, salida, client, catalog, reutilizar)
        with lock:
            hechas[0] += 1
            n = hechas[0]
        if on_result:
            on_result(r, n, total)
        return r

    with ThreadPoolExecutor(max(1, workers)) as ex:
        registros = [r for r in ex.map(uno, sorted(capturas.items())) if r is not None]
    (salida / "resultados.json").write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    return registros
