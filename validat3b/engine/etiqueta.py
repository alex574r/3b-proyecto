"""Selección de vista de anaquel, basada en el piloto v2."""
import math

import cv2
import numpy as np
from PIL import Image

RECORTE_LADO, RECORTE_ESCALA_MAX = 1024, 4.0

CLAHE_CLIP, CLAHE_TILE = 2.0, (8, 8)

TRABAJO_LADO = 960

OTROS_MAX = 0.35

SEL_ETIQUETA_GRANDE = 0.30

SEL_CONTRASTE_BAJO = 80

REFLEJO_BLOB = 0.03

def clahe_L(im):
    lab = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE).apply(lab[..., 0])
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))

LINEA_GAP = 1.2

LINEA_ALTO = (0.25, 2.2)

LINEA_ANCHO_MAX = 2.5

LINEA_LARGO_MAX = 10

LINEA_MIEMBROS_MAX = 14

BARRAS_ASPECTO = 0.28

DIGITO_ANCHO_MIN = 0.4

IMPORTE_MAYOR = 2.0

MARGEN_X, MARGEN_Y = 1.6, 1.3

FRANJA = 1.0

TRAZO_DIGITO_ALTO = (0.5, 3.5)

TRAZO_DIGITO_ASPECTO = 1.6

AMPLIACIONES_MAX = 2

DESC_ALTO = (0.06, 0.6)

DESC_ANCHO_MAX = 8

DESC_MIN_TRAZOS = 3

DESC_EXTRA = 1.0

OTRA_ETIQUETA = 0.75

def _dist_cajas(a, b):
    dx = max(0, b[0] - a[2], a[0] - b[2])
    dy = max(0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)

def _solape_v(a, y0, y1):
    return min(a[1] + a[3], y1) - max(a[1], y0)

