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
# Aprobación automática apagada: en dev, 6 de 22 aprobaciones fueron malas (5 eran revision_manual que Haiku ve
# perfectas). Las candidatas salen como revision_manual con CANDIDATA_APROBACION. Reactivar cuando se sepa cómo
# puntúa el script oficial una captura con etiqueta revision_manual.
ALLOW_APPROVE = False
# Rechazo por identidad apagado: en dev, 1 de 5 rechazos por producto/etiqueta fue correcto (Haiku marca "falla"
# por gramaje o variante que 3B acepta, y el catálogo no trae contratipos permitidos). Van a revisión manual.
# Reactivar con las reglas oficiales y la lista de contratipos.
REJECT_IDENTITY = False
# Aprobación por datos completos (solo si quien llama pasa `datos`: API, app y ventana; run.py no, porque genera el
# archivo oficial del set ciego): se aprueba si todos los CAMPOS_COMPLETOS vienen rellenos, los 7 criterios de Haiku
# están en "ok" y la nitidez medida pasa el corte. En dev: 27 aprobadas con 78 % de precisión (sin los 7 criterios
# eran 49 con 61 %); sigue por debajo del 97 % que exige el reto.
APPROVE_POR_DATOS = True
CAMPOS_COMPLETOS = ("capture_id", "capture_store_name", "capture_date", "capture_barcode", "capture_price",
                    "capture_brand", "product_name")
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


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _discount(vision, cap, precio):
    """(precio de oferta validado o None, motivo si se descartó). Una oferta no puede costar más que el precio de la
    etiqueta ni salirse del rango de referencia del catálogo; si pasa, Haiku probablemente leyó mal la etiqueta."""
    d = vision.get("precio_descuento")
    if d is None:
        return None, ""
    if not _is_num(d) or d <= 0:
        return None, "precio de descuento ilegible"
    if precio is not None and d > precio + PRICE_TOL:
        return None, f"precio de descuento {d} mayor que el de la etiqueta {precio}"
    lo, hi = cap.get("min_product_price"), cap.get("max_product_price")
    if _is_num(hi) and hi > 0 and not (lo if _is_num(lo) else 0) <= d <= hi:
        return None, f"precio de descuento {d} fuera del rango de referencia"
    return float(d), ""


def datos_completos(datos):
    return datos is not None and all(datos.get(k) not in (None, "") for k in CAMPOS_COMPLETOS)


def decide(cap, local, vision, datos=None):
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
    desc, desc_nota = _discount(vision, cap, precio)
    cp = cap["capture_price"]
    # el usuario pudo capturar el precio regular o el de oferta: cualquiera de los dos confirma el precio
    price_ok = cp is not None and any(x is not None and abs(x - cp) <= PRICE_TOL for x in (precio, desc))

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
        (REJECT_IDENTITY and f["producto"] and f["etiqueta"], "DESCRIPCION_INCOMPLETA",
         "La etiqueta y el producto no corresponden a la descripción esperada."),
        (REJECT_IDENTITY and f["producto"], "PRODUCTO_NO_COINCIDE", "El producto de la foto no coincide con el esperado."),
        (f["precio"], "SIN_ETIQUETA_PRECIO", "No hay etiqueta de precio legible."),
    )
    for hit, code, why in firm:
        if hit:
            return output.make(cid, "rechazada", FIRM_CONF, code, val, precio, bc_found, motivo or why, desc)

    # --- aprobar por datos completos: los 7 campos rellenos y fotos nítidas y cercanas (los rechazos firmes ya salieron) ---
    if (APPROVE_POR_DATOS and datos_completos(datos) and all(crit[k] == "ok" for k in CRITERIOS)
            and min_blur >= APPROVE_BLUR_MIN):
        return output.make(cid, "aprobada", APPROVE_CONF, "APROBADA", val, precio, bc_found,
                           "Datos completos (id, tienda, fecha, código, precio, marca y producto) y los 7 criterios de las fotos en orden.", desc)

    # --- aprobar solo si todo está en verde ---
    all_ok = all(crit[k] == "ok" for k in CRITERIOS)
    local_ok = min_blur >= APPROVE_BLUR_MIN and max_moire <= APPROVE_MOIRE_MAX
    if all_ok and local_ok and price_ok and not desc_nota:
        if ALLOW_APPROVE:
            return output.make(cid, "aprobada", APPROVE_CONF, "APROBADA", val, precio, bc_found,
                               "Fachada, producto y etiqueta coinciden con lo esperado; precio confirmado en etiqueta.", desc)
        return output.make(cid, "revision_manual", MANUAL_CONF, "CANDIDATA_APROBACION", val, precio, bc_found,
                           "Toda la evidencia coincide; la aprobación automática está desactivada, revisión rápida.", desc)

    dudas = [k for k in CRITERIOS if crit[k] != "ok"]
    if not local_ok:
        dudas.append("calidad_local")
    if not price_ok:
        dudas.append("precio_no_confirmado")
    if desc_nota:
        dudas.append(desc_nota)
    expl = motivo or f"No se puede confirmar: {', '.join(dudas)}."
    if desc_nota and motivo:
        expl += f" Además: {desc_nota}."
    return output.make(cid, "revision_manual", MANUAL_CONF, "EVIDENCIA_AMBIGUA", val, precio, bc_found, expl, desc)
