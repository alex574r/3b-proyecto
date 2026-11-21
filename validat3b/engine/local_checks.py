"""Chequeos locales (sin tokens): nitidez, indicio de foto-a-pantalla y decodificación de códigos de barras."""
import cv2
import numpy as np
import zxingcpp
from PIL import Image, ImageOps


def _load(path, mode, max_side=1024):
    im = ImageOps.exif_transpose(Image.open(path)).convert(mode)
    im.thumbnail((max_side, max_side))
    return np.asarray(im)


def blur_score(gray):
    """Varianza del Laplaciano: más bajo = más borrosa."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def moire_score(gray):
    """Pico/mediana del espectro en banda media-alta. Solo se registra para calibrar; la decisión
    todavía no lo usa (shortcut: sin umbral hasta ver los valores en debug/)."""
    g = gray.astype(np.float64)
    f = np.abs(np.fft.fftshift(np.fft.fft2(g - g.mean())))
    h, w = f.shape
    yy, xx = np.ogrid[:h, :w]
    r = np.hypot(yy - h // 2, xx - w // 2)
    band = f[(r > min(h, w) * 0.1) & (r < min(h, w) * 0.5)]
    return float(band.max() / (np.median(band) + 1e-9))


def decode_barcodes(paths):
    """Códigos legibles en las fotos dadas (etiqueta y producto), a resolución completa."""
    out = []
    for p in paths:
        img = np.asarray(ImageOps.exif_transpose(Image.open(p)).convert("L"))
        out += [r.text for r in zxingcpp.read_barcodes(img)]
    return out


def analyze(paths):
    """paths: {'facade','product','shelf'} -> dict de rasgos locales."""
    blur, moire = {}, {}
    for k in ("product", "shelf"):
        g = _load(paths[k], "L")
        blur[k], moire[k] = blur_score(g), moire_score(g)
    return {
        "blur": blur,
        "moire": moire,
        "barcodes": decode_barcodes([paths["shelf"], paths["product"]]),
    }
