"""Reglas del selector v2 sobre imágenes sintéticas: no dependen de ningún capture_id.

Cada prueba dibuja una etiqueta con OpenCV y comprueba la regla, no un caso concreto del conjunto de desarrollo.
"""
import inspect
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import piloto_etiquetas as v2  # noqa: E402

F = cv2.FONT_HERSHEY_SIMPLEX
TINTA = (25, 25, 25)


def lienzo(color=(40, 90, 200), w=720, h=960):
    return np.full((h, w, 3), color, np.uint8)


def etiqueta(img, x, y, entero="19", centavos="00", desc="LECHE ENTERA 1 L", escala=2.6, w=380, h=190):
    """Etiqueta blanca con descripción arriba, "$" + entero grande y centavos superíndice.
    Devuelve la caja del importe (x0, y0, x1, y1)."""
    cv2.rectangle(img, (x, y), (x + w, y + h), (232, 232, 228), -1)  # papel, no blanco saturado
    if desc:
        cv2.putText(img, desc, (x + 20, y + 38), F, 0.75, TINTA, 2)
    base = y + 140
    (tw, th), _ = cv2.getTextSize("$" + entero, F, escala, 7)
    cv2.putText(img, "$" + entero, (x + 20, base), F, escala, TINTA, 7)
    cv2.circle(img, (x + 20 + tw + 10, base - 4), 5, TINTA, -1)
    (cw, ch), _ = cv2.getTextSize(centavos, F, escala * 0.5, 4)
    cx = x + 20 + tw + 24
    cv2.putText(img, centavos, (cx, base - th + ch), F, escala * 0.5, TINTA, 4)
    return (x + 15, base - th - 8, cx + cw + 5, base + 12)


def elegir(img):
    im = Image.fromarray(img)
    reg = v2.region_recorte(v2.detectar_etiquetas(im), im.size)
    sen = v2.senales_recorte(im.crop(reg["box"])) if reg else None
    var, motivo = v2.selector(reg, sen)
    return var, motivo, (reg["box"] if reg else None)


def contiene(box, caja, tol=3):
    return box[0] <= caja[0] + tol and box[1] <= caja[1] + tol and box[2] >= caja[2] - tol and box[3] >= caja[3] - tol


class ReglasSinteticas(unittest.TestCase):
    def test_etiqueta_limpia_se_recorta_completa(self):
        img = lienzo()
        caja = etiqueta(img, 170, 380)
        var, motivo, box = elegir(img)
        self.assertIn(var, ("B", "C"), motivo)
        self.assertTrue(contiene(box, caja), (box, caja))

    def test_centavos_no_se_recortan_solos(self):
        """Centavos pequeños junto a enteros 3x más altos ("$5.50"): nunca un recorte que muestre solo "50"."""
        img = lienzo()
        caja = etiqueta(img, 150, 380, entero="5", centavos="50", escala=3.2, w=420)
        var, motivo, box = elegir(img)
        self.assertTrue(var == "A" or contiene(box, caja), (var, motivo, box, caja))

    def test_franja_encuentra_trazos_fuera_y_fragmentos(self):
        """Lo que v1 no veía: un trazo completamente fuera del recorte y un fragmento ancho que cruza el borde."""
        linea = {"hc": 30, "filas": (100, 130), "claves": set()}
        box = [200, 60, 400, 170]
        uno_fuera = (180, 102, 10, 28, 200)        # "1" fuera del recorte, dentro de la franja de 1 altura
        fragmento = (190, 110, 28, 19, 300)        # trozo de "9" más ancho que alto que cruza el borde
        lejano = (60, 100, 18, 30, 300)            # trazo a más de una altura: no cuenta
        renglon = (210, 20, 15, 12, 100)           # texto de la descripción, fuera de las filas del importe
        fuera = v2._trazos_fuera(box, linea, [uno_fuera, fragmento, lejano, renglon])
        self.assertIn(uno_fuera, fuera)
        self.assertIn(fragmento, fuera)
        self.assertNotIn(lejano, fuera)
        self.assertNotIn(renglon, fuera)

    def test_codigo_de_barras_no_es_importe(self):
        img = lienzo()
        cv2.rectangle(img, (150, 380), (560, 560), (245, 245, 245), -1)
        cv2.putText(img, "ARROZ 1 KG", (170, 420), F, 0.75, TINTA, 2)
        x = 180
        for i in range(40):
            ancho = 3 + (i * 7) % 6
            cv2.rectangle(img, (x, 440), (x + ancho, 530), TINTA, -1)
            x += ancho + 4 + (i * 5) % 4
        var, motivo, _ = elegir(img)
        self.assertEqual(var, "A", motivo)

    def test_dos_etiquetas_parecidas_usan_foto_completa(self):
        img = lienzo(w=960, h=720)
        etiqueta(img, 40, 260, entero="19", centavos="00")
        etiqueta(img, 500, 260, entero="23", centavos="50", desc="LECHE LIGHT 1 L")
        var, motivo, _ = elegir(img)
        self.assertEqual(var, "A", motivo)

    def test_sin_descripcion_usa_foto_completa(self):
        img = lienzo()
        etiqueta(img, 170, 380, desc=None)
        var, motivo, _ = elegir(img)
        self.assertEqual((var, motivo), ("A", "sin_descripcion"))

    def test_importe_cortado_por_el_borde_de_la_foto(self):
        img = lienzo()
        etiqueta(img, -40, 380)  # el "$" queda fuera de la foto
        var, motivo, _ = elegir(img)
        self.assertEqual(var, "A", motivo)

    def test_selector_solo_recibe_imagen(self):
        """El selector y el detector no reciben precio reportado, decisión ni anotaciones."""
        self.assertEqual(list(inspect.signature(v2.detectar_etiquetas).parameters), ["im", "traza"])
        self.assertEqual(list(inspect.signature(v2.selector).parameters), ["reg", "sen"])

    def test_variantes_no_reconstruyen_digitos(self):
        """B es el mismo recorte reescalado; C solo cambia contraste local: mismas dimensiones que B."""
        img = lienzo()
        etiqueta(img, 170, 380)
        im = Image.fromarray(img)
        crop = im.crop((150, 360, 570, 590))
        b, b_size, _ = v2.preparar_recorte(crop)
        c, c_size, _ = v2.preparar_recorte(v2.clahe_L(crop))
        self.assertEqual(b_size, c_size)
        self.assertEqual(v2.clahe_L(crop).size, crop.size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
