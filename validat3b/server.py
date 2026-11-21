"""API HTTP del motor: python server.py [--host 127.0.0.1] [--port 8000] [--no-llm]

GET  /health
GET  /imagenes/<capture_id>_<facade|product|shelf>.jpg   fotos guardadas (misma autenticación que los POST)
POST /validar   JSON: campos de capturas.json (capture_store_name, capture_barcode, capture_price, capture_brand,
                product_name, unit_product, unit_quantity_product, capture_id opcional)
                + facade_b64, product_b64, shelf_b64 (JPEG en base64)
POST /analizar  Solo las 3 fotos son obligatorias; todos los demás campos son opcionales y, si vienen, mandan.
Ambos POST -> un registro con la forma de capturas.json (capture_id ... decision_esperada, motivo_rechazo) y después el
detalle del motor (precio_descuento, confidence_score, reason_code, validaciones, explicacion...). Siempre 200 con
registro válido; ante error interno, revision_manual / ERROR_PROCESAMIENTO. Dentro del proyecto quedan las fotos en
salida_api/imagenes/ y cada registro en salida_api/json/<capture_id>.json.
Auth (si hay VALIDAT3B_TOKEN o VALIDAT3B_JWT_SECRET definidos; si no, abierto): header X-Api-Key con el token fijo,
o Authorization: Bearer <JWT HS256 firmado con VALIDAT3B_JWT_SECRET, con exp a lo sumo 15 min adelante>.
La llave de Foundry vive solo aquí (FOUNDRY_API_KEY); la app nunca la ve.
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import auto, decide, output, vision
from engine.data import normalize
from engine.local_checks import analyze

MAX_BODY = 40 * 1024 * 1024
PHOTOS = ("facade", "product", "shelf")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
IMG_RE = re.compile(r"^/imagenes/([A-Za-z0-9_-]{1,64}_(?:facade|product|shelf)\.jpg)$")
SALIDA = Path(__file__).resolve().parent / "salida_api"  # dentro del proyecto, no depende de dónde se lance
HOST_RE = re.compile(r"^[A-Za-z0-9.:-]{1,255}$")
CATALOGO = Path(os.environ.get("VALIDAT3B_CATALOGO") or
                Path(__file__).resolve().parent.parent / "Validat3B_desarrollo_metadatos" / "catalogo_productos.csv")


def parse(body, require_store=True):
    """Valida el JSON de entrada. Devuelve (captura, {foto: bytes}); lanza ValueError si es inválido."""
    if not isinstance(body, dict):
        raise ValueError("el cuerpo debe ser un objeto JSON")
    photos = {}
    for k in PHOTOS:
        b64 = body.get(f"{k}_b64")
        if not isinstance(b64, str) or not b64:
            raise ValueError(f"falta {k}_b64")
        photos[k] = base64.b64decode(b64, validate=True)
    cap = {k: v for k, v in body.items() if not k.endswith("_b64")}
    cid = cap.get("capture_id") or f"APP-{uuid.uuid4().hex[:8]}"
    if not isinstance(cid, str) or not ID_RE.match(cid):
        raise ValueError("capture_id inválido (solo letras, números, - y _; máx. 64)")
    cap["capture_id"] = cid
    if require_store and (not isinstance(cap.get("capture_store_name"), str) or not cap["capture_store_name"].strip()):
        raise ValueError("falta capture_store_name")
    return normalize(cap), photos


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_jwt(token, secret, now=None, leeway=30, max_ttl=900):
    """JWT HS256 válido: firma correcta y exp entre ahora y ahora+max_ttl (rechaza alg distinto y tokens eternos)."""
    try:
        h, p, s = token.split(".")
        if json.loads(_b64d(h)).get("alg") != "HS256":
            return False
        want = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _b64d(s)):
            return False
        exp, now = json.loads(_b64d(p))["exp"], time.time() if now is None else now
        return isinstance(exp, (int, float)) and now - leeway <= exp <= now + max_ttl + leeway
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def guardar_fotos(cid, photos, img_dir):
    """Guarda las 3 fotos como <capture_id>_<foto>.jpg (un capture_id repetido las reemplaza)."""
    img_dir.mkdir(parents=True, exist_ok=True)
    paths = {k: img_dir / f"{cid}_{k}.jpg" for k in photos}
    for k, data in photos.items():
        paths[k].write_bytes(data)
    return paths


def run_capture(cap, paths, client, usage_log, catalog):
    """/validar: compara contra los datos esperados que mandó el cliente. -> (resultado oficial, datos)."""
    local = analyze(paths)
    vis = None if client is None else vision.extract(cap, paths, client, usage_log)
    datos = auto.detectar(cap, local["barcodes"], vis, catalog)
    # el rango del catálogo valida el precio de descuento, salvo que el cliente mande el suyo
    rango = {"min_product_price": datos["min_product_price"], "max_product_price": datos["max_product_price"]}
    res = decide.decide({**rango, **cap}, local, vis)
    datos["precio_descuento"] = res["precio_descuento"]
    return res, datos


def run_analizar(cap, paths, client, usage_log, catalog):
    local = analyze(paths)
    vis = None if client is None else vision.extract(cap, paths, client, usage_log, auto=True)
    return auto.completar(cap, local, vis, catalog)


class Handler(BaseHTTPRequestHandler):
    client = None
    token = os.environ.get("VALIDAT3B_TOKEN")
    jwt_secret = os.environ.get("VALIDAT3B_JWT_SECRET")
    catalog = {}
    usage_log = SALIDA / "usage.jsonl"
    img_dir = SALIDA / "imagenes"
    json_dir = SALIDA / "json"

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        if not (self.token or self.jwt_secret):
            return True
        key = self.headers.get("X-Api-Key", "")
        if self.token and hmac.compare_digest(key.encode(), self.token.encode()):
            return True
        bearer = self.headers.get("Authorization", "")
        return bool(self.jwt_secret and bearer.startswith("Bearer ") and verify_jwt(bearer[7:], self.jwt_secret))

    def _base_url(self):
        """URL pública con la que llegó la petición (detrás de Cloudflare: https://api.jamp.digital)."""
        proto = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        host = self.headers.get("Host", "")
        return f"{proto}://{host if HOST_RE.match(host) else 'localhost'}"

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok", "llm": self.client is not None})
        m = IMG_RE.match(self.path)
        if not m:
            return self._send(404, {"error": "no encontrado"})
        if not self._authorized():
            return self._send(401, {"error": "token inválido"})
        f = self.img_dir / m.group(1)
        if not f.is_file():
            return self._send(404, {"error": "no encontrado"})
        data = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")  # el contenido lo subió un cliente: que no se interprete
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        modo_auto = {"/validar": False, "/analizar": True}.get(self.path)
        if modo_auto is None:
            return self._send(404, {"error": "no encontrado"})
        if not self._authorized():
            return self._send(401, {"error": "token inválido"})
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, {"error": "falta Content-Length"})
        if not 0 < n <= MAX_BODY:
            return self._send(413, {"error": f"cuerpo fuera de rango (máx. {MAX_BODY} bytes)"})
        try:
            cap, photos = parse(json.loads(self.rfile.read(n)), require_store=not modo_auto)
        except ValueError as e:  # incluye JSONDecodeError y base64 inválido
            return self._send(400, {"error": str(e)})
        cid, base = cap["capture_id"], self._base_url()
        fotos = {k: (f"imagenes/{cid}_{k}.jpg", f"{base}/imagenes/{cid}_{k}.jpg") for k in PHOTOS}
        guardadas = False
        try:
            paths = guardar_fotos(cid, photos, self.img_dir)
            guardadas = True
            res, datos = (run_analizar if modo_auto else run_capture)(cap, paths, self.client, self.usage_log, self.catalog)
            errs = output.validate(res)
            if errs:
                raise ValueError(f"salida inválida: {errs}")
        except Exception as e:  # noqa: BLE001 - nunca devolver algo que no sea un registro válido
            res = output.fallback(cid, f"{type(e).__name__}: {e}")
            datos = auto.detectar(cap, [], None, self.catalog)
            fotos = fotos if guardadas else {}
        registro = auto.registro(datos, res, fotos)
        try:  # el registro queda en disco; si falla, la respuesta al cliente no debe fallar
            self.json_dir.mkdir(parents=True, exist_ok=True)
            (self.json_dir / f"{cid}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            print(f"No se pudo guardar el JSON de {cid}: {e}", file=sys.stderr)
        self._send(200, registro)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="usa 0.0.0.0 para que un celular físico llegue por la red local")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-llm", action="store_true", help="solo chequeos locales; no llama al endpoint de Foundry")
    args = ap.parse_args()
    if not args.no_llm:
        if "FOUNDRY_API_KEY" not in os.environ:
            sys.exit("Define FOUNDRY_API_KEY (o usa --no-llm).")
        Handler.client = vision.make_client()
    Handler.usage_log.parent.mkdir(parents=True, exist_ok=True)
    Handler.catalog = auto.load_catalog(CATALOGO)
    print(f"API en http://{args.host}:{args.port}  llm={'no' if args.no_llm else 'sí'}  "
          f"token={'sí' if Handler.token else 'no'}  jwt={'sí' if Handler.jwt_secret else 'no'}  "
          f"catálogo={len(Handler.catalog)} productos")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