def _segmentar(im):
    """Igual que v1: escala de trabajo, fondo de etiqueta, tinta (umbral adaptativo) y componentes."""
    W0, H0 = im.size
    s = min(1.0, TRABAJO_LADO / max(W0, H0))
    rgb = np.asarray(im.resize((round(W0 * s), round(H0 * s)), Image.LANCZOS) if s < 1 else im)
    H, W = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    Hh, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    fondo = ((S < 70) & (V > 140)) | ((Hh >= 15) & (Hh <= 40) & (S > 80) & (V > 140))
    bs = max(15, (min(W, H) // 12) | 1)
    tinta = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, bs, 20)
    n, _, st, _ = cv2.connectedComponentsWithStats(tinta, 8)
    st = [tuple(int(v) for v in st[i]) for i in range(1, n)]
    comps = [a for a in st if a[4] >= 12 and a[3] >= 0.01 * H]
    glifos = [a for a in st if 0.02 * H <= a[3] <= 0.3 * H and 0.12 <= a[2] / a[3] <= 1.2
              and 0.15 <= a[4] / (a[2] * a[3]) <= 0.9]
    return {"s": s, "W": W, "H": H, "rgb": rgb, "fondo": fondo, "tinta": tinta, "comps": comps, "glifos": glifos}

def _agrupar(glifos):
    """Igual que v1: glifos vecinos de alto parecido, alineados y contiguos."""
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
    return [g for g in grupos.values() if 2 <= len(g) <= 7]

def _linea_importe(g, comps):
    """Une al grupo los trazos a la altura de sus dígitos separados por huecos <= LINEA_GAP alturas."""
    hc = max(a[3] for a in g)
    cy0, cy1 = min(a[1] for a in g), max(a[1] + a[3] for a in g)
    lx0, lx1 = min(a[0] for a in g), max(a[0] + a[2] for a in g)
    ly0, ly1 = cy0, cy1
    miembros = list(g)
    claves = {a[:4] for a in g}
    cambio = True
    while cambio and (lx1 - lx0) <= LINEA_LARGO_MAX * hc and len(miembros) <= LINEA_MIEMBROS_MAX:
        cambio = False
        for a in comps:
            if a[:4] in claves or not (LINEA_ALTO[0] * hc <= a[3] <= LINEA_ALTO[1] * hc) or a[2] > LINEA_ANCHO_MAX * hc:
                continue
            if _solape_v(a, cy0, cy1) < 0.5 * min(a[3], cy1 - cy0):
                continue
            if max(a[0] - lx1, lx0 - (a[0] + a[2])) > LINEA_GAP * max(hc, a[3]):
                continue
            claves.add(a[:4]); miembros.append(a); cambio = True
            lx0, lx1 = min(lx0, a[0]), max(lx1, a[0] + a[2])
            ly0, ly1 = min(ly0, a[1]), max(ly1, a[1] + a[3])
    return {"hc": hc, "filas": (cy0, cy1), "caja": (lx0, ly0, lx1, ly1), "miembros": miembros, "claves": claves,
            "glifos": list(g),
            "core": (min(a[0] for a in g), cy0, max(a[0] + a[2] for a in g), cy1)}

def _no_plausible(linea, grupos):
    """Motivo por el que la línea no es un precio, o None."""
    hc, (lx0, ly0, lx1, ly1) = linea["hc"], linea["caja"]
    if lx1 - lx0 > LINEA_LARGO_MAX * hc or len(linea["miembros"]) > LINEA_MIEMBROS_MAX:
        return "linea_de_texto"
    if not any(a[2] / a[3] >= DIGITO_ANCHO_MIN for a in linea["glifos"]):
        return "trazos_no_parecen_digitos"
    barras = [a for a in linea["miembros"] if a[3] >= 0.5 * hc and a[2] / a[3] < BARRAS_ASPECTO]
    if len(barras) >= 4 and len(barras) >= 0.5 * len(linea["miembros"]):
        return "parece_codigo_de_barras"
    for g in grupos:
        hg = max(a[3] for a in g)
        if hg >= IMPORTE_MAYOR * hc and not any(a[:4] in linea["claves"] for a in g):
            caja_g = (min(a[0] for a in g), min(a[1] for a in g), max(a[0] + a[2] for a in g), max(a[1] + a[3] for a in g))
            if _dist_cajas(caja_g, linea["caja"]) <= hg:
                return "importe_mayor_al_lado"
    return None

def _trazos_fuera(box, linea, comps):
    """Trazos compatibles con un dígito, a la altura del importe, que cruzan el borde del recorte o están
    en la franja exterior (FRANJA alturas). Incluye fragmentos anchos que v1 ignoraba."""
    hc, (cy0, cy1) = linea["hc"], linea["filas"]
    x0, y0, x1, y1 = box
    fb = FRANJA * hc
    fuera = []
    for a in comps:
        if a[:4] in linea["claves"]:
            continue
        if not (TRAZO_DIGITO_ALTO[0] * hc <= a[3] <= TRAZO_DIGITO_ALTO[1] * hc) or a[2] > TRAZO_DIGITO_ASPECTO * a[3]:
            continue
        if _solape_v(a, cy0, cy1) < 0.5 * min(a[3], cy1 - cy0):
            continue
        ax0, ax1 = a[0], a[0] + a[2]
        if x0 <= ax0 and ax1 <= x1:
            continue
        if ax1 > x0 - fb and ax0 < x1 + fb:
            fuera.append(a)
    return fuera

def _renglones_texto(box, linea, comps):
    """Renglones de texto (>= DESC_MIN_LETRAS trazos pequeños alineados) dentro del recorte, fuera del importe."""
    hc = linea["hc"]
    x0, y0, x1, y1 = box
    peq = [a for a in comps if a[:4] not in linea["claves"] and DESC_ALTO[0] * hc <= a[3] <= DESC_ALTO[1] * hc
           and a[2] <= DESC_ANCHO_MAX * a[3] and x0 <= a[0] and a[0] + a[2] <= x1 and y0 <= a[1] and a[1] + a[3] <= y1]
    padre = list(range(len(peq)))
    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]; i = padre[i]
        return i
    for i, a in enumerate(peq):
        for j in range(i + 1, len(peq)):
            b = peq[j]
            hm = max(a[3], b[3])
            gap = max(a[0], b[0]) - min(a[0] + a[2], b[0] + b[2])
            if 0.5 <= a[3] / b[3] <= 2 and abs((a[1] + a[3] / 2) - (b[1] + b[3] / 2)) < 0.5 * hm and gap < 1.5 * hm:
                padre[raiz(i)] = raiz(j)
    renglones = {}
    for i in range(len(peq)):
        renglones.setdefault(raiz(i), []).append(peq[i])
    def es_renglon(r):
        ancho = max(a[0] + a[2] for a in r) - min(a[0] for a in r)
        return len(r) >= DESC_MIN_TRAZOS or (len(r) >= 2 and ancho >= 1.5 * hc)
    return sum(1 for r in renglones.values() if es_renglon(r))

