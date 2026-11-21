"""Rellena los campos nulos de JSON ya generados con los datos del catálogo.

python rellenar.py <archivo.json | carpeta> [--catalogo catalogo_productos.csv] [--dry-run]

Acepta un registro suelto, una lista de registros (resultados.json) o una exportación de la ventana ({"capturas": [...]}).
Busca el producto por id_product, código de barras o, si no hay, nombre y contenido (solo coincidencias claras).
Solo rellena lo que está en null o vacío; nunca pisa un valor. Con --dry-run solo cuenta, sin escribir.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from engine import auto, catalogo


def registros(dato):
    """Los registros de captura que contiene un JSON cargado (para rellenarlos en su sitio)."""
    if isinstance(dato, list):
        return [r for r in dato if isinstance(r, dict) and "capture_id" in r]
    if isinstance(dato, dict) and isinstance(dato.get("capturas"), list):
        return registros(dato["capturas"])
    return [dato] if isinstance(dato, dict) and "capture_id" in dato else []


def procesar(ruta, catalog, dry_run=False):
    """-> {'archivos': n, 'registros': n, 'rellenados': n, 'campos': Counter, 'metodos': Counter, 'sin_match': n}"""
    ruta = Path(ruta)
    archivos = [ruta] if ruta.is_file() else sorted(ruta.rglob("*.json"))
    res = {"archivos": 0, "registros": 0, "rellenados": 0, "campos": Counter(), "metodos": Counter(), "sin_match": 0}
    for f in archivos:
        try:
            dato = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue  # no es JSON legible: se ignora
        regs = registros(dato)
        if not regs:
            continue
        res["archivos"] += 1
        cambio = False
        for r in regs:
            res["registros"] += 1
            _, llenados = catalogo.rellenar(r, catalog)
            if llenados:
                cambio = True
                res["rellenados"] += 1
                res["campos"].update(llenados)
                res["metodos"][r["fuente_catalogo"]] += 1
            elif any(r.get(k) in (None, "") for k in catalogo.CAMPOS):
                res["sin_match"] += 1
        if cambio and not dry_run:
            f.write_text(json.dumps(dato, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ruta", type=Path, help="archivo .json o carpeta con JSON")
    ap.add_argument("--catalogo", type=Path, default=catalogo.ruta_catalogo())
    ap.add_argument("--dry-run", action="store_true", help="solo contar lo que se rellenaría")
    a = ap.parse_args()
    catalog = auto.load_catalog(a.catalogo)
    if not catalog:
        raise SystemExit(f"No se pudo leer el catálogo: {a.catalogo}")
    r = procesar(a.ruta, catalog, a.dry_run)
    print(f"Catálogo: {a.catalogo} ({len(catalog)} productos)")
    print(f"{'Se rellenarían' if a.dry_run else 'Rellenados'} {r['rellenados']} de {r['registros']} registros en {r['archivos']} archivos"
          f" · sin coincidencia clara: {r['sin_match']}")
    if r["rellenados"]:
        print("  por método:", dict(r["metodos"]))
        print("  campos:", dict(r["campos"]))


if __name__ == "__main__":
    main()
