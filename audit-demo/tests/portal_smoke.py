"""Prueba del portal servido por la API. Requiere Playwright."""
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe

from playwright.sync_api import expect, sync_playwright

backend = Path(__file__).resolve().parents[2] / "validat3b"
sys.path.extend([str(backend), str(backend / "tests")])
from server import Handler
from test_server import call, jpeg_b64


def main():
    with tempfile.TemporaryDirectory() as temp:
        class Local(Handler):
            token = token_urlsafe()
            audit_token = token_urlsafe()
            jwt_secret = None
            json_dir = Path(temp) / "json"
            img_dir = Path(temp) / "imagenes"

        with ThreadingHTTPServer(("127.0.0.1", 0), Local) as api:
            threading.Thread(target=api.serve_forever, daemon=True).start()
            try:
                ejecutar(api.server_port, Local)
            finally:
                api.shutdown()


def ejecutar(port, handler):
    img = jpeg_b64()
    captura = dict(capture_id="APP-QA123", product_name="Prueba", capture_store_name="Prueba",
                   facade_b64=img, product_b64=img, shelf_b64=img)
    code, data = call(port, "/analizar", captura, {"X-Api-Key": handler.token})
    assert code == 200 and data["decision_esperada"] == "revision_manual"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get("QA_BROWSER_PATH"))
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/")
        assert page.url.startswith(f"http://127.0.0.1:{port}/portal/")
        def conectar():
            page.get_by_label("Credencial de auditoría").fill(handler.audit_token)
            page.get_by_role("button", name="Conectar", exact=True).click()
        conectar()
        page.get_by_text("Abrir bandeja", exact=True).click()
        page.get_by_role("link", name="APP-QA123").click()
        page.wait_for_function("document.querySelector('.photo img')?.naturalWidth > 0")
        page.get_by_role("button", name="Aprobar", exact=True).click()
        page.get_by_role("button", name="Confirmar aprobación").click()
        expect(page.get_by_text("Aprobación registrada", exact=True)).to_be_visible()
        page.reload()
        conectar()
        expect(page.get_by_text("Aprobación registrada", exact=True)).to_be_visible()
        page.get_by_role("link", name="Ver demo").click()
        expect(page.get_by_text("Periodo de demostración")).to_be_visible()
        assert not errors, errors
        browser.close()
    print("OK: captura, bandeja, foto, resolución persistida y demo")


if __name__ == "__main__":
    main()
