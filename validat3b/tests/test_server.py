"""Prueba de la API sin llamar a Foundry (client=None): python tests/test_server.py"""
import base64
import io
import json
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

import server  # noqa: E402
from engine import auto, output  # noqa: E402
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


def raw(port, path, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    server.Handler.client = None
    server.Handler.token = None
    server.Handler.jwt_secret = None
    server.Handler.catalog = {}
    tmp = Path(tempfile.mkdtemp())  # no ensuciar salida_api con fotos y JSON de prueba
    server.Handler.img_dir, server.Handler.json_dir = tmp / "imagenes", tmp / "json"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    img = jpeg_b64()
    ok = {"capture_store_name": "Soriana", "capture_barcode": "7501", "capture_price": "10.5",
          "facade_b64": img, "product_b64": img, "shelf_b64": img}

    assert call(port, "/health") == (200, {"status": "ok", "llm": False})
    assert call(port, "/nada")[0] == 404

    code, res = call(port, "/validar", ok)
    assert code == 200 and output.validate(auto.oficial(res)) == [], res
    # registro con la forma de capturas.json, en el mismo orden, y el detalle del motor al final
    assert list(res)[:len(auto.REGISTRO)] == list(auto.REGISTRO), list(res)
    assert res["decision_esperada"] == "revision_manual" and res["reason_code"] == "SIN_ANALISIS_VISUAL"
    assert res["motivo_rechazo"] == "" and res["capture_barcode"] == 7501 and res["capture_price"] == 10.5
    assert res["capture_id"].startswith("APP-") and res["capture_store_name"] == "Soriana"

    code, res = call(port, "/validar", dict(ok, capture_id="CAP-1"))
    assert res["capture_id"] == "CAP-1"
    # el registro queda guardado en disco tal como se devolvió
    assert json.loads((server.Handler.json_dir / "CAP-1.json").read_text(encoding="utf-8")) == res
    # las fotos quedan guardadas y se sirven en la URL del registro
    assert res["facade_file"] == "imagenes/CAP-1_facade.jpg"
    assert res["shelf_url"] == f"http://127.0.0.1:{port}/imagenes/CAP-1_shelf.jpg", res["shelf_url"]
    assert raw(port, "/imagenes/CAP-1_product.jpg") == (200, base64.b64decode(img))
    assert raw(port, "/imagenes/NO-EXISTE_product.jpg")[0] == 404
    assert raw(port, "/imagenes/../server.py")[0] == 404 and raw(port, "/imagenes/CAP-1_otra.jpg")[0] == 404
    # detrás de Cloudflare la URL sale con https y el dominio público
    code, res = call(port, "/validar", dict(ok, capture_id="CAP-2"), {"Host": "api.jamp.digital", "X-Forwarded-Proto": "https"})
    assert res["facade_url"] == "https://api.jamp.digital/imagenes/CAP-2_facade.jpg"

    # entradas inválidas -> 400, nunca 500
    assert call(port, "/validar", {k: v for k, v in ok.items() if k != "shelf_b64"})[0] == 400
    assert call(port, "/validar", dict(ok, product_b64="no es base64!!"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_price="abc"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_id="../x"))[0] == 400
    assert call(port, "/validar", dict(ok, capture_store_name=""))[0] == 400
    assert call(port, "/validar", [1, 2])[0] == 400

    # imagen corrupta -> registro con ERROR_PROCESAMIENTO, no caída
    code, res = call(port, "/validar", dict(ok, facade_b64=base64.b64encode(b"basura").decode(),
                                              product_b64=base64.b64encode(b"basura").decode()))
    assert code == 200 and res["reason_code"] == "ERROR_PROCESAMIENTO" and output.validate(auto.oficial(res)) == [], res
    assert list(res)[:len(auto.REGISTRO)] == list(auto.REGISTRO) and res["capture_store_name"] == "Soriana"

    # token (también protege las fotos)
    server.Handler.token = "s3cret"
    assert call(port, "/validar", ok)[0] == 401
    assert call(port, "/validar", ok, {"X-Api-Key": "mal"})[0] == 401
    assert call(port, "/validar", ok, {"X-Api-Key": "s3cret"})[0] == 200
    assert raw(port, "/imagenes/CAP-1_product.jpg")[0] == 401
    assert raw(port, "/imagenes/CAP-1_product.jpg", {"X-Api-Key": "s3cret"})[0] == 200
    server.Handler.token = None

    # /analizar: solo fotos; mismo registro. Sin Haiku no inventa datos; lo que manda el usuario aparece tal cual
    solo = {"facade_b64": img, "product_b64": img, "shelf_b64": img}
    code, res = call(port, "/analizar", solo)
    assert code == 200 and list(res)[:len(auto.REGISTRO)] == list(auto.REGISTRO), res
    assert output.validate(auto.oficial(res)) == [] and res["capture_store_name"] is None and res["precio_descuento"] is None
    assert call(port, "/analizar", {k: v for k, v in solo.items() if k != "shelf_b64"})[0] == 400
    code, res = call(port, "/analizar", dict(solo, capture_store_name="Neto", capture_price="14"))
    assert res["capture_store_name"] == "Neto" and res["capture_price"] == 14.0
    code, res = call(port, "/analizar", dict(solo, product_b64=base64.b64encode(b"basura").decode()))
    assert code == 200 and res["reason_code"] == "ERROR_PROCESAMIENTO" and res["decision_esperada"] == "revision_manual"

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
    # Una captura enviada por Android llega al auditor con las fotos originales.
    server.Handler.audit_token = "prueba-portal"
    audit = {"X-Audit-Token": "prueba-portal", "Origin": "http://127.0.0.1:8123"}
    ruta = "/auditoria/capturas"
    assert b"Validat3B" in raw(port, "/portal/?modo=demo")[1]
    assert raw(port, "/portal/assets/logo.png")[0] == 200
    assert raw(port, "/portal/tests/portal_smoke.py")[0] == 404
    assert raw(port, "/portal/imagenes/CAP-1_shelf.jpg")[0] == 404
    assert call(port, ruta)[0] == 401
    assert call(port, ruta, headers={**audit, "Origin": "https://api.jamp.digital"})[0] == 200
    assert call(port, ruta, headers={**audit, "Origin": "https://otro.example"})[0] == 403
    code, bandeja = call(port, ruta, headers=audit)
    assert code == 200
    caso = next(c for c in bandeja["casos"] if c["capture_id"] == "CAP-1")
    assert caso["decision_esperada"] == "revision_manual" and caso["auditoria"] is None
    assert raw(port, "/auditoria/imagenes/CAP-1_shelf.jpg")[0] == 401
    assert raw(port, "/auditoria/imagenes/CAP-1_shelf.jpg", audit) == (200, base64.b64decode(img))
    resolver = ruta + "/CAP-1/resolucion"
    decision = {"estado": "rechazada", "motivo": "Precio no verificable", "nota": "Etiqueta ilegible", "revision": caso["revision"]}
    assert call(port, resolver, {**decision, "revision": "anterior"}, audit)[0] == 409
    assert call(port, resolver, {**decision, "nota": ""}, audit)[0] == 400
    assert call(port, resolver, decision, audit)[0] == 201
    assert call(port, resolver, decision, audit)[0] == 409
    _, bandeja = call(port, ruta, headers=audit)
    caso = next(c for c in bandeja["casos"] if c["capture_id"] == "CAP-1")
    assert caso["auditoria"]["estado"] == "rechazada" and caso["decision_esperada"] == "revision_manual"
    assert "auditoria" not in json.loads((server.Handler.json_dir / "CAP-1.json").read_text(encoding="utf-8"))
    srv.shutdown()
    print("OK")


if __name__ == "__main__":
    main()
