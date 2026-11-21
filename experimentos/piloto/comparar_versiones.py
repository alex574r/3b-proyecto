"""Antes (selector v1, congelado) y después (selector v2) sobre las mismas capturas y la misma configuración.

Uso (Windows):  python comparar_versiones.py
  - Desarrollo: las 21 capturas de muestra_dev.json.
  - Reserva: 10 capturas que no están en desarrollo, elegidas por orden de sha1("reserva-v2|" + capture_id).
    Al crear muestra_reserva.json se guarda la huella sha256 del selector v2; si el selector cambia después,
    el informe lo advierte (la prueba de reserva dejaría de ser válida).
  - Ambas en lote (archivo original) y Android (simulación de ValidatApi.jpeg: 1280 px, JPEG 85).
Salida local (contiene fotos, no publicar): salida/antes_despues/
  antes_despues.html · antes_despues.png · tabla_antes_despues.csv · resumen_antes_despues.md · img/
La calidad de cada recorte proviene de revision_visual.csv (inspección visual del desarrollador). Ninguna
cifra de este informe es una lectura confirmada por el modelo: la lectura queda "sin medir" sin Foundry.
"""
import csv
import hashlib
import html
import importlib.util
import json
import sys
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import piloto_etiquetas as v2  # noqa: E402

_spec = importlib.util.spec_from_file_location("piloto_v1", AQUI / "linea_base" / "piloto_etiquetas_v1.py")
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

DATOS = Path(os.environ.get("VALIDAT3B_DATOS", AQUI.parent.parent))
SALIDA = AQUI / "salida" / "antes_despues"
REVISION = AQUI / "revision_visual.csv"
RESERVA = AQUI / "muestra_reserva.json"
N_RESERVA = 10
FOCO = [("CAP-563575", "android"), ("CAP-410562", "lote"), ("CAP-635322", "lote"), ("CAP-393881", "lote"),
        ("CAP-393881", "android"), ("CAP-520473", "lote"), ("CAP-520473", "android"), ("CAP-899554", "lote"),
        ("CAP-899554", "android")]
DEFECTOS = {"importe_cortado", "region_equivocada", "otra_etiqueta", "sin_descripcion", "texto_cortado"}
CATEGORIA = {
    ("recorte_defectuoso", "recorte_util"): "corregida_con_recorte",
    ("recorte_defectuoso", "foto_completa"): "vuelta_a_foto_completa",
    ("recorte_defectuoso", "recorte_defectuoso"): "sigue_defectuosa",
    ("recorte_util", "recorte_util"): "recorte_util_conservado",
    ("recorte_util", "foto_completa"): "recorte_util_perdido",
    ("recorte_util", "recorte_defectuoso"): "deterioro",
    ("foto_completa", "recorte_util"): "recorte_util_nuevo",
    ("foto_completa", "recorte_defectuoso"): "recorte_defectuoso_nuevo",
    ("foto_completa", "foto_completa"): "sin_cambio_foto_completa",
}


def huella_selector():
    """sha256 de la sección del detector/selector de v2 (lo que no debe cambiar durante la reserva)."""
    t = (AQUI / "piloto_etiquetas.py").read_text(encoding="utf-8")
    a = t.index("# ----------------------------------------------------------------------------- detector de etiquetas")
    b = t.index("# ----------------------------------------------------------------------------- muestra")
    return hashlib.sha256(t[a:b].encode("utf-8")).hexdigest()


def muestra_reserva(caps, dev_ids):
    if RESERVA.exists():
        return json.loads(RESERVA.read_text(encoding="utf-8"))
    libres = sorted((c for c in caps if c not in dev_ids), key=lambda c: hashlib.sha1(f"reserva-v2|{c}".encode()).hexdigest())
    m = {"criterio": (f"Primeras {N_RESERVA} capturas fuera de muestra_dev.json en orden de sha1('reserva-v2|' + "
                      "capture_id). Se abre una sola vez, con el selector v2 ya fijado; no se ajustan parámetros "
                      "después de verla."),
         "sha256_selector_v2_al_abrir": huella_selector(), "ids": libres[:N_RESERVA]}
    RESERVA.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


def decidir(mod, src):
    reg = mod.region_recorte(mod.detectar_etiquetas(src), src.size)
    sen = mod.senales_recorte(src.crop(reg["box"])) if reg else None
    var, motivo = mod.selector(reg, sen)
    return {"var": var, "motivo": motivo, "box": reg["box"] if reg and var != "A" else None,
            "verif": reg["etiqueta"].get("verificaciones", "") if reg else ""}


