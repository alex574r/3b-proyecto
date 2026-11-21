"""Prueba de la API sin llamar a Foundry (client=None): python tests/test_server.py"""
import base64
import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

import server  # noqa: E402
from engine import output  # noqa: E402
from test_auto import jwt  # noqa: E402


def jpeg_b64():
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), (120, 130, 140)).save(buf, "JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def call(port, path, body=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {},
                                 data=None if body is None else json.dumps(body).encode(),
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main():
    server.Handler.client = None
    server.Handler.token = None
    server.Handler.jwt_secret = None
    server.Handler.catalog = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    img = jpeg_b64()
    ok = {"capture_store_name": "Soriana", "capture_barcode": "7501", "capture_price": "10.5",
          "facade_b64": img, "product_b64": img, "shelf_b64": img}

    assert call(port, "/health") == (200, {"status": "ok", "llm": False})
    assert call(port, "/nada")[0] == 404

    code, res = call(port, "/validar", ok)
    assert code == 200 and output.validate(res) == [], res
    assert res["decision"] == "revision_manual" and res["reason_code"] == "SIN_ANALISIS_VISUAL"
    assert res["capture_id"].startswith("APP-")

    code, res = call(port, "/validar", dict(ok, capture_id="CAP-1"))
    assert res["capture_id"] == "CAP-1"

    # entradas inválidas -> 400, nunca 500
    assert call(port, "/validar", {k: v for k, v in ok.items() if k != "shelf_b64"})[0] == 400
    assert call(port, "/validar", dict(ok, product_b64="no es base64!!"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_price="abc"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_id="../x"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_store_name=""))[0] == 400
    assert call(port, "/validar", [1, 2])[0] == 400

    # imagen corrupta -> JSON oficial de error, no caída
    code, res = call(port, "/validar", dict(ok, facade_b64=base64.b64encode(b"basura").decode(),
                                              product_b64=base64.b64encode(b"basura").decode()))
    assert code == 200 and res["reason_code"] == "ERROR_PROCESAMIENTO" and output.validate(res) == [], res

    # token
    server.Handler.token = "s3cret"
    assert call(port, "/validar", ok)[0] == 401
    assert call(port, "/validar", ok, {"X-Api-Key": "mal"})[0] == 401
    assert call(port, "/validar", ok, {"X-Api-Key": "s3cret"})[0] == 200
    server.Handler.token = None

    # /analizar: solo fotos; sin Haiku no inventa datos, y lo que manda el usuario aparece en datos_detectados
    solo = {"facade_b64": img, "product_b64": img, "shelf_b64": img}
    code, res = call(port, "/analizar", solo)
    assert code == 200 and set(res) == {"resultado", "datos_detectados"}, res
    assert output.validate(res["resultado"]) == [] and res["datos_detectados"]["capture_store_name"] is None
    assert res["resultado"]["precio_descuento"] is None and "precio_descuento" in res["datos_detectados"]
    assert call(port, "/analizar", {k: v for k, v in solo.items() if k != "shelf_b64"})[0] == 400
    code, res = call(port, "/analizar", dict(solo, capture_store_name="Neto", capture_price="14"))
    assert res["datos_detectados"]["capture_store_name"] == "Neto" and res["datos_detectados"]["capture_price"] == 14.0
    code, res = call(port, "/analizar", dict(solo, product_b64=base64.b64encode(b"basura").decode()))
    assert code == 200 and res["resultado"]["reason_code"] == "ERROR_PROCESAMIENTO" and res["datos_detectados"] == {}

    # JWT (y el token fijo sigue valiendo si ambos están configurados)
    server.Handler.jwt_secret = "clave-jwt"
    now = int(time.time())
    assert call(port, "/analizar", solo)[0] == 401
    assert call(port, "/analizar", solo, {"Authorization": "Bearer " + jwt("clave-jwt", now + 300)})[0] == 200
    assert call(port, "/analizar", solo, {"Authorization": "Bearer " + jwt("otra", now + 300)})[0] == 401
    assert call(port, "/analizar", solo, {"Authorization": "Bearer " + jwt("clave-jwt", now - 600)})[0] == 401
    assert call(port, "/validar", ok, {"Authorization": "Bearer " + jwt("clave-jwt", now + 300)})[0] == 200
    assert call(port, "/health")[0] == 200  # health nunca pide auth
    server.Handler.token = "s3cret"
    assert call(port, "/validar", ok, {"X-Api-Key": "s3cret"})[0] == 200
    srv.shutdown()
    print("OK")


if __name__ == "__main__":
    main()
