"""Pruebas sin dependencias externas ni red: python tests/test_core.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import decide, output  # noqa: E402
from evaluate import evaluate  # noqa: E402

CAP = {"capture_id": "CAP-1", "capture_store_name": "Bodega Aurrera", "capture_barcode": "7501",
       "capture_price": 10.0}
LOCAL_OK = {"blur": {"product": 600.0, "shelf": 500.0}, "moire": {"product": 30, "shelf": 30}, "barcodes": ["7501"]}
ALL_OK = {k: "ok" for k in decide.CRITERIOS}


def vis(precio_et=10.0, **crit):
    return {"criterios": dict(ALL_OK, **crit), "cadena_visible": "Aurrera", "precio_etiqueta": precio_et,
            "tipo_precio": "regular", "motivo": ""}


def run(local=LOCAL_OK, v="default"):
    r = decide.decide(CAP, local, vis() if v == "default" else v)
    assert output.validate(r) == [], output.validate(r)
    return r


def main():
    # con aprobación desactivada (default), la candidata sale a manual con su propio código
    assert decide.ALLOW_APPROVE is False
    r = run()
    assert r["decision"] == "revision_manual" and r["reason_code"] == "CANDIDATA_APROBACION"
    # con rechazo por identidad desactivado (default), producto/etiqueta en falla van a manual
    assert decide.REJECT_IDENTITY is False
    assert run(v=vis(producto="falla"))["decision"] == "revision_manual"
    assert run(v=vis(producto="falla", etiqueta="falla"))["decision"] == "revision_manual"
    # el resto prueba la lógica completa con aprobación y rechazo por identidad activos
    decide.ALLOW_APPROVE = True
    decide.REJECT_IDENTITY = True
    assert run()["decision"] == "aprobada"
    assert run(v=None)["decision"] == "revision_manual"
    # cualquier "dudoso" -> manual
    for k in decide.CRITERIOS:
        assert run(v=vis(**{k: "dudoso"}))["decision"] == "revision_manual", k
    # "falla" -> rechazo con su código, respetando prioridad
    assert run(v=vis(producto="falla"))["reason_code"] == "PRODUCTO_NO_COINCIDE"
    assert run(v=vis(producto="falla", etiqueta="falla"))["reason_code"] == "DESCRIPCION_INCOMPLETA"
    assert run(v=vis(pantalla="falla"))["reason_code"] == "FOTO_DE_PANTALLA"
    assert run(v=vis(cercania="falla"))["reason_code"] == "CAPTURA_LEJANA"
    assert run(v=vis(precio="falla"))["reason_code"] == "SIN_ETIQUETA_PRECIO"
    # etiqueta o fachada en falla por sí solas: manual, no rechazo
    assert run(v=vis(etiqueta="falla"))["decision"] == "revision_manual"
    assert run(v=vis(fachada="falla"))["decision"] == "revision_manual"
    # prioridad: calidad antes que identidad
    assert run(v=vis(producto="falla", pantalla="falla"))["reason_code"] == "FOTO_DE_PANTALLA"
    assert run(v=vis(producto="falla", cercania="falla"))["reason_code"] == "CAPTURA_LEJANA"
    # nitidez: rechazo solo si la medición local también es baja; si no, manual
    blurry = dict(LOCAL_OK, blur={"product": 100.0, "shelf": 500.0})
    assert run(local=blurry, v=vis(nitidez="falla"))["reason_code"] == "IMAGEN_BORROSA"
    assert run(v=vis(nitidez="falla"))["decision"] == "revision_manual"
    # "dudoso" en nitidez + local muy mala (nitidez < 70 y moiré > 110) -> rechazo; local mala sola -> manual
    very_bad = dict(LOCAL_OK, blur={"product": 60.0, "shelf": 500.0}, moire={"product": 150, "shelf": 30})
    assert run(local=very_bad, v=vis(nitidez="dudoso"))["reason_code"] == "IMAGEN_BORROSA"
    assert run(local=very_bad)["decision"] == "revision_manual"
    # señales locales bloquean la aprobación aunque Haiku diga todo ok
    assert run(local=blurry)["decision"] == "revision_manual"
    assert run(local=dict(LOCAL_OK, moire={"product": 90, "shelf": 30}))["decision"] == "revision_manual"
    # precio de etiqueta distinto o ausente: no aprobar
    assert run(v=vis(precio_et=12.0))["decision"] == "revision_manual"
    assert run(v=vis(precio_et=None))["decision"] == "revision_manual"
    # barcode leído distinto se reporta pero no bloquea
    r = run(local=dict(LOCAL_OK, barcodes=["9999"]))
    assert r["validaciones"]["codigo_barras"] == "falla" and r["decision"] == "aprobada"
    # fallback siempre válido
    assert output.validate(output.fallback("CAP-9", "x")) == []
    # costo
    m = evaluate({"a": "aprobada", "b": "rechazada", "c": "rechazada", "d": "aprobada"},
                 {"a": "aprobada", "b": "aprobada", "c": "revision_manual", "d": "rechazada"})
    assert m["costo"] == 0 + 10 + 1 + 3 and m["precision_aprobaciones"] == 0.5
    print("OK")


if __name__ == "__main__":
    main()