def _otra_etiqueta(box, linea, lineas_plausibles):
    """Otro importe plausible de tamaño parecido dentro del recorte."""
    x0, y0, x1, y1 = box
    for o in lineas_plausibles:
        if o is linea or o["hc"] < OTRA_ETIQUETA * linea["hc"]:
            continue
        if o["claves"] & linea["claves"]:
            continue
        cx0, cy0, cx1, cy1 = o["core"]
        ix = max(0, min(x1, cx1) - max(x0, cx0)); iy = max(0, min(y1, cy1) - max(y0, cy0))
        if ix * iy >= 0.5 * (cx1 - cx0) * (cy1 - cy0):
            return True
    return False

def detectar_etiquetas(im, traza=None):
    """Candidatas a etiqueta de precio (coordenadas de la imagen de entrada). Cada candidata indica si es
    apta para recortar ('apto_recorte') y, si no, el motivo; 'verificaciones' resume cada comprobación."""
    ctx = _segmentar(im)
    s, W, H, fondo, tinta, comps = ctx["s"], ctx["W"], ctx["H"], ctx["fondo"], ctx["tinta"], ctx["comps"]
    grupos = _agrupar(ctx["glifos"])
    lineas, descartes = [], []
    for g in grupos:
        linea = _linea_importe(g, comps)
        motivo = _no_plausible(linea, grupos)
        if motivo:
            descartes.append((linea, motivo))
        else:
            lineas.append(linea)
    cands = []
    for linea in lineas:
        hc = linea["hc"]
        lx0, ly0, lx1, ly1 = linea["caja"]
        box = [lx0 - MARGEN_X * hc, ly0 - MARGEN_Y * hc, lx1 + MARGEN_X * hc, ly1 + MARGEN_Y * hc]
        ver, motivo = [f"linea={len(linea['miembros'])} trazos"], None
        fuera = _trazos_fuera(box, linea, comps)
        for _ in range(AMPLIACIONES_MAX):
            if not fuera:
                break
            box = [min(box[0], min(a[0] for a in fuera) - 0.5 * hc), box[1],
                   max(box[2], max(a[0] + a[2] for a in fuera) + 0.5 * hc), box[3]]
            fuera = _trazos_fuera(box, linea, comps)
        if fuera:
            motivo = "trazos_del_importe_fuera"
        ver.append(f"franja={'con trazos' if fuera else 'limpia'}")
        # Si el importe termina a menos de un hueco entre dígitos del borde, podría seguir fuera de la foto.
        if motivo is None and (lx0 < LINEA_GAP * hc or lx1 > W - LINEA_GAP * hc):
            motivo = "importe_en_borde_de_foto"
        renglones = _renglones_texto(box, linea, comps)
        if renglones == 0:
            box2 = [box[0], box[1] - DESC_EXTRA * hc, box[2], box[3] + DESC_EXTRA * hc]
            renglones = _renglones_texto(box2, linea, comps)
            if renglones:
                box = box2
                ver.append("descripcion=tras ampliar")
        ver.append(f"descripcion={renglones} renglones")
        if motivo is None and renglones == 0:
            motivo = "sin_descripcion"
        otra = _otra_etiqueta(box, linea, lineas)
        ver.append(f"otra_etiqueta={'si' if otra else 'no'}")
        if motivo is None and otra:
            motivo = "otra_etiqueta_en_recorte"
        desc_fuera = box[1] < 0 or box[3] > H
        x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3])
        xi0, yi0, xi1, yi1 = int(x0), int(y0), int(x1), int(y1)
        zona = fondo[yi0:yi1, xi0:xi1]
        tz = tinta[yi0:yi1, xi0:xi1] > 0
        frac_fondo = float(zona.mean()) if zona.size else 0.0
        otros = 1 - float((zona | tz).mean()) if zona.size else 1.0
        if traza is not None:
            traza.append({"linea": [int(v) for v in linea["caja"]], "hc": hc, "trazos": len(linea["miembros"]),
                          "caja": [round(v) for v in box], "fondo": round(frac_fondo, 3), "otros": round(otros, 3),
                          "motivo": motivo, "verificaciones": ver})
        if frac_fondo < 0.35 or otros > OTROS_MAX:   # filtro de fondo de v1, sobre el recorte final
            continue
        cx, cy = (x0 + x1) / 2 / W - 0.5, (y0 + y1) / 2 / H - 0.5
        dist = math.hypot(cx, cy) / math.hypot(0.5, 0.5)
        score = (hc / H) * frac_fondo * (1 - otros) * (1 - 0.5 * dist)
        cands.append({
            "bbox": [x0 / s, y0 / s, x1 / s, y1 / s], "area_frac": (x1 - x0) * (y1 - y0) / (W * H),
            "fondo": round(frac_fondo, 3), "otros_tonos": round(otros, 3), "n_glifos": len(linea["miembros"]),
            "digitos": True, "alto_digitos": hc / s, "linea_bbox": [v / s for v in linea["caja"]],
            "desc_posible_fuera": desc_fuera, "precio_toca_borde": motivo in ("trazos_del_importe_fuera",
                                                                              "importe_en_borde_de_foto"),
            "apto_recorte": motivo is None, "motivo": motivo, "verificaciones": "; ".join(ver), "score": score})
    if traza is not None:
        for linea, motivo in descartes:
            traza.append({"linea": [int(v) for v in linea["caja"]], "hc": linea["hc"],
                          "trazos": len(linea["miembros"]), "descartada": motivo})
    cands.sort(key=lambda d: -d["score"])
    final = []
    for c in cands:
        if all(iou(c["bbox"], f["bbox"]) < 0.3 and not contiene(f["bbox"], c["bbox"]) for f in final):
            final.append(c)
    return final

