"""Motor de reglas: señales locales + criterios de Haiku -> decisión.

Principio: rechazar solo con "falla" firme de Haiku (nitidez confirmada por medición local; etiqueta o fachada
solas no bastan);
aprobar solo si TODOS los criterios están en "ok" y las señales locales pasan sus cortes; lo demás -> manual.

shortcut: cortes calibrados a ojo sobre las 100 capturas de dev (riesgo de sobreajuste) y confianzas fijas.
Reemplazar por una probabilidad calibrada cuando haya corrida completa con Haiku.
"""
from . import output

# Cortes para PERMITIR aprobar (no para rechazar). En dev: 31/33 aprobadas tienen nitidez mínima >= 180
# y 32/33 tienen moiré <= 65; 8/11 borrosas quedan por debajo de 180.
APPROVE_BLUR_MIN = 180.0
APPROVE_MOIRE_MAX = 65.0
REJECT_BLUR_MAX = 180.0   # nitidez "falla" de Haiku solo se acepta como rechazo si la medición local también es baja
APPROVE_CONF = 0.97
FIRM_CONF = 0.90
MANUAL_CONF = 0.50
PRICE_TOL = 0.01

# Muy mala calidad local: en dev nunca coincide con una aprobada (6 rechazos, 3 revisiones manuales).
# Solo se usa junto con "dudoso" de Haiku en nitidez, porque sola sale neutra en costo.
LOCAL_BAD_BLUR = 70.0
LOCAL_BAD_MOIRE = 110.0

CRITERIOS = ("fachada", "pantalla", "nitidez", "cercania", "producto", "etiqueta", "precio")
_VAL = {"ok": "ok", "falla": "falla"}  # "dudoso" o cualquier otra cosa -> no_evaluable


def _worst(*vals):
    return "falla" if "falla" in vals else ("ok" if all(v == "ok" for v in vals) else "no_evaluable")


def _barcode_check(cap, local):
    decoded = [d.lstrip("0") for d in local["barcodes"]]
    if not decoded:
        return "no_evaluable", None
    want = (cap["capture_barcode"] or "").lstrip("0")
    if want in decoded:
        return "ok", cap["capture_barcode"]
    return "falla", local["barcodes"][0]


def decide(cap, local, vision):
    cid = cap["capture_id"]
    bc_val, bc_found = _barcode_check(cap, local)
    val = {"tienda_fachada": "no_evaluable", "producto": "no_evaluable",
           "codigo_barras": bc_val, "evidencia_precio": "no_evaluable"}

    if vision is None:
        return output.make(cid, "revision_manual", MANUAL_CONF, "SIN_ANALISIS_VISUAL", val, None, bc_found,
                           "No hubo análisis visual; se envía a revisión manual.")

    crit = {k: (vision.get("criterios") or {}).get(k) for k in CRITERIOS}
    p = vision.get("precio_etiqueta")
    precio = float(p) if isinstance(p, (int, float)) else None
    price_ok = precio is not None and cap["capture_price"] is not None and abs(precio - cap["capture_price"]) <= PRICE_TOL

    val["tienda_fachada"] = _VAL.get(crit["fachada"], "no_evaluable")
    val["producto"] = _worst(*(_VAL.get(crit[k], "no_evaluable") for k in ("producto", "etiqueta", "cercania")))
    v_precio = _VAL.get(crit["precio"], "no_evaluable")
    val["evidencia_precio"] = "falla" if v_precio == "falla" or (v_precio == "ok" and precio is not None and not price_ok) else v_precio

    min_blur = min(local["blur"].values())
    max_moire = max(local["moire"].values())
    motivo = (vision.get("motivo") or "").strip()

    # --- rechazos firmes, en orden de prioridad del reason_code ---
    # Calidad va primero: con una foto mala, las fallas de identidad suelen ser consecuencia (en dev los rechazos
    # por calidad dominan). Etiqueta o fachada en "falla" por sí solas van a manual: en dev Haiku se equivocó en
    # ambas (etiqueta "Bayo" vs producto "Negros" aprobada por 3B; fachada mal leída).
    f = {k: crit[k] == "falla" for k in CRITERIOS}
    local_bad = min_blur < LOCAL_BAD_BLUR and max_moire > LOCAL_BAD_MOIRE
    blurry = (f["nitidez"] and min_blur < REJECT_BLUR_MAX) or (crit["nitidez"] == "dudoso" and local_bad)
    firm = (
        (f["pantalla"], "FOTO_DE_PANTALLA", "La foto parece tomada a la pantalla de otro celular."),
        (blurry, "IMAGEN_BORROSA", "Las fotos del producto o la etiqueta están borrosas."),
        (f["cercania"], "CAPTURA_LEJANA", "La foto del producto es demasiado lejana."),
        # en dev, producto y etiqueta de otra variante ("estrella" vs "moñito") se registró como descripción incompleta
        (f["producto"] and f["etiqueta"], "DESCRIPCION_INCOMPLETA", "La etiqueta y el producto no corresponden a la descripción esperada."),
        (f["producto"], "PRODUCTO_NO_COINCIDE", "El producto de la foto no coincide con el esperado."),
        (f["precio"], "SIN_ETIQUETA_PRECIO", "No hay etiqueta de precio legible."),
    )
    for hit, code, why in firm:
        if hit:
            return output.make(cid, "rechazada", FIRM_CONF, code, val, precio, bc_found, motivo or why)

    # --- aprobar solo si todo está en verde ---
    all_ok = all(crit[k] == "ok" for k in CRITERIOS)
    local_ok = min_blur >= APPROVE_BLUR_MIN and max_moire <= APPROVE_MOIRE_MAX
    if all_ok and local_ok and price_ok:
        return output.make(cid, "aprobada", APPROVE_CONF, "APROBADA", val, precio, bc_found,
                           "Fachada, producto y etiqueta coinciden con lo esperado; precio confirmado en etiqueta.")

    dudas = [k for k in CRITERIOS if crit[k] != "ok"]
    if not local_ok:
        dudas.append("calidad_local")
    if not price_ok:
        dudas.append("precio_no_confirmado")
    return output.make(cid, "revision_manual", MANUAL_CONF, "EVIDENCIA_AMBIGUA", val, precio, bc_found,
                       motivo or f"No se puede confirmar: {', '.join(dudas)}.")
