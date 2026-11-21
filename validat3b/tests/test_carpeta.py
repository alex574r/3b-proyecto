"""Analizar carpetas (motor y ventana tkinter), sin red: python tests/test_carpeta.py"""
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from engine import auto, carpeta, output  # noqa: E402


def foto(ruta, color):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (200, 300), color).save(ruta, "JPEG")


def crear(base):
    """Carpeta como Validat3B_desarrollo_imagenes: subcarpeta imagenes/ con 2 capturas completas y casos incompletos."""
    for cid in ("CAP-1", "CAP-2"):
        for k in carpeta.KINDS:
            foto(base / "imagenes" / f"{cid}_{k}.jpg", (120, 130, 140))
    foto(base / "imagenes" / "CAP-3_facade.jpg", "red")                 # incompleta
    foto(base / "imagenes" / "mala foto_product.jpg", "red")            # id inválido
    foto(base / "imagenes" / "CAP-4_shelf.PNG".replace("PNG", "jpg"), "red")
    (base / "imagenes" / "notas.txt").write_text("no es una foto")


def main():
    base = Path(tempfile.mkdtemp())
    crear(base)

    capturas, avisos = carpeta.buscar_capturas(base)
    assert sorted(capturas) == ["CAP-1", "CAP-2"] and set(capturas["CAP-1"]) == set(carpeta.KINDS)
    assert any("CAP-3" in a and "faltan" in a for a in avisos) and any("mala foto" in a for a in avisos), avisos

    # sin Haiku: un JSON por captura con la forma del registro, y el consolidado
    salida = base / "salida"
    vistos = []
    regs = carpeta.analizar_carpeta(base, salida, None, {}, workers=2, on_result=lambda r, n, t: vistos.append((n, t)))
    assert [r["capture_id"] for r in regs] == ["CAP-1", "CAP-2"] and sorted(vistos) == [(1, 2), (2, 2)]
    for r in regs:
        assert list(r)[:len(auto.REGISTRO)] == list(auto.REGISTRO) and output.validate(auto.oficial(r)) == []
        assert r["decision_esperada"] == "revision_manual" and r["reason_code"] == "SIN_ANALISIS_VISUAL"
        assert r["facade_file"] == f"imagenes/{r['capture_id']}_facade.jpg" and r["facade_url"] is None
        assert json.loads((salida / f"{r['capture_id']}.json").read_text(encoding="utf-8")) == r
    assert json.loads((salida / "resultados.json").read_text(encoding="utf-8")) == regs

    # reutiliza lo guardado (no recalcula), y un archivo dañado se vuelve a analizar
    (salida / "CAP-1.json").write_text(json.dumps({"capture_id": "CAP-1", "marca": "guardado"}), encoding="utf-8")
    (salida / "CAP-2.json").write_text("{dañado", encoding="utf-8")
    r1, r2 = (carpeta.analizar_captura(c, capturas[c], base, salida, None, {}, reutilizar=True) for c in ("CAP-1", "CAP-2"))
    assert r1["marca"] == "guardado" and r2["reason_code"] == "SIN_ANALISIS_VISUAL"
    assert carpeta.analizar_captura("CAP-1", capturas["CAP-1"], base, salida, None, {}, reutilizar=False)["reason_code"] == "SIN_ANALISIS_VISUAL"

    # foto corrupta: el registro sale con ERROR_PROCESAMIENTO y también se guarda
    (base / "imagenes" / "CAP-2_product.jpg").write_bytes(b"basura")
    r = carpeta.analizar_captura("CAP-2", capturas["CAP-2"], base, salida, None, {}, reutilizar=False)
    assert r["reason_code"] == "ERROR_PROCESAMIENTO" and output.validate(auto.oficial(r)) == []

    # detener: no se empiezan capturas nuevas
    stop = threading.Event()
    stop.set()
    assert carpeta.analizar_carpeta(base, base / "salida2", None, {}, stop=stop) == []

    gui_humo(base)
    print("OK")


def gui_humo(base):
    """Crea la ventana (oculta), analiza la carpeta sin Haiku y comprueba la tabla. Se omite si no hay pantalla."""
    import tkinter as tk
    import gui
    try:
        app = gui.App()
    except tk.TclError as e:
        print("sin pantalla, se omite la prueba de la ventana:", e)
        return
    app.withdraw()
    gui.SALIDA = base / "salidas_gui"
    app.iniciar(str(base), usar_llm=False, reutilizar=False)
    fin = time.time() + 30
    while app.hilo.is_alive() or not app.cola.empty():
        assert time.time() < fin, "el análisis no terminó"
        app.update()
        time.sleep(0.05)
    app.update()
    assert sorted(app.tabla.get_children()) == ["CAP-1", "CAP-2"], app.tabla.get_children()
    v = app.tabla.item("CAP-1", "values")
    assert v[0] == "CAP-1" and v[1] == "revision_manual" and v[2] == "SIN_ANALISIS_VISUAL", v
    assert (gui.SALIDA / base.name / "CAP-1.json").exists() and (gui.SALIDA / base.name / "resultados.json").exists()
    assert "Listo" in app.estado.get() and "revision manual 2" in app.estado.get(), app.estado.get()
    app.destroy()


if __name__ == "__main__":
    main()
