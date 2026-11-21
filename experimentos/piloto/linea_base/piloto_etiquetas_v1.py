"""Piloto Validat3B: recuperación de etiquetas de anaquel (variantes A/B/C + selector operativo).

Por defecto es 100 % local (cero tokens): genera la muestra, las variantes, la tabla, el informe y la
comparación visual. La lectura remota con Azure AI Foundry solo se activa con --remoto y --max-llamadas.

Aislado de la app y del motor: no importa ni modifica validat3b/ ni 3bApp/. Replica sus parámetros:
  - Android  ValidatApi.jpeg(): lado máximo 1280 (solo reduce), JPEG calidad 85.
  - Backend  vision._img_block(): exif_transpose, thumbnail 1024 (solo reduce), JPEG calidad 85.
Referencia: github.com/alex574r/3b-proyecto @ d196c6f05fefb2309f550f2271d008e37b487aab.

El lector y el selector NUNCA reciben precio reportado, decisión histórica, motivo ni anotaciones.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

AQUI = Path(__file__).resolve().parent
REF_COMMIT = "d196c6f05fefb2309f550f2271d008e37b487aab"

ANDROID_MAX, BACKEND_MAX, JPEG_Q = 1280, 1024, 85
RECORTE_LADO, RECORTE_ESCALA_MAX = 1024, 4.0
CLAHE_CLIP, CLAHE_TILE = 2.0, (8, 8)
TRABAJO_LADO = 960  # resolución de trabajo del detector (coordenadas se devuelven en la imagen de origen)
OTROS_MAX = 0.35    # fracción máxima de píxeles que no son fondo de etiqueta ni tinta

# Umbrales del selector: elegidos a mano en desarrollo, NO calibrados con lecturas.
SEL_ETIQUETA_GRANDE = 0.30   # si la etiqueta ya ocupa >30 % de la foto, recortar no aporta: A
SEL_CONTRASTE_BAJO = 80      # rango p5-p95 de L en el recorte; por debajo -> C (CLAHE)
REFLEJO_BLOB = 0.03          # blob saturado >3 % del recorte -> reflejo_posible

ENDPOINT = "https://softwaredevelopment-resource.services.ai.azure.com/anthropic"  # el asignado (vision.py)
MODEL = "claude-haiku-5-5"
PROMPT_VERSION = "lector-v2"
SYSTEM = ("Transcribes etiquetas de precio de anaquel en tiendas de México. Describe solo lo que se ve; "
          "no adivines dígitos. Responde únicamente con un objeto JSON válido, sin texto extra.")
PROMPT = """Foto 1: el producto. Foto 2: el anaquel o un recorte de su etiqueta de precio.
Lee la etiqueta de precio que corresponde al producto de la foto 1.
- Si algún dígito del precio está tapado, borroso, cortado o en una zona blanca por reflejo, NO lo completes:
  precio null y estado "indeterminada".
- Si hay varias etiquetas y no se puede saber cuál corresponde al producto, estado "asociacion_ambigua".
- Si no ves el signo "$" del precio o algún dígito toca el borde de la imagen, puede faltar una cifra:
  precio null y estado "indeterminada".
- asociacion: "coincide" si la descripción de la etiqueta corresponde al producto de la foto 1 (marca,
  variante, contenido), "no_coincide" si describe otro, "ambigua" si no alcanza a leerse.
