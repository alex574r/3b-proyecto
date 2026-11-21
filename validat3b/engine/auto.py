"""Modo automático (/analizar): completa los datos de la captura desde las fotos y decide con ellos.

Los datos que el usuario sí escribió tienen prioridad. El nombre del producto sale del catálogo si el código de
barras se leyó y está en él; si no, de lo que Haiku lee en el empaque.
"""
import csv
import re
import time
from pathlib import Path

from . import decide

CODE_LENS = (8, 12, 13, 14)  # EAN-8, UPC-A, EAN-13, ITF-14


def _digits(s):
    return re.sub(r"\D", "", str(s or ""))


def _code(s):
    d = _digits(s)
    return d if len(d) in CODE_LENS else None


def _num(x):
    try:
        return None if x in (None, "") or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def load_catalog(path):
    """{código sin ceros a la izquierda: fila del catálogo}. Vacío si el archivo no existe."""
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {_digits(r["product_barcode"]).lstrip("0"): r for r in csv.DictReader(f) if _digits(r.get("product_barcode"))}


def detectar(cap, barcodes, vis, catalog):
    """Datos de la captura con la estructura de capturas.json: lo que escribió el usuario manda; si falta, lo leído en
    las fotos; los datos del SKU salen del catálogo cuando el código está en él."""
    vis = vis or {}
    d = vis.get("datos") or {}
    # Las fotos suelen traer varios códigos (caja, etiqueta, empaque): se prefiere el que está en el catálogo
    cands = [c for c in (*map(_code, barcodes), _code(d.get("codigo_barras"))) if c]
    code = cap.get("capture_barcode") or next((c for c in cands if c.lstrip("0") in catalog), cands[0] if cands else None)
    cat = (catalog.get(code.lstrip("0")) if code else None) or {}
    date = cap.get("capture_date")
    return {
        "capture_id": cap["capture_id"],
        "capture_store_name": cap.get("capture_store_name") or vis.get("cadena_visible"),
        "capture_date": date if isinstance(date, str) and date else time.strftime("%Y-%m-%d %H:%M:%S"),
        "capture_barcode": code,
        "capture_price": cap.get("capture_price") if cap.get("capture_price") is not None else _num(vis.get("precio_etiqueta")),
        "capture_brand": cap.get("capture_brand") or d.get("marca"),
        "id_product": int(_digits(cat.get("id_product"))) if _digits(cat.get("id_product")) else None,
        "product_name": cap.get("product_name") or cat.get("product_name") or d.get("producto"),
        "product_barcode": _digits(cat.get("product_barcode")) or None,
        "product_price": _num(cat.get("product_price")),
        "min_product_price": _num(cat.get("min_product_price")),
        "max_product_price": _num(cat.get("max_product_price")),
        "unit_product": cap.get("unit_product") or cat.get("unit_product") or d.get("unidad"),
        "unit_quantity_product": cap.get("unit_quantity_product") or _num(cat.get("unit_quantity_product")) or _num(d.get("contenido")),
        "product_group": cat.get("product_group"),
        "product_line": cat.get("product_line"),
        "precio_descuento": None,  # se llena con el valor ya validado por decide
        "fuente_producto": ("usuario" if cap.get("product_name") else "catalogo" if cat
                            else "foto" if d.get("producto") else None),
    }


def completar(cap, local, vis, catalog):
    """(resultado oficial, datos detectados). cap trae solo lo que escribió el usuario (todo opcional)."""
    datos = detectar(cap, local["barcodes"], vis, catalog)
    code = datos["capture_barcode"]
    # El rango del catálogo viaja a decide para validar el precio de descuento
    full = dict(cap, capture_store_name=datos["capture_store_name"], capture_barcode=code, capture_price=datos["capture_price"],
                min_product_price=datos["min_product_price"], max_product_price=datos["max_product_price"])
    # Si el código no es uno de los decodificados (p. ej. se leyó del texto impreso o salió del catálogo), el JSON no debe
    # reportar "falla" por los códigos de otras cajas: el elegido por el modo automático cuenta como leído de las fotos,
    # y uno escrito por el usuario que no se pudo decodificar queda "no_evaluable".
    if code and code.lstrip("0") not in {_digits(c).lstrip("0") for c in local["barcodes"]}:
        local = dict(local, barcodes=[] if cap.get("capture_barcode") else [code])
    res = decide.decide(full, local, vis or None, datos)
    datos["precio_descuento"] = res["precio_descuento"]
    return res, datos


# Llaves y orden exactos de un registro de capturas.json; el detalle del motor va después
REGISTRO = ("capture_id", "capture_store_name", "capture_date", "capture_barcode", "capture_price", "capture_brand",
            "id_product", "product_name", "product_barcode", "product_price", "min_product_price", "max_product_price",
            "unit_product", "unit_quantity_product", "product_group", "product_line",
            "facade_file", "facade_url", "product_file", "product_url", "shelf_file", "shelf_url",
            "decision_esperada", "motivo_rechazo")
# Texto de motivo_rechazo como lo registran los analistas en capturas.json (los 3 primeros son literales del set de dev)
MOTIVOS = {
    "IMAGEN_BORROSA": "Capturas borrosas", "CAPTURA_LEJANA": "Capturas lejanas",
    "DESCRIPCION_INCOMPLETA": "Descripción de producto incompleta",
    "FOTO_DE_PANTALLA": "Foto tomada a la pantalla de otro celular",
    "PRODUCTO_NO_COINCIDE": "Producto no coincide con la descripción", "FACHADA_INCORRECTA": "Fachada incorrecta",
    "SIN_ETIQUETA_PRECIO": "No hay etiqueta de precio",
}
OFICIAL = ("confidence_score", "reason_code", "validaciones", "precio_detectado", "precio_descuento",
           "codigo_barras_detectado", "explicacion")


def _int(s):
    d = _digits(s)
    return int(d) if d else None


def registro(datos, res, fotos):
    """Respuesta de la API: registro con la forma de capturas.json + detalle del motor al final.
    fotos: {"facade"|"product"|"shelf": (ruta relativa, url)}. Los códigos de barras van como número, igual que en el set."""
    r = {k: datos.get(k) for k in REGISTRO}
    r["capture_id"] = res["capture_id"]
    r["capture_barcode"], r["product_barcode"] = _int(datos.get("capture_barcode")), _int(datos.get("product_barcode"))
    for k in ("facade", "product", "shelf"):
        r[f"{k}_file"], r[f"{k}_url"] = fotos.get(k, (None, None))
    r["decision_esperada"] = res["decision"]
    r["motivo_rechazo"] = MOTIVOS.get(res["reason_code"], res["reason_code"]) if res["decision"] == "rechazada" else ""
    r.update({k: res[k] for k in OFICIAL})
    r["fuente_producto"] = datos.get("fuente_producto")
    return r


def oficial(r):
    """El JSON oficial del reto contenido en un registro (para validarlo con output.validate)."""
    return {"capture_id": r["capture_id"], "decision": r["decision_esperada"], **{k: r[k] for k in OFICIAL}}
