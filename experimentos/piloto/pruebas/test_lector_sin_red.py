"""Fase remota sin red: cliente Foundry simulado. Tope de llamadas, caché, corte por error de autenticación,
prompt idéntico y sin datos de la captura. Escribe solo en un directorio temporal."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PILOTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PILOTO))
import piloto_etiquetas as p  # noqa: E402

try:
    import anthropic
except ImportError:  # el modo local no necesita el SDK
    anthropic = None


class _Msg:
    def __init__(self, texto, stop="end_turn"):
        self.content = [type("B", (), {"type": "text", "text": texto})()]
        self.usage = type("U", (), {"input_tokens": 2100, "output_tokens": 60})()
        self.stop_reason = stop


@unittest.skipIf(anthropic is None, "SDK anthropic no instalado")
class LectorSinRed(unittest.TestCase):
    def _lector(self, tmp, tope, respuesta=None, error=None):
        vistos = []

        class Mensajes:
            def create(self_inner, **kw):
                vistos.append(kw)
                if error:
                    raise error
                return respuesta

        class Cliente:
            def __init__(self_inner, **kw):
                self.assertTrue(kw["base_url"].startswith(p.ENDPOINT))
                self_inner.messages = Mensajes()

        with mock.patch.dict(os.environ, {"FOUNDRY_API_KEY": "prueba-sin-red"}), \
                mock.patch.object(anthropic, "AnthropicFoundry", Cliente):
            return p.Lector(Path(tmp), tope), vistos

    def test_tope_cache_y_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            lector, vistos = self._lector(tmp, 2, _Msg('{"estado": "legible", "precio": "$19.00", '
                                                       '"texto_etiqueta": "x", "asociacion": "coincide"}'))
            r1 = lector.leer(b"prod", b"vista1", {"capture_id": "X", "origen": "lote", "variante": "A"})
            r2 = lector.leer(b"prod", b"vista1", {"capture_id": "X", "origen": "lote", "variante": "A"})
            lector.leer(b"prod", b"vista2", {"capture_id": "X", "origen": "lote", "variante": "B"})
            r4 = lector.leer(b"prod", b"vista3", {"capture_id": "X", "origen": "lote", "variante": "C"})
            self.assertEqual(r1["precio_leido"], 19.0)
            self.assertEqual(r2["llamadas"], 0)          # caché
            self.assertIsNone(r4)                         # tope de 2 llamadas nuevas
            self.assertEqual(len(vistos), 2)
            textos = {kw["messages"][0]["content"][0]["text"] for kw in vistos}
            self.assertEqual(textos, {p.PROMPT})          # mismo prompt, sin precio reportado
            self.assertTrue((Path(tmp) / "consumo.jsonl").exists())

    def test_error_de_autenticacion_corta_la_fase(self):
        err = anthropic.AuthenticationError.__new__(anthropic.AuthenticationError)
        with tempfile.TemporaryDirectory() as tmp:
            lector, vistos = self._lector(tmp, 50, error=err)
            r = lector.leer(b"p", b"v", {"capture_id": "X", "origen": "lote", "variante": "A"})
            self.assertEqual(r["estado_lectura"], "error_llamada")
            self.assertIsNone(lector.leer(b"p", b"w", {"capture_id": "X", "origen": "lote", "variante": "B"}))
            self.assertEqual(len(vistos), 1)
            self.assertTrue(lector.abortado)

    def test_rechazo_y_respuesta_truncada(self):
        with tempfile.TemporaryDirectory() as tmp:
            lector, _ = self._lector(tmp, 5, _Msg("", stop="refusal"))
            r = lector.leer(b"p", b"v", {"capture_id": "X", "origen": "lote", "variante": "A"})
            self.assertEqual(r["estado_lectura"], "rechazo_modelo")
        with tempfile.TemporaryDirectory() as tmp:
            lector, _ = self._lector(tmp, 5, _Msg('{"estado": "legible", "precio": 4', stop="max_tokens"))
            r = lector.leer(b"p", b"v", {"capture_id": "X", "origen": "lote", "variante": "A"})
            self.assertEqual(r["estado_lectura"], "json_invalido")


if __name__ == "__main__":
    unittest.main(verbosity=2)
