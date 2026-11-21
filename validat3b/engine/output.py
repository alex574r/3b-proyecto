"""Formato de salida por captura + validación.

shortcut: REASON_CODES y los valores de `validaciones` son PROVISIONALES (inferidos del ejemplo del reto
y de los motivos del dev). Reemplazar por la lista/esquema oficial cuando se descargue de la página.
"""
DECISIONS = {"aprobada", "rechazada", "revision_manual"}
VALIDACION_KEYS = ("tienda_fachada", "producto", "codigo_barras", "evidencia_precio")
VALIDACION_VALUES = {"ok", "falla", "no_evaluable"}
REASON_CODES = {
    "APROBADA", "PRODUCTO_NO_COINCIDE", "FOTO_DE_PANTALLA", "IMAGEN_BORROSA", "CAPTURA_LEJANA",
    "FACHADA_INCORRECTA", "SIN_ETIQUETA_PRECIO", "DESCRIPCION_INCOMPLETA",
    "EVIDENCIA_AMBIGUA", "SIN_ANALISIS_VISUAL", "ERROR_PROCESAMIENTO",
}


def make(capture_id, decision, confidence, reason, validaciones, precio=None, barcode=None, explicacion=""):
    return {
        "capture_id": capture_id,
        "decision": decision,
        "confidence_score": round(float(confidence), 2),
        "reason_code": reason,
        "validaciones": validaciones,
        "precio_detectado": precio,
        "codigo_barras_detectado": barcode,
        "explicacion": explicacion,
    }


def fallback(capture_id, why):
    """Nunca dejar una captura sin JSON válido: ante error, revisión manual."""
    v = {k: "no_evaluable" for k in VALIDACION_KEYS}
    return make(capture_id, "revision_manual", 0.0, "ERROR_PROCESAMIENTO", v, None, None, f"Error de procesamiento: {why}")


def validate(o):
    """Devuelve lista de errores (vacía = válido)."""
    e = []
    if not isinstance(o.get("capture_id"), str):
        e.append("capture_id")
    if o.get("decision") not in DECISIONS:
        e.append("decision")
    c = o.get("confidence_score")
    if not isinstance(c, (int, float)) or not 0 <= c <= 1:
        e.append("confidence_score")
    if o.get("reason_code") not in REASON_CODES:
        e.append("reason_code")
    v = o.get("validaciones")
    if not isinstance(v, dict) or set(v) != set(VALIDACION_KEYS) or not set(v.values()) <= VALIDACION_VALUES:
        e.append("validaciones")
    p = o.get("precio_detectado")
    if p is not None and not isinstance(p, (int, float)):
        e.append("precio_detectado")
    b = o.get("codigo_barras_detectado")
    if b is not None and not isinstance(b, str):
        e.append("codigo_barras_detectado")
    if not isinstance(o.get("explicacion"), str):
        e.append("explicacion")
    return e
