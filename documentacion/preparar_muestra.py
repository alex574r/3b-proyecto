"""Genera una página autocontenida con los JPEG del equipo y sus dictámenes reales."""
import argparse
import base64
import json
import re
from html import escape
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


FOTOS = (("facade", "Fachada"), ("product", "Producto"), ("shelf", "Etiqueta de precio"))
ESTADOS = {"aprobada": "Aprobada", "rechazada": "Rechazada", "revision_manual": "Revisión manual"}
ESTILO = """
*{box-sizing:border-box} html{color-scheme:light} body{margin:0;background:#faf6f4;color:#302522;font:17px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:24px} h1,h2,p{margin:0} h1{font-size:clamp(24px,4vw,38px)}
header{border-bottom:3px solid #bb2232;padding-bottom:12px} section{margin:18px 0 28px;padding:20px;background:white;border:1px solid #e6d9d5;border-radius:12px}
h2{font-size:clamp(22px,3vw,30px)} .estado{color:#812132;font-weight:650} .fotos{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:12px 0}
figure{margin:0} figcaption{font-weight:600;margin-bottom:4px} img{width:100%;height:clamp(170px,28vh,270px);object-fit:contain;background:#f6f2f0;border-radius:6px;display:block}
.datos{display:flex;gap:8px 24px;align-items:baseline;flex-wrap:wrap} .explica{margin-top:8px} a{color:#942035} code{font-size:.88em} footer{margin-top:10px}
@media(max-width:650px){main{padding:12px}.fotos{grid-template-columns:1fr}img{height:230px}section{padding:14px}}
@media print{section{break-inside:avoid}footer{display:none}img{height:160px}}
"""


def ficha(archivo, entradas, caso):
    origen, titulo, ruta = caso
    registro = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    cid = registro["capture_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cid):
        raise ValueError("Identificador de respuesta inválido")
    estado = ESTADOS[registro["decision_esperada"]]
    fotos = []
    for tipo, nombre in FOTOS:
        f = f"{origen}_{tipo}.jpg"
        coincidencias = entradas.get(f, [])
        if len(coincidencias) != 1:
            raise ValueError(f"Se esperaba exactamente un archivo {f} en el ZIP")
        datos = archivo.read(coincidencias[0])
        if not datos.startswith(b"\xff\xd8"):
            raise ValueError(f"{f} no contiene un JPEG")
        b64 = base64.b64encode(datos).decode("ascii")
        fotos.append(f'<figure><figcaption>{nombre}</figcaption><img alt="{nombre} de {escape(titulo)}" '
                     f'src="data:image/jpeg;base64,{b64}"></figure>')
    precio = registro.get("precio_detectado")
    lectura = "Sin precio legible" if precio is None else f"Precio leído: ${float(precio):,.2f}"
    return f"""<section><h2>{escape(titulo)}</h2>
<div class="datos"><span class="estado">{estado}</span><span>{lectura}</span><code>{escape(cid)}</code></div>
<div class="fotos">{''.join(fotos)}</div><p class="explica">{escape(registro.get('explicacion') or '')}</p>
<footer><a href="http://127.0.0.1:18124/portal/#captura/{cid}" target="_blank" rel="noopener">Abrir este folio en el portal USB</a></footer></section>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="ZIP oficial de imágenes de desarrollo")
    parser.add_argument("--caso", nargs=3, action="append", required=True,
                        metavar=("ID_DATASET", "TITULO", "JSON_API"),
                        help="Identificador de las fotos, título para el público y registro devuelto por la API")
    args = parser.parse_args()
    try:
        with ZipFile(args.zip) as archivo:
            entradas = {}
            for item in archivo.infolist():
                nombre = PurePosixPath(item.filename.replace("\\", "/")).name
                entradas.setdefault(nombre, []).append(item)
            fichas = [ficha(archivo, entradas, caso) for caso in args.caso]
    except (OSError, KeyError, ValueError) as error:
        parser.exit(1, f"No se pudo preparar la muestra: {error}\n")
    pagina = f"""<!doctype html><html lang="es-MX"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Validat3B · Evidencia de campo</title>
<style>{ESTILO}</style><main><header><h1>Validat3B · Evidencia de campo</h1></header>{''.join(fichas)}</main></html>"""
    salida = Path(__file__).resolve().parents[1] / "salida_presentacion" / "muestra.html"
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(pagina, encoding="utf-8")
    print(salida)


if __name__ == "__main__":
    main()
