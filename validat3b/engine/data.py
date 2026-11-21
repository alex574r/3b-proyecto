"""Carga de capturas. Funciona igual con el set de desarrollo y con el ciego (sin etiquetas)."""
import json
from pathlib import Path

IMG_KEYS = {"facade": "facade_file", "product": "product_file", "shelf": "shelf_file"}


def normalize(c):
    """Código de barras como str y precio como float (o None). Lanza ValueError si no son numéricos."""
    bc = c.get("capture_barcode")
    c["capture_barcode"] = str(int(bc)) if bc not in (None, "") else None
    p = c.get("capture_price")
    c["capture_price"] = float(p) if p not in (None, "") else None
    return c


def load_captures(path):
    return [normalize(c) for c in json.loads(Path(path).read_text(encoding="utf-8-sig"))]


def image_paths(cap, images_root):
    """images_root = carpeta que contiene `imagenes/` (las rutas del JSON son `imagenes/...`)."""
    return {k: Path(images_root) / cap[f] for k, f in IMG_KEYS.items()}
