"""Regresión sobre las capturas reales que motivaron el ajuste (requiere ../../capturas.json e imagenes/).

IMPORTES: caja del precio completo en píxeles del ORIGINAL, anotada por inspección visual del desarrollador
(no es anotación humana del reto ni la ve el selector). Sirve para verificar la geometría del recorte:
"el recorte contiene el importe completo". No verifica la lectura del modelo.
"""
import importlib.util
import json
import sys
import unittest
import os
from pathlib import Path

PILOTO = Path(__file__).resolve().parents[1]
DATOS = Path(os.environ.get("VALIDAT3B_DATOS", PILOTO.parent.parent))
sys.path.insert(0, str(PILOTO))
import piloto_etiquetas as v2  # noqa: E402

_spec = importlib.util.spec_from_file_location("piloto_v1", PILOTO / "linea_base" / "piloto_etiquetas_v1.py")
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

IMPORTES = {  # x0, y0, x1, y1 del importe con "$" (original)
    "CAP-563575": (218, 776, 410, 858),
    "CAP-410562": (205, 544, 316, 575),
    "CAP-635322": (1190, 600, 3230, 1210),
    "CAP-393881": (1220, 1350, 2245, 1790),
    "CAP-520473": (296, 508, 436, 592),
    "CAP-899554": (267, 344, 363, 405),
}
FALLAS_V1 = [("CAP-563575", "android"), ("CAP-410562", "lote"), ("CAP-635322", "lote"),
             ("CAP-393881", "lote"), ("CAP-393881", "android")]
CONTROLES = [("CAP-520473", "lote"), ("CAP-520473", "android"), ("CAP-899554", "lote"), ("CAP-899554", "android")]
HAY_DATOS = (DATOS / "capturas.json").exists()
_cache = {}


def elegir(mod, cid, origen):
    """(variante, motivo, recorte en coordenadas del original o None)."""
    clave = (mod.__name__, cid, origen)
    if clave not in _cache:
        caps = {c["capture_id"]: c for c in json.loads((DATOS / "capturas.json").read_text(encoding="utf-8-sig"))}
        orig = mod.cargar_rgb(DATOS / caps[cid]["shelf_file"])
        src = orig if origen == "lote" else mod.simular_android(orig)
        reg = mod.region_recorte(mod.detectar_etiquetas(src), src.size)
        sen = mod.senales_recorte(src.crop(reg["box"])) if reg else None
        var, motivo = mod.selector(reg, sen)
        k = src.size[0] / orig.size[0]
        _cache[clave] = (var, motivo, [v / k for v in reg["box"]] if reg and var != "A" else None)
    return _cache[clave]


def contiene_importe(box, imp):
    tx, ty = 0.03 * (imp[2] - imp[0]), 0.05 * (imp[3] - imp[1])  # tolerancia de la anotación
    return box[0] <= imp[0] + tx and box[1] <= imp[1] + ty and box[2] >= imp[2] - tx and box[3] >= imp[3] - ty


@unittest.skipUnless(HAY_DATOS, "faltan capturas.json e imagenes/ en la carpeta de datos")
class Regresion(unittest.TestCase):
    def test_v1_reproduce_las_cuatro_fallas(self):
        for cid, origen in FALLAS_V1:
            var, motivo, box = elegir(v1, cid, origen)
            with self.subTest(cid=cid, origen=origen):
                self.assertIn(var, ("B", "C"), "v1 debía elegir un recorte")
                self.assertFalse(contiene_importe(box, IMPORTES[cid]), "v1 debía dejar fuera parte del importe")

    def test_v1_controles_eran_utiles(self):
        for cid, origen in CONTROLES:
            var, _, box = elegir(v1, cid, origen)
            with self.subTest(cid=cid, origen=origen):
                self.assertIn(var, ("B", "C"))
                self.assertTrue(contiene_importe(box, IMPORTES[cid]))

    def test_v2_no_entrega_vista_enganosa(self):
        for cid, origen in FALLAS_V1 + CONTROLES + [("CAP-563575", "lote")]:
            var, motivo, box = elegir(v2, cid, origen)
            with self.subTest(cid=cid, origen=origen, var=var, motivo=motivo):
                self.assertTrue(motivo)
                if var != "A":
                    self.assertTrue(contiene_importe(box, IMPORTES[cid]), "el recorte excluye parte del importe")

    def test_v2_caso_19_ya_no_muestra_9_00(self):
        var, motivo, box = elegir(v2, "CAP-563575", "android")
        self.assertTrue(var == "A" or contiene_importe(box, IMPORTES["CAP-563575"]), (var, motivo))

    def test_v2_conserva_controles(self):
        for cid, origen in CONTROLES:
            var, motivo, box = elegir(v2, cid, origen)
            with self.subTest(cid=cid, origen=origen):
                self.assertIn(var, ("B", "C"), motivo)
                self.assertTrue(contiene_importe(box, IMPORTES[cid]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
