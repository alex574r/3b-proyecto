"""Relleno de nulos desde el catálogo, sin red: python tests/test_catalogo.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rellenar  # noqa: E402
from engine import auto, catalogo  # noqa: E402

CSV = """id_product,product_name,product_barcode,product_price,min_product_price,max_product_price,unit_product,unit_quantity_product,product_group,product_line
7,Leche  evaporada,7501058611062,22.0,4.0,64.5,mililitro,360.0,(30) Lacti Deli NR,(03) Leches enlatadas
8,Leche evaporada light,0000000099999,25.0,5.0,60.0,mililitro,360.0,(30) Lacti Deli NR,(03) Leches enlatadas
5055,Arena para gato,0763331024755,14.0,0.0,28.0,gramo,2000.0,(29) Pets,(04) Accesorios
6,Jabón de lavandería rosa 400g,7501026005671,24.0,5.0,55.5,gramo,400.0,(13) Cleaning,(01) Jabon Ropa
"""
VACIO = {k: None for k in catalogo.CAMPOS}


def main():
    tmp = Path(tempfile.mkdtemp())
    csv = tmp / "cat.csv"
    csv.write_text(CSV, encoding="utf-8")
    cat = auto.load_catalog(csv)

    # buscar: id > código (con o sin ceros) > nombre + contenido
    assert catalogo.buscar(cat, id_product="5055") == (cat["763331024755"], "id_product")
    assert catalogo.buscar(cat, id_product=5055, barcode="7501058611062")[1] == "id_product"      # el id manda
    assert catalogo.buscar(cat, barcode="0763331024755")[1] == "codigo_barras"
    assert catalogo.buscar(cat, barcode="763331024755")[1] == "codigo_barras"
    f, m = catalogo.buscar(cat, name="Arena para gato", qty=2000, unit="gramo")
    assert (f["id_product"], m) == ("5055", "nombre")
    assert catalogo.buscar(cat, name="arena  PARA  gato!")[1] == "nombre"                            # sin acentos/mayúsculas
    # el caso Carnation: código fuera del catálogo; el nombre del empaque + 360 ml encuentra "Leche evaporada"
    f, m = catalogo.buscar(cat, barcode="7501056611060", name="100% Leche Evaporada", qty=360, unit="mililitro")
    assert (f["id_product"], m) == ("7", "nombre"), (f, m)
    # con duda no se rellena: nombres sin parecido, ambiguo, o contenido distinto que baja el puntaje
    # Haiku lee "gramo" en un líquido: con el mismo contenido (360) sigue encontrando "Leche evaporada" (mililitro)
    f, m = catalogo.buscar(cat, name="100% Leche Evaporada", qty=360, unit="gramo")
    assert (f["id_product"], m) == ("7", "nombre")
    assert catalogo.buscar(cat, name="Refresco de cola")[0] is None
    assert catalogo.buscar(cat, name="Leche")[0] is None
    assert catalogo.buscar(cat, name="Arena para gato", qty=500, unit="gramo")[1] == "nombre"     # contenido distinto solo baja el puntaje
    assert catalogo.buscar(cat, name="Arena para perro", qty=500, unit="gramo")[0] is None       # nombre distinto + contenido distinto
    assert catalogo.buscar(cat) == (None, None) and catalogo.buscar(cat, name="   ") == (None, None)

    # rellenar: solo nulos, nunca pisa, tipos como capturas.json
    r, llenos = catalogo.rellenar(dict(VACIO, capture_id="X", capture_barcode=763331024755), cat)
    assert r["id_product"] == 5055 and r["product_barcode"] == 763331024755 and r["product_price"] == 14.0
    assert r["unit_quantity_product"] == 2000.0 and r["product_group"] == "(29) Pets" and r["fuente_catalogo"] == "codigo_barras"
    assert set(llenos) == set(catalogo.CAMPOS) and r["product_name"] == "Arena para gato"
    r, llenos = catalogo.rellenar(dict(VACIO, capture_id="X", id_product=5055, product_name="Mi nombre", product_price=99.0), cat)
    assert r["product_name"] == "Mi nombre" and r["product_price"] == 99.0 and "product_price" not in llenos   # no pisa
    assert r["min_product_price"] == 0.0 and r["unit_product"] == "gramo"                                        # 0.0 es un valor, no un nulo
    lleno = dict(VACIO, capture_id="X", **{k: "v" for k in catalogo.CAMPOS})
    assert catalogo.rellenar(dict(lleno), cat)[1] == []                                                         # nada que hacer
    assert catalogo.rellenar(dict(VACIO, capture_id="X", product_name="Refresco de cola"), cat)[1] == []       # sin match

    # integración: auto.detectar usa id, código o nombre y deja la fuente
    cap = {"capture_id": "A"}
    assert auto.detectar(cap, [], None, cat)["fuente_catalogo"] is None
    d = auto.detectar(dict(cap, id_product=5055), [], None, cat)
    assert d["fuente_catalogo"] == "id_product" and d["product_barcode"] == "0763331024755" and d["max_product_price"] == 28.0
    vis = {"datos": {"producto": "100% Leche Evaporada", "contenido": 360, "unidad": "mililitro", "codigo_barras": "7501056611060"}}
    d = auto.detectar(cap, [], vis, cat)
    assert d["fuente_catalogo"] == "nombre" and d["id_product"] == 7 and d["product_name"] == "Leche  evaporada"
    assert d["capture_barcode"] == "7501056611060" and d["product_price"] == 22.0 and d["product_group"] == "(30) Lacti Deli NR"

    # rellenar.py: registro suelto, lista, exportación; dry-run no escribe; segunda pasada no cambia nada
    base = tmp / "json"
    (base / "debug").mkdir(parents=True)
    suelto = dict(VACIO, capture_id="S", capture_barcode=763331024755)
    lista = [dict(VACIO, capture_id="L1", id_product=7), dict(VACIO, capture_id="L2", product_name="Refresco de cola")]
    expo = {"total": 1, "capturas": [dict(VACIO, capture_id="E1", capture_barcode=7501026005671)]}
    for nombre, dato in (("S.json", suelto), ("resultados.json", lista), ("export.json", expo), ("debug/x.json", {"local": {}})):
        (base / nombre).write_text(json.dumps(dato), encoding="utf-8")
    (base / "roto.json").write_text("{no es json", encoding="utf-8")
    antes = {f.name: f.read_text(encoding="utf-8") for f in base.rglob("*.json")}
    seco = rellenar.procesar(base, cat, dry_run=True)
    assert (seco["archivos"], seco["registros"], seco["rellenados"], seco["sin_match"]) == (3, 4, 3, 1), seco
    assert {f.name: f.read_text(encoding="utf-8") for f in base.rglob("*.json")} == antes                     # dry-run: sin cambios
    real = rellenar.procesar(base, cat)
    assert real["rellenados"] == 3 and real["metodos"] == {"id_product": 1, "codigo_barras": 2}, real
    assert json.loads((base / "S.json").read_text(encoding="utf-8"))["id_product"] == 5055
    assert json.loads((base / "resultados.json").read_text(encoding="utf-8"))[0]["product_name"] == "Leche  evaporada"
    assert json.loads((base / "export.json").read_text(encoding="utf-8"))["capturas"][0]["id_product"] == 6
    assert (base / "debug/x.json").read_text(encoding="utf-8") == antes["x.json"]                              # no es un registro
    assert rellenar.procesar(base, cat)["rellenados"] == 0                                                     # idempotente
    print("OK")


if __name__ == "__main__":
    main()