Devuelve:
{"estado": "legible"|"indeterminada"|"asociacion_ambigua", "precio": number|null,
 "texto_etiqueta": str|null, "asociacion": "coincide"|"no_coincide"|"ambigua", "motivo": str}"""

SIN_MEDIR = "sin medir"
VARIANTES = ("A", "B", "C")
ORIGENES = ("lote", "android")


# ----------------------------------------------------------------------------- utilidades de imagen
def cargar_rgb(path):
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def jpeg_ida_vuelta(im, q=JPEG_Q):
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    data = buf.getvalue()
    return Image.open(io.BytesIO(data)).convert("RGB"), data


def simular_android(im):
    """ValidatApi.jpeg: reduce si el lado mayor > 1280 (nunca amplía) y recomprime a JPEG 85."""
    w, h = im.size
    s = ANDROID_MAX / max(w, h)
    if s < 1:
        im = im.resize((int(w * s), int(h * s)), Image.LANCZOS)
    return jpeg_ida_vuelta(im)[0]


def preparar_backend(im):
    """vision._img_block: thumbnail 1024 (solo reduce) + JPEG 85. Devuelve (bytes, tamaño)."""
    im = im.copy()
    im.thumbnail((BACKEND_MAX, BACKEND_MAX))
    out, data = jpeg_ida_vuelta(im)
    return data, out.size


def preparar_recorte(im):
    """Recorte -> lado mayor 1024 (amplía hasta 4x con Lanczos) + JPEG 85."""
    w, h = im.size
    s = min(RECORTE_LADO / max(w, h), RECORTE_ESCALA_MAX)
    im2 = im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    out, data = jpeg_ida_vuelta(im2)
    return data, out.size, s


def clahe_L(im):
    lab = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=CLAHE_CLIP, tileGridSize=CLAHE_TILE).apply(lab[..., 0])
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def nitidez(gray):
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def tokens_imagen_est(size):
    """Aproximación pública de Anthropic: (ancho*alto)/750 tras ajustar a 1568 px / 1.15 MP."""
    w, h = size
    s = min(1.0, 1568 / max(w, h), math.sqrt(1_150_000 / (w * h)))
    return math.ceil((w * s) * (h * s) / 750)


# ----------------------------------------------------------------------------- detector de etiquetas
def detectar_etiquetas(im):
    """Detector "dígitos primero". 1) Glifos oscuros sobre claro (umbral adaptativo). 2) Grupos de >=2
    glifos de alto parecido, alineados y contiguos (candidato a precio). 3) Verifica fondo de etiqueta
    (blanco o amarillo, plano) alrededor del grupo. Coordenadas en la imagen de entrada."""
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
    tinta_cc = [st[i] for i in range(1, n) if st[i][4] >= 12 and st[i][3] >= 0.01 * H]
    glifos = [st[i] for i in range(1, n)
              if 0.02 * H <= st[i][3] <= 0.3 * H and 0.12 <= st[i][2] / st[i][3] <= 1.2
              and 0.15 <= st[i][4] / (st[i][2] * st[i][3]) <= 0.9]
    # unión de glifos vecinos de alto parecido
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
        if not (2 <= len(g) <= 7):   # un precio tiene pocas cifras grandes; líneas largas de texto se descartan
            continue
        gx0 = min(a[0] for a in g); gy0 = min(a[1] for a in g)
        gx1 = max(a[0] + a[2] for a in g); gy1 = max(a[1] + a[3] for a in g)
        hg = gy1 - gy0
        # Crecer hacia trazos vecinos (un "1" delgado, "$", pesos junto a centavos) para no cortar el
        # precio: un precio truncado y nítido ("4.00" en vez de "14.00") es el peor error posible.
        h0 = hg
        for _ in range(6):
            mx, my = 0.5 * hg, 0.25 * hg
            nuevos = [a for a in tinta_cc if 0.4 * h0 <= a[3] <= 3.5 * h0
                      and a[0] < gx1 + mx and a[0] + a[2] > gx0 - mx and a[1] < gy1 + my and a[1] + a[3] > gy0 - my
                      and not (gx0 <= a[0] and a[0] + a[2] <= gx1 and gy0 <= a[1] and a[1] + a[3] <= gy1)]
            if not nuevos:
                break
            gx0 = min([gx0] + [a[0] for a in nuevos]); gy0 = min([gy0] + [a[1] for a in nuevos])
            gx1 = max([gx1] + [a[0] + a[2] for a in nuevos]); gy1 = max([gy1] + [a[1] + a[3] for a in nuevos])
            hg = max([hg] + [a[3] for a in nuevos])
            if gx1 - gx0 > 14 * h0:  # creció hacia texto corrido o el borde de un empaque: no es una etiqueta
                break
        if gx1 - gx0 > 14 * h0:
            continue
        cortado = gx0 <= 1 or gx1 >= W - 1 or gy0 <= 1 or gy1 >= H - 1
        # caja estimada de etiqueta: precio + margen para "$", centavos y descripción arriba/abajo
        x0, y0 = max(0, gx0 - 1.6 * hg), max(0, gy0 - 1.3 * hg)
        x1, y1 = min(W, gx1 + 1.6 * hg), min(H, gy1 + 1.3 * hg)
        xi0, yi0, xi1, yi1 = int(x0), int(y0), int(x1), int(y1)
        # Salvaguarda: un trazo a la altura del precio que cruza el borde del recorte indica precio cortado.
        for a in tinta_cc:
            if not (0.5 * h0 <= a[3] <= 2 * hg) or a[2] > 1.2 * a[3] or a[1] > gy1 or a[1] + a[3] < gy0:
                continue  # solo trazos con forma de dígito a la altura del precio (no rieles ni bordes)
            dentro_x = x0 <= a[0] and a[0] + a[2] <= x1
            toca_x = a[0] < x1 and a[0] + a[2] > x0
            if toca_x and not dentro_x:
                cortado = True
                break
        zona = fondo[yi0:yi1, xi0:xi1]
        tz = tinta[yi0:yi1, xi0:xi1] > 0
        frac_fondo = float(zona.mean())
        otros = 1 - float((zona | tz).mean())
        if frac_fondo < 0.35 or otros > OTROS_MAX:
            continue
        cx, cy = (x0 + x1) / 2 / W - 0.5, (y0 + y1) / 2 / H - 0.5
        dist = math.hypot(cx, cy) / math.hypot(0.5, 0.5)
        score = (hg / H) * frac_fondo * (1 - otros) * (1 - 0.5 * dist)
        cands.append({
            "bbox": [x0 / s, y0 / s, x1 / s, y1 / s], "area_frac": (x1 - x0) * (y1 - y0) / (W * H),
            "fondo": round(frac_fondo, 3), "otros_tonos": round(otros, 3), "n_glifos": len(g),
            "digitos": True, "alto_digitos": hg / s,
            "desc_posible_fuera": y0 <= 0 or y1 >= H, "precio_toca_borde": cortado, "score": score})
    cands.sort(key=lambda d: -d["score"])
    # quitar duplicados solapados (p. ej. pesos y centavos como grupos distintos de la misma etiqueta)
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
    """Mejor candidata (la caja ya incluye margen para descripción). Ambigua si otra etiqueta con
    dígitos de alto parecido (>=75 %) puntúa >=80 % de la mejor."""
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
    """Selector operativo: solo señales locales, antes de llamar al modelo. Devuelve (variante, motivo)."""
    if reg is None:
        return "A", "sin_etiqueta_fiable"
    if reg["varias_etiquetas"]:
        return "A", "varias_etiquetas"
    if reg["etiqueta"]["precio_toca_borde"]:
        return "A", "precio_toca_borde"
    if reg["etiqueta"]["area_frac"] > SEL_ETIQUETA_GRANDE:
        return "A", "etiqueta_ya_grande"
    if sen["reflejo_posible"]:
        return "B", "recorte_con_reflejo"  # CLAHE no recupera saturación y amplifica su borde
    if sen["contraste_L"] < SEL_CONTRASTE_BAJO:
        return "C", "bajo_contraste"
    return "B", "recorte_fiable"


# ----------------------------------------------------------------------------- muestra
def h(s):
    return hashlib.sha1(s.encode()).hexdigest()


def glare_score(path):
    im = cargar_rgb(path)
    im.thumbnail((960, 960))
    sat = (np.asarray(im).min(axis=2) >= 245).astype(np.uint8)
    n, _, st, _ = cv2.connectedComponentsWithStats(sat, 8)
    return max((st[i][4] for i in range(1, n)), default=0) / sat.size


def elegir_muestra(caps, raiz):
    """Estratificada y determinista (orden por sha1(capture_id)). La decisión histórica se usa SOLO
    para estratificar la muestra; nunca llega al detector, al selector ni al lector."""
    orden = sorted(caps, key=lambda c: h(c["capture_id"]))
    def grupo(pred, n):
        return [c["capture_id"] for c in orden if pred(c)][:n]
    def rechazo(t):
        return lambda c: (c.get("motivo_rechazo") or "").startswith(t)
    sel = {}
    for cid in grupo(lambda c: c["decision_esperada"] == "aprobada", 3): sel[cid] = "control_aprobada"
    for cid in grupo(rechazo("Capturas lejanas"), 3): sel[cid] = "lejana"
    for cid in grupo(rechazo("Capturas borrosas"), 3): sel[cid] = "borrosa"
    for cid in grupo(rechazo("Descrip"), 2): sel[cid] = "descripcion_incompleta"
    for cid in grupo(lambda c: c["decision_esperada"] == "revision_manual", 2): sel[cid] = "revision_manual"
    # reflejos: señal local (blob saturado) porque no hay etiqueta histórica de reflejo
    g = sorted(((glare_score(raiz / c["shelf_file"]), c["capture_id"]) for c in orden), reverse=True)
    for sc, cid in [x for x in g if x[0] > 0.003 and x[1] not in sel][:2]:
        sel[cid] = f"reflejo_posible({sc:.3f})"
    # todos los originales grandes: único caso donde Android/backend reducen resolución
    for c in orden:
        if max(Image.open(raiz / c["shelf_file"]).size) > ANDROID_MAX and c["capture_id"] not in sel:
            sel[c["capture_id"]] = "original_alta_resolucion"
    return sel


# ----------------------------------------------------------------------------- lector remoto
class Lector:
    """Lector remoto con tope duro de llamadas nuevas, caché local y corte ante errores no recuperables."""
    ESTADOS = {"legible", "indeterminada", "asociacion_ambigua"}

    def __init__(self, salida, max_llamadas):
        key = os.environ.get("FOUNDRY_API_KEY")
        if not key:
            sys.exit("--remoto requiere la variable de entorno FOUNDRY_API_KEY (no se lee de archivos).")
        import anthropic  # import diferido: el modo local no lo necesita
        self.client = anthropic.AnthropicFoundry(api_key=key, base_url=ENDPOINT, max_retries=2, timeout=60)
        # Errores que no se arreglan reintentando: cortar la fase remota en vez de gastar el tope.
        self.no_recuperables = (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                                anthropic.NotFoundError, anthropic.BadRequestError)
        self.max, self.usadas, self.errores_seguidos, self.abortado = max_llamadas, 0, 0, None
        self.cache_path, self.log_path = salida / "lecturas_cache.jsonl", salida / "consumo.jsonl"
        self.cache = cargar_cache(self.cache_path)

    def leer(self, prod_bytes, shelf_bytes, meta):
        k = clave_cache(prod_bytes, shelf_bytes)
        if k in self.cache:
            return {**self.cache[k], "llamadas": 0, "desde_cache": True}
        if self.abortado or self.usadas >= self.max:
            return None
        self.usadas += 1
        content = [{"type": "text", "text": PROMPT}]
        for b in (prod_bytes, shelf_bytes):
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(b).decode()}})
        t0 = time.perf_counter()
        try:
            msg = self.client.messages.create(model=MODEL, max_tokens=1024, thinking={"type": "disabled"},
                                              system=SYSTEM, messages=[{"role": "user", "content": content}])
        except Exception as e:  # sin trazas ni cuerpos de respuesta en el log
            nombre = type(e).__name__
            status = getattr(e, "status_code", None)
            self._log({**meta, "error": nombre, "status": status})
            self.errores_seguidos += 1
            if isinstance(e, self.no_recuperables):
                self.abortado = f"{nombre} (HTTP {status})"
            elif self.errores_seguidos >= 3:
                self.abortado = f"3 errores seguidos (último: {nombre})"
            print(f"  [{self.usadas}/{self.max}] {meta['capture_id']} {meta['origen']} {meta['variante']}: "
                  f"error {nombre}" + (f" -> se detiene la fase remota: {self.abortado}" if self.abortado else ""),
                  flush=True)
            return {"estado_lectura": "error_llamada", "llamadas": 1}
        self.errores_seguidos = 0
        lat = round((time.perf_counter() - t0) * 1000)
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        if msg.stop_reason == "refusal":
            r = {"estado_lectura": "rechazo_modelo"}
        else:
            try:
                j = json.loads(text[text.find("{"): text.rfind("}") + 1])
                est = j.get("estado")
                r = {"estado_lectura": est if est in self.ESTADOS else "json_invalido",
                     "precio_leido": normalizar_precio(j.get("precio")),
                     "texto_etiqueta": j.get("texto_etiqueta"), "asociacion": j.get("asociacion")}
            except ValueError:
                r = {"estado_lectura": "json_invalido"}
        r.update(latencia_modelo_ms=lat, tokens_entrada=msg.usage.input_tokens,
                 tokens_salida=msg.usage.output_tokens)
        self._log({**meta, "latencia_ms": lat, "tokens_entrada": msg.usage.input_tokens,
                   "tokens_salida": msg.usage.output_tokens, "stop_reason": msg.stop_reason,
                   "estado": r["estado_lectura"]})
        with open(self.cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"clave": k, **r}, ensure_ascii=False) + "\n")
        self.cache[k] = r
        print(f"  [{self.usadas}/{self.max}] {meta['capture_id']} {meta['origen']} {meta['variante']}: "
              f"{r['estado_lectura']} ({lat} ms)", flush=True)
        return {**r, "llamadas": 1}

    def _log(self, d):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "modelo": MODEL, **d}) + "\n")


def normalizar_precio(v):
    """Número o None. Acepta "18.50", "$18.50" o "1,299.00"; cualquier otra cosa -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def clave_cache(prod_bytes, shelf_bytes):
    return hashlib.sha256(prod_bytes + shelf_bytes + PROMPT_VERSION.encode() + MODEL.encode()).hexdigest()


