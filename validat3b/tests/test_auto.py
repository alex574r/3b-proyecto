"""Modo automático y JWT, sin red: python tests/test_auto.py"""
import base64
import hashlib
import hmac
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import auto, output  # noqa: E402
from server import verify_jwt  # noqa: E402

LOCAL = {"blur": {"product": 600.0, "shelf": 500.0}, "moire": {"product": 30, "shelf": 30}, "barcodes": []}
CRIT = {k: "ok" for k in ("fachada", "pantalla", "nitidez", "cercania", "producto", "etiqueta", "precio")}
VIS = {"criterios": CRIT, "cadena_visible": "Neto", "precio_etiqueta": 14.0, "motivo": "",
       "datos": {"marca": "Cat-tit", "producto": "Arena sanitaria gato", "contenido": 2000, "unidad": "gramo",
                 "codigo_barras": "763331024755"}}


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def jwt(secret, exp, alg="HS256"):
    h, p = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode()), b64(json.dumps({"exp": exp}).encode())
    return f"{h}.{p}.{b64(hmac.new(secret.encode(), f'{h}.{p}'.encode(), hashlib.sha256).digest())}"


def main():
    cat_file = Path(tempfile.mkdtemp()) / "cat.csv"
    cat_file.write_text("id_product,product_name,product_barcode,product_price,min_product_price,max_product_price,"
                        "unit_product,unit_quantity_product,product_group,product_line\n"
                        "5055,Arena para gato,0763331024755,14.0,0.0,28.0,gramo,2000.0,(29) Pets,(04) Accesorios\n",
                        encoding="utf-8")
    catalog = auto.load_catalog(cat_file)
    assert auto.load_catalog(cat_file.parent / "no_existe.csv") == {}

    cap = {"capture_id": "APP-1", "capture_barcode": None, "capture_price": None}
    # todo se completa desde las fotos; el nombre sale del catálogo porque el código de Haiku está en él
    res, d = auto.completar(cap, LOCAL, VIS, catalog)
    assert output.validate(res) == []
    assert d["capture_store_name"] == "Neto" and d["capture_price"] == 14.0 and d["capture_brand"] == "Cat-tit"
    assert d["capture_barcode"] == "763331024755" and d["product_name"] == "Arena para gato"
    assert d["fuente_producto"] == "catalogo" and d["unit_quantity_product"] == 2000.0 and d["unit_product"] == "gramo"
    # todos los datos quedan rellenos (fotos + catálogo) y las fotos son nítidas y cercanas: se aprueba por datos completos
    assert res["decision"] == "aprobada" and res["reason_code"] == "APROBADA"
    # misma estructura que un registro de capturas.json, con el SKU completado desde el catálogo
    assert list(d) == ["capture_id", "capture_store_name", "capture_date", "capture_barcode", "capture_price",
                       "capture_brand", "id_product", "product_name", "product_barcode", "product_price",
                       "min_product_price", "max_product_price", "unit_product", "unit_quantity_product",
                       "product_group", "product_line", "precio_descuento", "fuente_producto", "fuente_catalogo"]
    assert d["capture_id"] == "APP-1" and d["id_product"] == 5055 and d["product_barcode"] == "0763331024755"
    assert (d["product_price"], d["min_product_price"], d["max_product_price"]) == (14.0, 0.0, 28.0)
    assert d["product_group"] == "(29) Pets" and d["product_line"] == "(04) Accesorios"
    assert len(d["capture_date"]) == 19 and d["precio_descuento"] is None
    assert auto.completar(dict(cap, capture_date="2026-11-19 10:26:48"), LOCAL, VIS, catalog)[1]["capture_date"] == "2026-11-19 10:26:48"
    # precio de descuento: se valida contra el rango del catálogo (máx. 28) y viaja igual en resultado y datos
    res, d = auto.completar(cap, LOCAL, dict(VIS, precio_descuento=12.0), catalog)
    assert res["precio_descuento"] == d["precio_descuento"] == 12.0
    res, d = auto.completar(dict(cap, capture_price=30.0), LOCAL, dict(VIS, precio_etiqueta=40.0, precio_descuento=30.0), catalog)
    # un descuento inválido se descarta (null); con datos completos la captura igual se aprueba
    assert res["precio_descuento"] is None and d["precio_descuento"] is None and res["decision"] == "aprobada"
    # registro de respuesta: llaves y orden de capturas.json, códigos como número, detalle del motor al final
    res, d = auto.completar(cap, LOCAL, VIS, catalog)
    fotos = {k: (f"imagenes/APP-1_{k}.jpg", f"https://x/imagenes/APP-1_{k}.jpg") for k in ("facade", "product", "shelf")}
    r = auto.registro(d, res, fotos)
    assert list(r)[:len(auto.REGISTRO)] == list(auto.REGISTRO) and list(r)[-2:] == ["fuente_producto", "fuente_catalogo"] and r["fuente_catalogo"] == "codigo_barras"
    assert r["capture_barcode"] == 763331024755 and r["product_barcode"] == 763331024755 and r["id_product"] == 5055
    assert r["facade_file"] == "imagenes/APP-1_facade.jpg" and r["shelf_url"] == "https://x/imagenes/APP-1_shelf.jpg"
    assert r["decision_esperada"] == res["decision"] and r["motivo_rechazo"] == ""
    assert output.validate(auto.oficial(r)) == [] and auto.oficial(r)["decision"] == res["decision"]
    res, d = auto.completar(cap, LOCAL, dict(VIS, criterios=dict(CRIT, cercania="falla")), catalog)
    r = auto.registro(d, res, {})
    assert r["decision_esperada"] == "rechazada" and r["motivo_rechazo"] == "Capturas lejanas" and r["facade_url"] is None
    r = auto.registro(auto.detectar({"capture_id": "X"}, [], None, {}), output.fallback("X", "error"), {})
    assert r["capture_barcode"] is None and r["reason_code"] == "ERROR_PROCESAMIENTO" and output.validate(auto.oficial(r)) == []

    # sin catálogo, los campos del SKU quedan en null
    _, d = auto.completar(cap, LOCAL, VIS, {})
    assert d["id_product"] is None and d["product_price"] is None and d["product_group"] is None

    # sin catálogo: el nombre sale de la foto; código leído localmente tiene prioridad sobre el de Haiku
    res, d = auto.completar(cap, dict(LOCAL, barcodes=["7506233812418"]), VIS, {})
    assert d["product_name"] == "Arena sanitaria gato" and d["fuente_producto"] == "foto"
    assert d["capture_barcode"] == "7506233812418"

    # varios códigos en las fotos: gana el que está en el catálogo aunque el local sea otro (el de la caja)
    res, d = auto.completar(cap, dict(LOCAL, barcodes=["0738545010740"]), VIS, catalog)
    assert d["capture_barcode"] == "763331024755" and d["product_name"] == "Arena para gato"
    # el JSON reporta el código elegido (no el de la caja) y no marca falla por los otros códigos
    assert res["codigo_barras_detectado"] == "763331024755" and res["validaciones"]["codigo_barras"] == "ok"
    # código escrito por el usuario que ninguna foto decodifica: no_evaluable, sin inventar "detectado"
    res, d = auto.completar(dict(cap, capture_barcode="763331024755"), dict(LOCAL, barcodes=["0738545010740"]), VIS, catalog)
    assert res["validaciones"]["codigo_barras"] == "no_evaluable" and res["codigo_barras_detectado"] is None
    # código escrito por el usuario que sí se decodifica: ok
    res, d = auto.completar(dict(cap, capture_barcode="763331024755"), dict(LOCAL, barcodes=["763331024755"]), VIS, catalog)
    assert res["validaciones"]["codigo_barras"] == "ok"

    # lo que escribió el usuario manda; un precio distinto al de la etiqueta impide el candidato
    res, d = auto.completar(dict(cap, capture_price=20.0, product_name="Otro", capture_store_name="Soriana"), LOCAL, VIS, catalog)
    assert d["capture_price"] == 20.0 and d["product_name"] == "Otro" and d["fuente_producto"] == "usuario"
    # el precio escrito difiere del de la etiqueta: se reporta como falla, pero con datos completos no bloquea la aprobación
    assert res["decision"] == "aprobada" and res["validaciones"]["evidencia_precio"] == "falla"

    # una falla de calidad firme se rechaza igual que en /validar
    bad = dict(VIS, criterios=dict(CRIT, pantalla="falla"))
    assert auto.completar(cap, LOCAL, bad, catalog)[0]["reason_code"] == "FOTO_DE_PANTALLA"

    # sin análisis visual: sin datos inventados, a revisión manual
    res, d = auto.completar(cap, LOCAL, None, catalog)
    assert res["reason_code"] == "SIN_ANALISIS_VISUAL" and d["product_name"] is None and d["capture_barcode"] is None
    assert auto.completar(cap, LOCAL, {}, catalog)[0]["reason_code"] == "SIN_ANALISIS_VISUAL"

    # códigos de longitud imposible se ignoran
    _, d = auto.completar(cap, LOCAL, dict(VIS, datos=dict(VIS["datos"], codigo_barras="12345")), {})
    assert d["capture_barcode"] is None

    # JWT
    now, s = 1_000_000, "secreto"
    assert verify_jwt(jwt(s, now + 300), s, now)
    assert not verify_jwt(jwt(s, now + 300), "otro", now)             # firma incorrecta
    assert not verify_jwt(jwt(s, now - 600), s, now)                  # vencido
    assert not verify_jwt(jwt(s, now + 100_000), s, now)              # vida demasiado larga
    assert not verify_jwt(jwt(s, now + 300, alg="none"), s, now)      # alg distinto
    assert not verify_jwt("basura", s, now) and not verify_jwt("a.b.c", s, now) and not verify_jwt("", s, now)
    assert not verify_jwt(jwt(s, "mañana"), s, now)                   # exp no numérico
    print("OK")


if __name__ == "__main__":
    main()
