"""Diagnóstico de las fallas del selector v1 (código congelado en linea_base/piloto_etiquetas_v1.py).

Réplica instrumentada de v1.detectar_etiquetas: mismos pasos y umbrales, pero registra cada etapa
(glifos, agrupación, crecimiento, margen, salvaguarda de borde). Antes de usar la traza se comprueba
que la réplica produce exactamente las mismas candidatas que v1.

Uso:  python diagnostico_v1.py            -> salida/diagnostico_v1/{traza.json, *_debug.png}
"""
import importlib.util
import json
import math
import sys
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

AQUI = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("v1", AQUI / "linea_base" / "piloto_etiquetas_v1.py")
v1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1)

CASOS = [  # (capture_id, origen, papel)
    ("CAP-563575", "android", "falla: pierde el primer dígito"),
    ("CAP-563575", "lote", "referencia: mismo caso en lote"),
    ("CAP-410562", "lote", "falla: corta el último cero"),
    ("CAP-635322", "lote", "falla: captura '$' y pierde el importe"),
    ("CAP-393881", "lote", "falla: código de barras"),
    ("CAP-393881", "android", "falla: código de barras"),
    ("CAP-520473", "lote", "control"),
    ("CAP-899554", "lote", "control"),
]


def detectar_traza(im):
    """Copia literal de v1.detectar_etiquetas + registro de etapas (coordenadas de trabajo)."""
    W0, H0 = im.size
    s = min(1.0, v1.TRABAJO_LADO / max(W0, H0))
    rgb = np.asarray(im.resize((round(W0 * s), round(H0 * s)), Image.LANCZOS) if s < 1 else im)
    H, W = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    Hh, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    fondo = ((S < 70) & (V > 140)) | ((Hh >= 15) & (Hh <= 40) & (S > 80) & (V > 140))
    bs = max(15, (min(W, H) // 12) | 1)
    tinta = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bs, 20)
    n, _, st, _ = cv2.connectedComponentsWithStats(tinta, 8)
    tinta_cc = [st[i] for i in range(1, n) if st[i][4] >= 12 and st[i][3] >= 0.01 * H]
    glifos = [st[i] for i in range(1, n)
              if 0.02 * H <= st[i][3] <= 0.3 * H and 0.12 <= st[i][2] / st[i][3] <= 1.2
              and 0.15 <= st[i][4] / (st[i][2] * st[i][3]) <= 0.9]
    padre = list(range(len(glifos)))
    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]; i = padre[i]
        return i
    for i, a in enumerate(glifos):
        for j in range(i + 1, len(glifos)):
            b = glifos[j]
            hm = max(a[3], b[3])
            gap = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
            if (0.7 <= a[3] / b[3] <= 1.43 and abs((a[1] + a[3] / 2) - (b[1] + b[3] / 2)) < 0.25 * hm
                    and gap < 0.6 * hm):
                padre[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(len(glifos)):
        grupos.setdefault(raiz(i), []).append(glifos[i])
    cands = []
    for g in grupos.values():
        if not (2 <= len(g) <= 7):
            continue
        tr = {"grupo_inicial": [list(map(int, a[:4])) for a in g], "crecimiento": []}
        gx0 = min(a[0] for a in g); gy0 = min(a[1] for a in g)
        gx1 = max(a[0] + a[2] for a in g); gy1 = max(a[1] + a[3] for a in g)
        hg = gy1 - gy0
        h0 = hg
        for _ in range(6):
            mx, my = 0.5 * hg, 0.25 * hg
            nuevos = [a for a in tinta_cc if 0.4 * h0 <= a[3] <= 3.5 * h0
                      and a[0] < gx1 + mx and a[0] + a[2] > gx0 - mx and a[1] < gy1 + my and a[1] + a[3] > gy0 - my
                      and not (gx0 <= a[0] and a[0] + a[2] <= gx1 and gy0 <= a[1] and a[1] + a[3] <= gy1)]
            if not nuevos:
                break
            tr["crecimiento"].append([list(map(int, a[:4])) for a in nuevos])
            gx0 = min([gx0] + [a[0] for a in nuevos]); gy0 = min([gy0] + [a[1] for a in nuevos])
            gx1 = max([gx1] + [a[0] + a[2] for a in nuevos]); gy1 = max([gy1] + [a[1] + a[3] for a in nuevos])
            hg = max([hg] + [a[3] for a in nuevos])
            if gx1 - gx0 > 14 * h0:
                break
        if gx1 - gx0 > 14 * h0:
            continue
        cortado = gx0 <= 1 or gx1 >= W - 1 or gy0 <= 1 or gy1 >= H - 1
        x0, y0 = max(0, gx0 - 1.6 * hg), max(0, gy0 - 1.3 * hg)
        x1, y1 = min(W, gx1 + 1.6 * hg), min(H, gy1 + 1.3 * hg)
        xi0, yi0, xi1, yi1 = int(x0), int(y0), int(x1), int(y1)
        borde = []
        for a in tinta_cc:
            if a[1] > gy1 or a[1] + a[3] < gy0:
                continue
            dentro_x = x0 <= a[0] and a[0] + a[2] <= x1
            toca_x = a[0] < x1 and a[0] + a[2] > x0
            cerca = (a[0] + a[2] > x0 - 2.5 * hg) and (a[0] < x1 + 2.5 * hg)
            if not cerca or dentro_x:
                continue
            f_alto = 0.5 * h0 <= a[3] <= 2 * hg
            f_ancho = not (a[2] > 1.2 * a[3])
            borde.append({"caja": list(map(int, a[:4])), "alto_rel_h0": round(a[3] / h0, 2),
                          "ancho_rel_alto": round(a[2] / a[3], 2), "pasa_filtro_alto": bool(f_alto),
                          "pasa_filtro_ancho": bool(f_ancho), "cruza_borde": bool(toca_x),
                          "fuera_completo": bool(not toca_x)})
        for a in tinta_cc:
            if not (0.5 * h0 <= a[3] <= 2 * hg) or a[2] > 1.2 * a[3] or a[1] > gy1 or a[1] + a[3] < gy0:
                continue
            dentro_x = x0 <= a[0] and a[0] + a[2] <= x1
            toca_x = a[0] < x1 and a[0] + a[2] > x0
            if toca_x and not dentro_x:
                cortado = True
                break
        zona = fondo[yi0:yi1, xi0:xi1]
        tz = tinta[yi0:yi1, xi0:xi1] > 0
        frac_fondo = float(zona.mean())
        otros = 1 - float((zona | tz).mean())
        tr.update(caja_grupo=[int(gx0), int(gy0), int(gx1), int(gy1)], h0=int(h0), hg=int(hg),
                  caja_recorte=[round(x0), round(y0), round(x1), round(y1)], trazos_fuera_a_la_altura=borde,
                  fondo=round(frac_fondo, 3), otros=round(otros, 3), descartada_por_fondo=bool(frac_fondo < 0.35 or otros > v1.OTROS_MAX))
        if frac_fondo < 0.35 or otros > v1.OTROS_MAX:
            continue
        cx, cy = (x0 + x1) / 2 / W - 0.5, (y0 + y1) / 2 / H - 0.5
        dist = math.hypot(cx, cy) / math.hypot(0.5, 0.5)
        score = (hg / H) * frac_fondo * (1 - otros) * (1 - 0.5 * dist)
        cands.append({
            "bbox": [x0 / s, y0 / s, x1 / s, y1 / s], "area_frac": (x1 - x0) * (y1 - y0) / (W * H),
            "fondo": round(frac_fondo, 3), "otros_tonos": round(otros, 3), "n_glifos": len(g),
            "digitos": True, "alto_digitos": hg / s,
            "desc_posible_fuera": y0 <= 0 or y1 >= H, "precio_toca_borde": cortado, "score": score, "_traza": tr})
    cands.sort(key=lambda d: -d["score"])
    final = []
    for c in cands:
        if all(v1.iou(c["bbox"], f["bbox"]) < 0.3 and not v1.contiene(f["bbox"], c["bbox"]) for f in final):
            final.append(c)
    return final, {"escala_trabajo": s, "W": W, "H": H, "rgb": rgb, "glifos": glifos}


def main():
    raiz = Path(os.environ.get("VALIDAT3B_DATOS", AQUI.parent.parent))
    out = AQUI / "salida" / "diagnostico_v1"
    out.mkdir(parents=True, exist_ok=True)
    caps = {c["capture_id"]: c for c in json.loads((raiz / "capturas.json").read_text(encoding="utf-8-sig"))}
    informe = []
    for cid, origen, papel in CASOS:
        orig = v1.cargar_rgb(raiz / caps[cid]["shelf_file"])
        src = orig if origen == "lote" else v1.simular_android(orig)
        cands_v1 = v1.detectar_etiquetas(src)
        cands, ctx = detectar_traza(src)
        assert [c["bbox"] for c in cands] == [c["bbox"] for c in cands_v1], f"réplica difiere de v1 en {cid} {origen}"
        reg = v1.region_recorte(cands_v1, src.size)
        sen = v1.senales_recorte(src.crop(reg["box"])) if reg else {"reflejo_posible": None, "contraste_L": None}
        elegida, motivo = v1.selector(reg, sen)
        best = cands[0] if cands else None
        tr = best["_traza"] if best else None
        informe.append({"capture_id": cid, "origen": origen, "papel": papel, "dims": list(src.size),
                        "escala_trabajo": round(ctx["escala_trabajo"], 4), "elegida_v1": elegida, "motivo_v1": motivo,
                        "n_candidatas": len(cands),
                        "candidatas": [{"score": round(c["score"], 4), "n_glifos": c["n_glifos"],
                                        "alto_digitos_trabajo": c["_traza"]["hg"], "caja_recorte_trabajo": c["_traza"]["caja_recorte"],
                                        "precio_toca_borde": c["precio_toca_borde"]} for c in cands[:4]],
                        "traza_mejor": tr})
        # imagen de depuración (resolución de trabajo, ampliada alrededor de la candidata elegida)
        img = Image.fromarray(ctx["rgb"]).convert("RGB"); d = ImageDraw.Draw(img)
        for a in ctx["glifos"]:
            d.rectangle([a[0], a[1], a[0] + a[2], a[1] + a[3]], outline=(170, 170, 170))
        for c in cands[1:4]:
            d.rectangle(c["_traza"]["caja_recorte"], outline=(255, 160, 0), width=2)
        if tr:
            for a in tr["grupo_inicial"]:
                d.rectangle([a[0], a[1], a[0] + a[2], a[1] + a[3]], outline=(0, 90, 255), width=2)
            for it in tr["crecimiento"]:
                for a in it:
                    d.rectangle([a[0], a[1], a[0] + a[2], a[1] + a[3]], outline=(0, 200, 220), width=2)
            for b in tr["trazos_fuera_a_la_altura"]:
                a = b["caja"]
                d.rectangle([a[0], a[1], a[0] + a[2], a[1] + a[3]], outline=(230, 0, 0), width=2)
            d.rectangle(tr["caja_recorte"], outline=(0, 190, 0), width=3)
            x0, y0, x1, y1 = tr["caja_recorte"]; m = max(x1 - x0, y1 - y0)
            img = img.crop((max(0, x0 - m), max(0, y0 - m // 2), min(ctx["W"], x1 + m), min(ctx["H"], y1 + m // 2)))
        f = 800 / max(img.size)
        img = img.resize((round(img.size[0] * f), round(img.size[1] * f)), Image.NEAREST)
        img.save(out / f"{cid}_{origen}_debug.png")
    (out / "traza.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1,
                                               default=lambda o: o.item() if hasattr(o, "item") else str(o)),
                                    encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for r in informe:
        t = r["traza_mejor"] or {}
        print(f"\n== {r['capture_id']} {r['origen']} ({r['papel']}) -> v1: {r['elegida_v1']} / {r['motivo_v1']}; "
              f"candidatas={r['n_candidatas']} escala={r['escala_trabajo']}")
        for c in r["candidatas"]:
            print("   cand:", c)
        if t:
            print("   grupo_inicial:", t["grupo_inicial"])
            print("   crecimiento:", t["crecimiento"])
            print("   caja_grupo:", t["caja_grupo"], "h0:", t["h0"], "hg:", t["hg"], "recorte:", t["caja_recorte"])
            for b in t["trazos_fuera_a_la_altura"]:
                print("   fuera/cruza:", b)


if __name__ == "__main__":
    main()
