"""Busca un producto en el catálogo y rellena los campos nulos de un registro con sus datos.

Búsqueda, en este orden: id_product, código de barras y, si no hay, nombre + contenido. Por nombre solo se acepta una
coincidencia clara (puntaje >= UMBRAL y ventaja >= MARGEN sobre la segunda); si hay duda no se rellena nada.
Nunca se pisa un valor que ya existe.
"""
import difflib
import os
import re
import unicodedata
from pathlib import Path

CAMPOS = ("id_product", "product_name", "product_barcode", "product_price", "min_product_price", "max_product_price",
          "unit_product", "unit_quantity_product", "product_group", "product_line")
# Medido con las 150 capturas de dev + ciego que traen su SKU real, buscando solo por nombre y contenido:
# acierta 142, se equivoca 0, sin respuesta 8. Con umbral 0.6 se equivocaba 4 veces.
UMBRAL, MARGEN, PESO_CONTENIDO = 0.7, 0.05, 0.15
_MASA_VOLUMEN = {"gramo", "mililitro"}
_RAIZ = Path(__file__).resolve().parent.parent.parent
_RUTAS = (_RAIZ / "Validat3B_evaluacion_metadatos" / "catalogo_productos.csv",
          _RAIZ / "Validat3B_desarrollo_metadatos" / "catalogo_productos.csv")


def ruta_catalogo():
    """VALIDAT3B_CATALOGO, o el primer catálogo que exista (evaluación, luego desarrollo)."""
    env = os.environ.get("VALIDAT3B_CATALOGO")
    return Path(env) if env else next((p for p in _RUTAS if p.exists()), _RUTAS[0])


def _digits(s):
    return re.sub(r"\D", "", str(s if s is not None else ""))


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s)


def _toks(s):
    return {t for t in _norm(s).split() if not t.isdigit() and len(t) > 1}


def _num(x):
    try:
        return None if x in (None, "") or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def valor(fila, campo):
    """Valor tipado de un campo del catálogo (la fila viene del CSV, todo texto)."""
    v = fila.get(campo)
    if v in (None, ""):
        return None
    if campo == "id_product":
        return int(_digits(v)) if _digits(v) else None
    if campo == "product_barcode":
        return int(_digits(v)) if _digits(v) else None
    if campo in ("product_price", "min_product_price", "max_product_price", "unit_quantity_product"):
        return _num(v)
    return v


def puntaje(nombre, qty, unit, fila):
    a, b = _norm(nombre), _norm(fila["product_name"])
    seq = difflib.SequenceMatcher(None, a, b).ratio()
    ta, tb = _toks(nombre), _toks(fila["product_name"])
    s = 0.5 * seq + 0.5 * (len(ta & tb) / len(ta | tb) if ta | tb else 0)
    q, qf = _num(qty), _num(fila.get("unit_quantity_product"))
    if q and qf:  # mismo contenido sube el puntaje, distinto lo baja
        uf = fila.get("unit_product")
        # Haiku suele leer "gramo" en líquidos (el catálogo dice mililitro): con el mismo número cuentan como compatibles
        unidad_ok = not unit or unit == uf or {unit, uf} <= _MASA_VOLUMEN
        s += PESO_CONTENIDO if abs(q - qf) < 1e-6 and unidad_ok else -PESO_CONTENIDO
    return s


def buscar(catalog, id_product=None, barcode=None, name=None, qty=None, unit=None):
    """catalog: {código sin ceros: fila} (auto.load_catalog). -> (fila, método) o (None, None).
    método: 'id_product' | 'codigo_barras' | 'nombre'."""
    filas = list(catalog.values())
    ident = _digits(id_product)
    if ident:
        fila = next((f for f in filas if _digits(f.get("id_product")).lstrip("0") == ident.lstrip("0")), None)
        if fila:
            return fila, "id_product"
    code = _digits(barcode).lstrip("0")
    if code and code in catalog:
        return catalog[code], "codigo_barras"
    if name and str(name).strip():
        ranking = sorted(((puntaje(name, qty, unit, f), f) for f in filas), key=lambda x: -x[0])
        if len(ranking) >= 1 and ranking[0][0] >= UMBRAL and (len(ranking) < 2 or ranking[0][0] - ranking[1][0] >= MARGEN):
            return ranking[0][1], "nombre"
    return None, None


def rellenar(registro, catalog):
    """Rellena (en el propio registro) los CAMPOS que estén en None o vacíos. -> (registro, [campos rellenados]).
    Agrega `fuente_catalogo` con el método usado cuando rellena algo."""
    nulos = [k for k in CAMPOS if registro.get(k) in (None, "")]
    if not nulos:
        return registro, []
    fila, metodo = buscar(catalog, registro.get("id_product"), registro.get("product_barcode") or registro.get("capture_barcode"),
                          registro.get("product_name"), registro.get("unit_quantity_product"), registro.get("unit_product"))
    llenados = []
    for k in nulos if fila else ():
        v = valor(fila, k)
        if v is not None:
            registro[k] = v
            llenados.append(k)
    if llenados and not registro.get("fuente_catalogo"):
        registro["fuente_catalogo"] = metodo
    return registro, llenados