def cargar_cache(p):
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            out[d.pop("clave")] = d
    return out


# ----------------------------------------------------------------------------- evaluación con anotaciones
def cargar_anotaciones(p):
    if not p or not Path(p).exists():
        return {}
    out = {}
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if (r.get("estado_anotacion") or "").strip():
                out[r["capture_id"]] = r
    return out


def calificar(fila, anot):
    """correcta | incorrecta | indeterminada | (sin anotación / sin medir)."""
    est = fila.get("estado_lectura")
    if est in (None, SIN_MEDIR, "", "error_llamada"):
        return SIN_MEDIR
    if anot is None:
        return "sin_anotacion"
    a_est = anot["estado_anotacion"].strip()
    leyo = est == "legible" and fila.get("precio_leido") not in (None, "")
    if not leyo:
        return "indeterminada"
    if a_est != "legible":   # el evaluador no pudo leerla o la asociación es ambigua: leer un precio es error
        return "incorrecta"
    ok_precio = abs(float(fila["precio_leido"]) - float(anot["precio_legible"])) < 0.005
    ok_asoc = fila.get("asociacion") == "coincide"
    return "correcta" if ok_precio and ok_asoc else "incorrecta"


# ----------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default=str(AQUI.parent.parent), help="carpeta con capturas.json e imagenes/")
    ap.add_argument("--salida", default=str(AQUI / "salida"))
    ap.add_argument("--muestra", default=str(AQUI / "muestra_dev.json"),
                    help="IDs de la muestra; se crea si no existe")
    ap.add_argument("--anotaciones", default=str(AQUI / "anotaciones_dev.csv"))
    ap.add_argument("--remoto", action="store_true", help="habilita lecturas en Foundry (consume tokens)")
    ap.add_argument("--max-llamadas", type=int, default=0, help="tope de llamadas remotas nuevas (obligatorio)")
    ap.add_argument("--solo-seleccion", action="store_true",
                    help="con --remoto, lee solo la vista elegida por el selector y A (base)")
    args = ap.parse_args()
    if args.remoto and args.max_llamadas <= 0:
        sys.exit("--remoto exige --max-llamadas N (N > 0).")

    raiz, salida = Path(args.datos), Path(args.salida)
    (salida / "vistas").mkdir(parents=True, exist_ok=True)
    caps = {c["capture_id"]: c for c in json.loads((raiz / "capturas.json").read_text(encoding="utf-8-sig"))}

    mpath = Path(args.muestra)
    if mpath.exists():
        muestra = json.loads(mpath.read_text(encoding="utf-8"))
    else:
        sel = elegir_muestra(list(caps.values()), raiz)
        muestra = {"criterio": (
            "Determinista: capturas ordenadas por sha1(capture_id); se toman 3 aprobadas (control), 3 rechazos "
            "por lejanía, 3 por desenfoque, 2 por descripción incompleta, 2 revisiones manuales, hasta 2 con "
            "mayor blob casi saturado (RGB>=245, >0.3 % de la foto) en la foto de anaquel como posible reflejo y todas las fotos de anaquel "
            f"con lado mayor >{ANDROID_MAX}px. La decisión histórica solo estratifica; no llega al detector, "
            "selector ni lector. Las demás capturas quedan reservadas."),
            "commit_referencia": REF_COMMIT, "ids": sel}
        mpath.write_text(json.dumps(muestra, ensure_ascii=False, indent=2), encoding="utf-8")
    ids = list(muestra["ids"])

    plantilla = AQUI / "plantilla_anotaciones.csv"
    if not plantilla.exists():
        with open(plantilla, "w", newline="", encoding="utf-8-sig") as f:
            wr = csv.writer(f)
            # estado_anotacion: legible | ilegible | asociacion_ambigua (leyendo el ORIGINAL a resolución completa)
            # recorte_*_ok: si | no_region_equivocada | no_precio_cortado | no_descripcion_fuera (ver vistas/)
            wr.writerow(["capture_id", "estado_anotacion", "precio_legible", "texto_producto_etiqueta",
                         "etiqueta_en_original_x0y0x1y1", "recorte_lote_ok", "recorte_android_ok",
                         "evaluador", "notas"])
            for cid in ids:
                wr.writerow([cid] + [""] * 8)

    anot = cargar_anotaciones(args.anotaciones)
    lector = Lector(salida, args.max_llamadas) if args.remoto else None
    cache = cargar_cache(salida / "lecturas_cache.jsonl")
    filas, visual = [], []

    for cid in ids:
        c = caps[cid]
        orig = cargar_rgb(raiz / c["shelf_file"])
        prod_orig = cargar_rgb(raiz / c["product_file"])
        g_orig = cv2.cvtColor(np.asarray(orig), cv2.COLOR_RGB2GRAY)
        nit_orig = round(nitidez(g_orig), 1)
        th = orig.copy(); th.thumbnail((BACKEND_MAX, BACKEND_MAX))
        nit_1024 = round(nitidez(cv2.cvtColor(np.asarray(th), cv2.COLOR_RGB2GRAY)), 1)
        vis_cap = {"cid": cid, "grupo": muestra["ids"][cid], "origenes": {}}

        for origen in ORIGENES:
            t0 = time.perf_counter()
            src = orig if origen == "lote" else simular_android(orig)
            prod = prod_orig if origen == "lote" else simular_android(prod_orig)
            prod_bytes, _ = preparar_backend(prod)        # constante entre A/B/C dentro del origen
            cands = detectar_etiquetas(src)
            reg = region_recorte(cands, src.size)
            vistas = {}
            a_bytes, a_size = preparar_backend(src)
            vistas["A"] = {"bytes": a_bytes, "size": a_size, "escala": a_size[0] / src.size[0], "box": None}
            sen = {"contraste_L": None, "blob_saturado": None, "reflejo_posible": None}
            if reg:
                crop = src.crop(reg["box"])
                sen = senales_recorte(crop)
                b_bytes, b_size, s = preparar_recorte(crop)
                c_bytes, c_size, _ = preparar_recorte(clahe_L(crop))
                vistas["B"] = {"bytes": b_bytes, "size": b_size, "escala": s, "box": reg["box"]}
                vistas["C"] = {"bytes": c_bytes, "size": c_size, "escala": s, "box": reg["box"]}
            elegida, motivo = selector(reg, sen)
            prep_ms = round((time.perf_counter() - t0) * 1000)
            k_src = src.size[0] / orig.size[0]  # para devolver coordenadas al original
            for v in VARIANTES:
                vi = vistas.get(v)
                fname = f"{cid}_{origen}_{v}.jpg"
                if vi:
                    (salida / "vistas" / fname).write_bytes(vi["bytes"])
                et = reg["etiqueta"] if reg else None
                fila = {
                    "capture_id": cid, "grupo_muestra": muestra["ids"][cid], "origen": origen, "variante": v,
                    "elegida_por_selector": v == elegida, "motivo_selector": motivo,
                    "dims_origen": f"{src.size[0]}x{src.size[1]}",
                    "region_original_x0y0x1y1": (" ".join(str(round(t / k_src)) for t in reg["box"]) if reg and v != "A"
                                                 else ("imagen completa" if v == "A" else "sin región")),
                    "n_candidatas": reg["n_candidatas"] if reg else 0,
                    "varias_etiquetas": reg["varias_etiquetas"] if reg else None,
                    "descripcion_posible_fuera": et["desc_posible_fuera"] if et else None,
                    "reflejo_posible": sen["reflejo_posible"], "contraste_L_recorte": sen["contraste_L"],
                    "nitidez_original": nit_orig, "nitidez_1024": nit_1024,
                    "dims_enviada": f"{vi['size'][0]}x{vi['size'][1]}" if vi else "no generada",
                    "escala_aplicada": round(vi["escala"], 3) if vi else None,
                    "alto_etiqueta_px_enviado": round((et["bbox"][3] - et["bbox"][1]) * vi["escala"]) if vi and et else None,
                    "alto_digitos_px_nativos": round(et["alto_digitos"]) if et else None,  # detalle real en la fuente
                    "alto_digitos_px_enviado": round(et["alto_digitos"] * vi["escala"]) if vi and et and et["digitos"] else None,
                    "bytes_jpeg": len(vi["bytes"]) if vi else None,
                    "tokens_imagen_est": tokens_imagen_est(vi["size"]) if vi else None,
                    "prep_local_ms": prep_ms,
                    "precio_leido": SIN_MEDIR, "texto_etiqueta": SIN_MEDIR, "asociacion": SIN_MEDIR,
                    "estado_lectura": SIN_MEDIR, "latencia_modelo_ms": SIN_MEDIR, "llamadas": 0,
                    "tokens_entrada": SIN_MEDIR, "tokens_salida": SIN_MEDIR,
                }
                if vi:
                    leer = not args.solo_seleccion or v in ("A", elegida)
                    r = None
                    if lector and leer:
                        r = lector.leer(prod_bytes, vi["bytes"], {"capture_id": cid, "origen": origen, "variante": v})
                    elif not lector:
                        r = cache.get(clave_cache(prod_bytes, vi["bytes"]))
                        r = {**r, "llamadas": 0} if r else None
                    if r:
                        fila.update({k: r[k] for k in r if k in fila})
                else:
                    fila["estado_lectura"] = "no_aplica (sin recorte)"
                filas.append(fila)
            # fila del selector = copia de la variante elegida (elegida ANTES de conocer la lectura)
            fsel = dict(next(f for f in filas if f["capture_id"] == cid and f["origen"] == origen
                             and f["variante"] == elegida))
            fsel["variante"] = f"SEL->{elegida}"
            filas.append(fsel)
            vis_cap["origenes"][origen] = {"cands": cands[:5], "reg": reg, "elegida": elegida, "motivo": motivo,
                                           "src_size": src.size, "orig_scale": k_src}

        # miniatura del original con candidatas (gris) y región elegida (verde) para la comparación visual
        im = orig.copy(); d = ImageDraw.Draw(im); lw = max(2, orig.size[0] // 200)
        o = vis_cap["origenes"]["lote"]
        for cc in o["cands"]:
            d.rectangle(cc["bbox"], outline=(150, 150, 150), width=lw)
        if o["reg"]:
            d.rectangle(o["reg"]["box"], outline=(0, 200, 0), width=lw * 2)
        im.thumbnail((480, 480)); im.save(salida / "vistas" / f"{cid}_original_marcado.jpg", quality=85)
        visual.append(vis_cap)

    for f in filas:
        f["resultado_vs_anotacion"] = calificar(f, anot.get(f["capture_id"])) if anot else SIN_MEDIR

    campos = list(filas[0].keys())
    with open(salida / "tabla_piloto.csv", "w", newline="", encoding="utf-8-sig") as fh:
        wr = csv.DictWriter(fh, fieldnames=campos); wr.writeheader(); wr.writerows(filas)
    escribir_html(salida, visual, filas)
    resumen = escribir_resumen(salida, filas, ids, anot, lector)
    if lector and lector.abortado:
        aviso = f"\n\n**ATENCIÓN:** la fase remota se detuvo antes de terminar: {lector.abortado}.\n"
        resumen += aviso
        with open(salida / "resumen.md", "a", encoding="utf-8") as fh:
            fh.write(aviso)
    sys.stdout.reconfigure(encoding="utf-8")
    print(resumen)


# ----------------------------------------------------------------------------- informes
def escribir_html(salida, visual, filas):
    idx = {(f["capture_id"], f["origen"], f["variante"]): f for f in filas}
    rows = []
    for v in visual:
        cid = v["cid"]
        celdas = [f"<td><b>{cid}</b><br><small>{v['grupo']}</small><br>"
                  f"<img src='vistas/{cid}_original_marcado.jpg' width=220></td>"]
        for origen in ORIGENES:
            o = v["origenes"][origen]
            for var in VARIANTES:
                f = idx[(cid, origen, var)]
                tag = " ★" if var == o["elegida"] else ""
                img = (f"<img src='vistas/{cid}_{origen}_{var}.jpg' width=200>" if f["dims_enviada"] != "no generada"
                       else "<div class=na>sin recorte</div>")
                celdas.append(f"<td>{img}<br><small>{origen}·{var}{tag} {f['dims_enviada']} · dígitos "
                              f"{f['alto_digitos_px_enviado']}px · ~{f['tokens_imagen_est']} tok<br>"
                              f"lectura: {f['precio_leido']} ({f['estado_lectura']})</small></td>")
            celdas.append(f"<td><small>selector {origen}: <b>{o['elegida']}</b><br>{o['motivo']}</small></td>")
        rows.append("<tr>" + "".join(celdas) + "</tr>")
    head = ("<tr><th>original (gris: candidatas, verde: recorte)</th>"
            + "".join(f"<th>{o} · {v}</th>" for o in ORIGENES for v in list(VARIANTES) + ["selector"]) + "</tr>")
    html = f"""<!doctype html><html lang=es><meta charset=utf-8><title>Piloto etiquetas</title>
<style>body{{font-family:system-ui;background:#fff;color:#111}}td{{vertical-align:top;border-bottom:1px solid #ddd;padding:4px}}
img{{border:1px solid #ccc}}.na{{width:200px;height:120px;background:#eee;display:grid;place-items:center}}th{{position:sticky;top:0;background:#f4f4f4}}</style>
<h1>Piloto de recuperación de etiquetas · comparación visual (local)</h1>
<p>★ = vista elegida por el selector operativo antes de llamar al modelo. Archivo local: no publicar (contiene fotos).</p>
<table>{head}{''.join(rows)}</table></html>"""
    (salida / "comparacion_visual.html").write_text(html, encoding="utf-8")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def escribir_resumen(salida, filas, ids, anot, lector):
    n = len(ids)
    L = ["# Resumen del piloto (generado)", "",
         f"Muestra de desarrollo: {n} capturas. Referencia del equipo: commit `{REF_COMMIT[:7]}`.", ""]
    for origen in ORIGENES:
        F = [f for f in filas if f["origen"] == origen]
        sel = [f for f in F if f["variante"].startswith("SEL")]
        con_rec = sum(1 for f in F if f["variante"] == "B" and f["dims_enviada"] != "no generada")
        motivos = {}
        for f in sel:
            motivos[f["motivo_selector"]] = motivos.get(f["motivo_selector"], 0) + 1
        elig = {v: sum(1 for f in sel if f["variante"] == f"SEL->{v}") for v in VARIANTES}
        ganancia = []
        for cid in ids:
            a = next(f for f in F if f["capture_id"] == cid and f["variante"] == "A")
            s = next(f for f in sel if f["capture_id"] == cid)
            if a["alto_digitos_px_enviado"] and s["alto_digitos_px_enviado"]:
                ganancia.append(s["alto_digitos_px_enviado"] / a["alto_digitos_px_enviado"])
        tokA = sum(f["tokens_imagen_est"] for f in F if f["variante"] == "A")
        tokS = sum(f["tokens_imagen_est"] or 0 for f in sel)
        L += [f"## Origen: {origen}", "",
              f"- Recorte generado (B/C disponibles): {con_rec}/{n}",
              f"- Selector eligió A/B/C: {elig['A']}/{elig['B']}/{elig['C']} de {n}; motivos: "
              + ", ".join(f"{k}={v}" for k, v in sorted(motivos.items())),
              f"- Alto de dígitos enviado (mediana px) A: {_med(f['alto_digitos_px_enviado'] for f in F if f['variante']=='A')}"
              f" · B: {_med(f['alto_digitos_px_enviado'] for f in F if f['variante']=='B')}"
              f" · selector: {_med(f['alto_digitos_px_enviado'] for f in sel)}",
              f"- Ampliación de dígitos selector/A (mediana, {len(ganancia)} capturas con dígitos en ambas): {_med(ganancia)}x",
              f"- Tokens de imagen estimados (foto de anaquel, suma): A={tokA} · selector={tokS}; llamadas por captura "
              "en operación: 1 en ambos (más la foto de producto, constante)", ""]
        L += ["| Vista | correctas | incorrectas | indeterminadas | sin medir | denominador |", "|---|---|---|---|---|---|"]
        for v in list(VARIANTES) + ["SEL"]:
            G = [f for f in F if f["variante"].startswith(v)]
            cnt = {k: sum(1 for f in G if f["resultado_vs_anotacion"] == k)
                   for k in ("correcta", "incorrecta", "indeterminada")}
            sm = len(G) - sum(cnt.values())
            L.append(f"| {v} | {cnt['correcta']} | {cnt['incorrecta']} | {cnt['indeterminada']} | {sm} | {len(G)} |")
        L.append("")
        # Estado de lectura sin anotación: útil aunque falte la evaluación humana.
        L += ["Estado de lectura del modelo (no requiere anotación):", "",
              "| Vista | legible con precio | indeterminada | asociación ambigua | JSON inválido | rechazo | error | "
              "sin medir / sin recorte | mismo precio que A* | latencia mediana ms | tokens entrada mediana |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        lecA = {f["capture_id"]: f for f in F if f["variante"] == "A"}
        for v in list(VARIANTES) + ["SEL"]:
            G = [f for f in F if f["variante"].startswith(v)]
            leg = [f for f in G if f["estado_lectura"] == "legible" and _num(f["precio_leido"]) is not None]
            est = lambda e: sum(1 for f in G if f["estado_lectura"] == e)
            otros = len(G) - len(leg) - sum(est(e) for e in ("indeterminada", "asociacion_ambigua", "json_invalido",
                                                              "rechazo_modelo", "error_llamada"))
            ambas = [f for f in leg if lecA[f["capture_id"]]["estado_lectura"] == "legible"
                     and _num(lecA[f["capture_id"]]["precio_leido"]) is not None]
            igual = sum(1 for f in ambas if abs(_num(f["precio_leido"]) - _num(lecA[f["capture_id"]]["precio_leido"])) < 0.005)
            lat = _med(f["latencia_modelo_ms"] for f in G if isinstance(f["latencia_modelo_ms"], (int, float)))
            tok = _med(f["tokens_entrada"] for f in G if isinstance(f["tokens_entrada"], (int, float)))
            lat, tok = (SIN_MEDIR if lat is None else lat), (SIN_MEDIR if tok is None else tok)
            L.append(f"| {v} | {len(leg)} | {est('indeterminada')} | {est('asociacion_ambigua')} | {est('json_invalido')} | "
                     f"{est('rechazo_modelo')} | {est('error_llamada')} | {otros} | {igual}/{len(ambas)} | {lat} | {tok} |")
        L += ["", "*Entre capturas donde ambas vistas dieron precio. Coincidir con A no prueba que sea correcto.", ""]
    # Discrepancias: dónde las vistas no coinciden. Son las primeras capturas a revisar a mano.
    disc = []
    for cid in ids:
        for origen in ORIGENES:
            fila = {f["variante"]: f for f in filas if f["capture_id"] == cid and f["origen"] == origen}
            sel = next(f for k, f in fila.items() if k.startswith("SEL"))
            precios = {v: (_num(fila[v]["precio_leido"]) if fila[v]["estado_lectura"] == "legible" else None)
                       for v in VARIANTES}
            medidas = [v for v in VARIANTES if fila[v]["estado_lectura"] not in (SIN_MEDIR, "no_aplica (sin recorte)")]
            distintos = {p for v, p in precios.items() if v in medidas and p is not None}
            if len(medidas) > 1 and (len(distintos) > 1 or (distintos and any(precios[v] is None for v in medidas))):
                fmt = lambda v: (f"{precios[v]:g}" if precios[v] is not None else fila[v]["estado_lectura"])
                disc.append(f"| {cid} | {origen} | {fmt('A')} | {fmt('B')} | {fmt('C')} | {sel['variante']} |")
    if disc:
        L += ["## Discrepancias entre vistas (revisar primero)", "",
              "| Captura | Origen | A | B | C | Selector |", "|---|---|---|---|---|---|"] + disc + [""]
    llam = sum(f["llamadas"] for f in filas if not f["variante"].startswith("SEL"))
    L += [f"Llamadas remotas en esta ejecución: {llam}" + ("" if lector else " (modo local; sin consumo de tokens)."),
          f"Anotaciones humanas cargadas: {len(anot)}/{n}" + ("" if anot else
          " → lecturas correctas/incorrectas/indeterminadas: **sin medir** (llenar plantilla_anotaciones.csv y "
          "guardarla como anotaciones_dev.csv)."), ""]
    txt = "\n".join(L)
    (salida / "resumen.md").write_text(txt, encoding="utf-8")
    return txt


if __name__ == "__main__":
    main()