def contiene(a, b):
    """b está mayormente dentro de a."""
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy >= 0.6 * (b[2] - b[0]) * (b[3] - b[1])

def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0

def region_recorte(cands, size):
    """Mejor candidata. Ambigua si otra etiqueta con dígitos de alto parecido (>=75 %) puntúa >=80 % de la
    mejor (regla de v1)."""
    if not cands:
        return None
    b = cands[0]
    rivales = [c for c in cands[1:] if c["score"] >= 0.8 * b["score"] and c["alto_digitos"] >= 0.75 * b["alto_digitos"]]
    W, H = size
    box = [max(0, b["bbox"][0]), max(0, b["bbox"][1]), min(W, b["bbox"][2]), min(H, b["bbox"][3])]
    return {"box": [round(v) for v in box], "etiqueta": b, "varias_etiquetas": bool(rivales),
            "n_candidatas": len(cands), "n_rivales": len(rivales)}

def senales_recorte(crop):
    a = np.asarray(crop)
    L = cv2.cvtColor(a, cv2.COLOR_RGB2LAB)[..., 0]
    contraste = float(np.percentile(L, 95) - np.percentile(L, 5))
    sat = (a.min(axis=2) >= 245).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(sat, 8)
    blob = max((st[i][4] for i in range(1, n)), default=0) / sat.size
    return {"contraste_L": round(contraste, 1), "blob_saturado": round(float(blob), 4),
            "reflejo_posible": blob > REFLEJO_BLOB}

def selector(reg, sen):
    """Selector operativo: solo señales locales, antes de llamar al modelo. Devuelve (variante, motivo).
    Ante cualquier duda sobre el recorte devuelve la foto completa (A): nunca completa ni reconstruye dígitos."""
    if reg is None:
        return "A", "sin_etiqueta_fiable"
    if reg["varias_etiquetas"]:
        return "A", "varias_etiquetas"
    if not reg["etiqueta"]["apto_recorte"]:
        return "A", reg["etiqueta"]["motivo"]
    if reg["etiqueta"]["area_frac"] > SEL_ETIQUETA_GRANDE:
        return "A", "etiqueta_ya_grande"
    if sen["reflejo_posible"]:
        return "B", "recorte_con_reflejo"  # CLAHE no recupera saturación y amplifica su borde
    if sen["contraste_L"] < SEL_CONTRASTE_BAJO:
        return "C", "bajo_contraste"
    return "B", "recorte_fiable"

def preparar(im):
    regiones = detectar_etiquetas(im)
    region = region_recorte(regiones, im.size)
    crop = im.crop(region["box"]) if region else None
    vista, motivo = selector(region, senales_recorte(crop) if crop is not None else {})
    if vista == "A":
        return im, vista, motivo
    if vista == "C":
        crop = clahe_L(crop)
    escala = min(RECORTE_LADO / max(crop.size), RECORTE_ESCALA_MAX)
    size = tuple(max(1, round(n * escala)) for n in crop.size)
    return crop.resize(size, Image.Resampling.LANCZOS), vista, motivo
