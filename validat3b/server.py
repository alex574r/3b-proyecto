"""API HTTP del motor: python server.py [--host 127.0.0.1] [--port 8000] [--no-llm]

GET  /health
POST /validar   JSON: campos de capturas.json (capture_store_name, capture_barcode, capture_price, capture_brand,
                product_name, unit_product, unit_quantity_product, capture_id opcional)
                + facade_b64, product_b64, shelf_b64 (JPEG en base64)
                -> JSON oficial de la captura (siempre válido; ante error interno, revision_manual).
Auth opcional: si VALIDAT3B_TOKEN está definido, se exige el header X-Api-Key con ese valor.
La llave de Foundry vive solo aquí (FOUNDRY_API_KEY); la app nunca la ve.
"""
import argparse
import base64
import hmac
import json
import os
import re
import sys
import tempfile
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from engine import decide, output, vision
from engine.data import normalize
from engine.local_checks import analyze

MAX_BODY = 40 * 1024 * 1024
PHOTOS = ("facade", "product", "shelf")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def parse(body):
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
    if not isinstance(cap.get("capture_store_name"), str) or not cap["capture_store_name"].strip():
        raise ValueError("falta capture_store_name")
    return normalize(cap), photos


def run_capture(cap, photos, client, usage_log):
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for k, data in photos.items():
            paths[k] = Path(d) / f"{k}.jpg"
            paths[k].write_bytes(data)
        local = analyze(paths)
        vis = None if client is None else vision.extract(cap, paths, client, usage_log)
    return decide.decide(cap, local, vis)


class Handler(BaseHTTPRequestHandler):
    client = None
    token = os.environ.get("VALIDAT3B_TOKEN")
    usage_log = Path("salida_api") / "usage.jsonl"

    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "llm": self.client is not None})
        else:
            self._send(404, {"error": "no encontrado"})

    def do_POST(self):
        if self.path != "/validar":
            return self._send(404, {"error": "no encontrado"})
        if self.token and not hmac.compare_digest(self.headers.get("X-Api-Key", "").encode(), self.token.encode()):
            return self._send(401, {"error": "token inválido"})
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, {"error": "falta Content-Length"})
        if not 0 < n <= MAX_BODY:
            return self._send(413, {"error": f"cuerpo fuera de rango (máx. {MAX_BODY} bytes)"})
        try:
            cap, photos = parse(json.loads(self.rfile.read(n)))
        except ValueError as e:  # incluye JSONDecodeError y base64 inválido
            return self._send(400, {"error": str(e)})
        try:
            res = run_capture(cap, photos, self.client, self.usage_log)
            errs = output.validate(res)
            if errs:
                raise ValueError(f"salida inválida: {errs}")
        except Exception as e:  # noqa: BLE001 - nunca devolver algo que no sea el JSON oficial
            res = output.fallback(cap["capture_id"], f"{type(e).__name__}: {e}")
        self._send(200, res)


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
    Handler.usage_log.parent.mkdir(exist_ok=True)
    print(f"API en http://{args.host}:{args.port}  llm={'no' if args.no_llm else 'sí'}  "
          f"token={'sí' if Handler.token else 'no'}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