def vista(mod, src, d):
    if d["var"] == "A":
        data, size = mod.preparar_backend(src)
    else:
        crop = src.crop(d["box"])
        data, size, _ = mod.preparar_recorte(mod.clahe_L(crop) if d["var"] == "C" else crop)
    return data, size


def cargar_revision():
    rev = {}
    if REVISION.exists():
        with open(REVISION, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rev[(r["muestra"], r["capture_id"], r["origen"], r["version"])] = r
    return rev


def calidad(d, juicio):
    if d["var"] == "A":
        return "foto_completa"
    if not juicio:
        return "sin_revisar"
    # "correcto_texto_cortado": importe completo y descripción identificable, pero corta texto en los bordes.
    return "recorte_util" if juicio in ("correcto", "correcto_texto_cortado") else "recorte_defectuoso"


def miniatura(data_o_img, lado):
    im = Image.open(__import__("io").BytesIO(data_o_img)).convert("RGB") if isinstance(data_o_img, bytes) else data_o_img
    im = im.copy(); im.thumbnail((lado, lado))
    return im


def main():
    (SALIDA / "img").mkdir(parents=True, exist_ok=True)
    caps = {c["capture_id"]: c for c in json.loads((DATOS / "capturas.json").read_text(encoding="utf-8-sig"))}
    dev = list(json.loads((AQUI / "muestra_dev.json").read_text(encoding="utf-8"))["ids"])
    res = muestra_reserva(caps, set(dev))
    huella = huella_selector()
    rev = cargar_revision()
    filas = []
    for muestra, ids in (("desarrollo", dev), ("reserva", res["ids"])):
        for cid in ids:
            orig = v2.cargar_rgb(DATOS / caps[cid]["shelf_file"])
            for origen in v2.ORIGENES:
                src = orig if origen == "lote" else v2.simular_android(orig)
                k = src.size[0] / orig.size[0]
                d1, d2 = decidir(v1, src), decidir(v2, src)
                j1 = rev.get((muestra, cid, origen, "v1"), {})
                j2 = rev.get((muestra, cid, origen, "v2"), {})
                q1, q2 = calidad(d1, j1.get("juicio")), calidad(d2, j2.get("juicio"))
                cat = CATEGORIA.get((q1, q2), "pendiente_de_revision")
                base = f"{muestra}_{cid}_{origen}"
                full = src.copy(); dr = ImageDraw.Draw(full); lw = max(2, src.size[0] // 160)
                if d1["box"]:
                    dr.rectangle(d1["box"], outline=(220, 30, 30), width=lw)
                if d2["box"]:
                    dr.rectangle(d2["box"], outline=(0, 170, 0), width=lw)
                miniatura(full, 520).save(SALIDA / "img" / f"{base}_foto.jpg", quality=85)
                tokens = {}
                for nombre, mod, d in (("v1", v1, d1), ("v2", v2, d2)):
                    data, size = vista(mod, src, d)
                    tokens[nombre] = v2.tokens_imagen_est(size)
                    miniatura(data, 520).save(SALIDA / "img" / f"{base}_{nombre}.jpg", quality=85)
                caja = lambda b: " ".join(str(round(t / k)) for t in b) if b else "foto completa"
                filas.append({
                    "muestra": muestra, "capture_id": cid, "origen": origen,
                    "v1_vista": d1["var"], "v1_motivo": d1["motivo"], "v1_recorte_original": caja(d1["box"]),
                    "v1_calidad": q1, "v1_juicio": j1.get("juicio", ""),
                    "v2_vista": d2["var"], "v2_motivo": d2["motivo"], "v2_verificaciones": d2["verif"],
                    "v2_recorte_original": caja(d2["box"]), "v2_calidad": q2, "v2_juicio": j2.get("juicio", ""),
                    "categoria": cat, "tokens_imagen_v1": tokens["v1"], "tokens_imagen_v2": tokens["v2"],
                    "llamadas_por_captura": 1, "frase": j2.get("frase") or j1.get("frase", ""),
                    "evidencia": ("inspección visual del desarrollador" if (j1 or j2) else
                                  ("sin recorte en ninguna versión" if q1 == q2 == "foto_completa" else "sin revisar")),
                    "lectura_modelo": v2.SIN_MEDIR, "_img": base})
    campos = [c for c in filas[0] if not c.startswith("_")]
    with open(SALIDA / "tabla_antes_despues.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore"); w.writeheader(); w.writerows(filas)
    resumen = escribir_resumen(filas, res, huella)
    (SALIDA / "resumen_antes_despues.md").write_text(resumen, encoding="utf-8")
    escribir_html(filas, resumen)
    escribir_png(filas)
    sys.stdout.reconfigure(encoding="utf-8")
    print(resumen)


def conteos(filas, muestra, origen):
    F = [f for f in filas if f["muestra"] == muestra and f["origen"] == origen]
    c = {}
    for f in F:
        c[f["categoria"]] = c.get(f["categoria"], 0) + 1
    return F, c


def escribir_resumen(filas, res, huella):
    L = ["# Antes (v1) y después (v2) del ajuste del selector", "",
         "Misma configuración en ambas versiones: misma muestra, misma simulación de Android, misma preparación "
         "de imagen (1024 px, JPEG 85), mismo CLAHE. Solo cambia el detector/selector.", "",
         f"Huella del selector v2 al abrir la reserva: `{res['sha256_selector_v2_al_abrir'][:16]}…` · "
         f"actual: `{huella[:16]}…` · " + ("**coinciden: la reserva se evaluó sin retocar el selector**"
                                          if huella == res["sha256_selector_v2_al_abrir"] else
                                          "**NO coinciden: el selector cambió después de abrir la reserva**"), "",
         "Calidad de recorte = inspección visual del desarrollador (revision_visual.csv). "
         "Lectura del modelo: **sin medir** (no hay credenciales de Foundry en este entorno).", ""]
    orden = ["corregida_con_recorte", "vuelta_a_foto_completa", "sigue_defectuosa", "recorte_util_conservado",
             "recorte_util_perdido", "deterioro", "recorte_util_nuevo", "recorte_defectuoso_nuevo",
             "sin_cambio_foto_completa", "pendiente_de_revision"]
    for muestra in ("desarrollo", "reserva"):
        L += [f"## {muestra.capitalize()}", "", "| Categoría | lote | android |", "|---|---|---|"]
        cs = {o: conteos(filas, muestra, o) for o in v2.ORIGENES}
        n = {o: len(cs[o][0]) for o in v2.ORIGENES}
        for k in orden:
            if any(cs[o][1].get(k) for o in v2.ORIGENES):
                L.append(f"| {k} | {cs['lote'][1].get(k, 0)}/{n['lote']} | {cs['android'][1].get(k, 0)}/{n['android']} |")
        for o in v2.ORIGENES:
            F = cs[o][0]
            def_v1 = sum(1 for f in F if f["v1_calidad"] == "recorte_defectuoso")
            def_v2 = sum(1 for f in F if f["v2_calidad"] == "recorte_defectuoso")
            util_v1 = sum(1 for f in F if f["v1_calidad"] == "recorte_util")
            util_v2 = sum(1 for f in F if f["v2_calidad"] == "recorte_util")
            tok1 = sum(f["tokens_imagen_v1"] for f in F); tok2 = sum(f["tokens_imagen_v2"] for f in F)
            L.append(f"\n{o}: recortes defectuosos v1 {def_v1} → v2 {def_v2}; recortes útiles v1 {util_v1} → v2 {util_v2}; "
                     f"tokens de imagen estimados (anaquel) v1 {tok1} → v2 {tok2}; 1 llamada por captura en ambas.")
        L.append("")
    probl = [f for f in filas if f["muestra"] == "reserva" and (
        f["v2_calidad"] in ("recorte_defectuoso", "sin_revisar") or f["v2_juicio"] == "correcto_texto_cortado"
        or f["categoria"] in ("recorte_util_perdido", "deterioro"))]
    L += ["## Reserva: casos donde v2 corta texto, pierde un recorte útil, falla o falta revisar", ""]
    L += [f"- {f['capture_id']} {f['origen']}: v2 {f['v2_vista']}/{f['v2_motivo']} — "
          f"{f['v2_juicio'] or ('foto completa' if f['v2_vista'] == 'A' else 'sin revisar')}"
          f"{': ' + f['frase'] if f['frase'] else ''}" for f in probl] or ["- Ninguno."]
    return "\n".join(L) + "\n"


def escribir_html(filas, resumen):
    idx = {(f["muestra"], f["capture_id"], f["origen"]): f for f in filas}
    esc = html.escape
    def tarjeta(f):
        b = f["_img"]
        return (f"<div class=fila><h3>{esc(f['capture_id'])} · {esc(f['origen'])}</h3><div class=imgs>"
                f"<figure><img src='img/{b}_foto.jpg'><figcaption>Foto completa (rojo: recorte v1, verde: recorte v2)</figcaption></figure>"
                f"<figure><img src='img/{b}_v1.jpg'><figcaption>Antes · v1 envía {esc(f['v1_vista'])} ({esc(f['v1_motivo'])})</figcaption></figure>"
                f"<figure><img src='img/{b}_v2.jpg'><figcaption>Después · v2 envía {esc(f['v2_vista'])} ({esc(f['v2_motivo'])})</figcaption></figure>"
                f"</div><p class=frase>{esc(f['frase'])}</p></div>")
    foco = [idx[("desarrollo", c, o)] for c, o in FOCO]
    tabla = "".join(
        f"<tr><td>{esc(f['capture_id'])}</td><td>{esc(f['origen'])}</td><td>{esc(f['v1_juicio'] or f['v1_calidad'])}</td>"
        f"<td>{esc(f['v2_vista'])} · {esc(f['v2_motivo'])}</td><td>{esc(f['evidencia'])}; caja del importe anotada y "
        f"verificada en pruebas/test_regresion_capturas.py; lectura del modelo: sin medir</td></tr>" for f in foco)
    reserva = [f for f in filas if f["muestra"] == "reserva" and (f["v1_vista"] != "A" or f["v2_vista"] != "A")]
    md = esc(resumen).replace("\n", "<br>")
    doc = f"""<!doctype html><html lang=es><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Selector antes y después</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#111;max-width:1200px}}
.fila{{border-top:1px solid #ddd;padding:8px 0}}.imgs{{display:flex;gap:8px;flex-wrap:wrap}}figure{{margin:0;flex:1 1 300px}}
img{{max-width:100%;border:1px solid #ccc}}figcaption{{font-size:13px;color:#444}}.frase{{font-size:16px;margin:6px 0 0}}
table{{border-collapse:collapse;font-size:14px}}td,th{{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top}}
.aviso{{background:#fff4d6;padding:8px;border:1px solid #e6c200}}</style>
<h1>Selector de etiquetas: antes (v1) y después (v2)</h1>
<p class=aviso>Calidad de recorte verificada por inspección visual y por la caja anotada del importe. <b>Ninguna lectura de precio fue
confirmada por el modelo</b> (sin credenciales de Foundry). Archivo local: contiene fotos, no publicar.</p>
<h2>Fallas conocidas y controles</h2>{''.join(tarjeta(f) for f in foco)}
<h2>Tabla breve</h2><table><tr><th>ID</th><th>Origen</th><th>Problema anterior</th><th>Decisión nueva</th><th>Evidencia verificada</th></tr>{tabla}</table>
<h2>Conteos</h2><p>{md}</p>
<h2>Reserva: capturas donde alguna versión recorta</h2>{''.join(tarjeta(f) for f in reserva) or '<p>Ninguna.</p>'}
</html>"""
    (SALIDA / "antes_despues.html").write_text(doc, encoding="utf-8")


def _fuente(tam):
    for f in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def escribir_png(filas):
    """Lámina de las fallas conocidas y controles: foto, antes, después (para revisar sin navegador)."""
    import textwrap
    idx = {(f["muestra"], f["capture_id"], f["origen"]): f for f in filas}
    T, cab, pie = 300, 26, 64
    f_tit, f_txt = _fuente(15), _fuente(14)
    lam = Image.new("RGB", (3 * (T + 8), len(FOCO) * (T + cab + pie)), "white")
    d = ImageDraw.Draw(lam)
    for i, (cid, o) in enumerate(FOCO):
        f = idx[("desarrollo", cid, o)]
        y = i * (T + cab + pie)
        d.text((4, y + 4), f"{cid} · {o} — antes v1 {f['v1_vista']} ({f['v1_motivo']}) → después v2 {f['v2_vista']} "
                           f"({f['v2_motivo']})", fill="black", font=f_tit)
        for j, suf in enumerate(("foto", "v1", "v2")):
            im = Image.open(SALIDA / "img" / f"{f['_img']}_{suf}.jpg"); im.thumbnail((T, T))
            lam.paste(im, (j * (T + 8), y + cab))
        for k, renglon in enumerate(textwrap.wrap(f["frase"], 120)[:3]):
            d.text((4, y + cab + T + 4 + 18 * k), renglon, fill=(0, 0, 150), font=f_txt)
    lam.save(SALIDA / "antes_despues.png")


if __name__ == "__main__":
    main()
