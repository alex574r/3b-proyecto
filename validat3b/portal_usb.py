"""Portal de presentación para un POCO con la APK debug y depuración USB autorizada."""
import argparse
import getpass
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.client import HTTPException, HTTPSConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from server import Handler, ID_RE, IMG_RE, MAX_BODY, PHOTOS

PACKAGE = "com.example.a3bapp"
DB = "databases/3bapp.db"
FOTO = re.compile(r"/data/(?:user/0|data)/com\.example\.a3bapp/files/capturas/(\d+_(?:fachada|producto|etiqueta)\.jpg)")


def leer_adb(comando, *args):
    return subprocess.run([*comando, "exec-out", "run-as", PACKAGE, *args],
                          capture_output=True, timeout=12, check=True).stdout


def historial(comando):
    # Dos copias idénticas evitan combinar el WAL y la base de dos transacciones.
    def archivos_actuales():
        nombres = leer_adb(comando, "ls", "databases").decode().split()
        return [DB, DB + "-wal"] if "3bapp.db-wal" in nombres else [DB]
    archivos = archivos_actuales()
    def instantanea():
        return {Path(f).name: leer_adb(comando, "cat", f) for f in archivos}
    copia = instantanea()
    if copia != instantanea() or archivos != archivos_actuales():
        return []
    with tempfile.TemporaryDirectory() as temporal:
        for nombre, datos in copia.items():
            (Path(temporal) / nombre).write_bytes(datos)
        db = sqlite3.connect(Path(temporal) / "3bapp.db")
        try:
            return db.execute("""SELECT resultadoJson, fachada, producto, etiqueta FROM capturas
                                 WHERE estado = 'ENVIADA' AND resultadoJson IS NOT NULL
                                 ORDER BY creadaEn""").fetchall()
        finally:
            db.close()


def guardar(destino, datos):
    temporal = destino.with_suffix(".tmp")
    temporal.write_bytes(datos)
    temporal.replace(destino)


def copiar_fila(comando, salida, fila):
    registro = json.loads(fila[0])
    cid = registro.get("capture_id")
    if not isinstance(cid, str) or not ID_RE.fullmatch(cid):
        return
    destino = salida / "json" / (cid + ".json")
    datos = fila[0].encode("utf-8")
    if destino.is_file() and destino.read_bytes() == datos:
        return
    for tipo, ruta in zip(PHOTOS, fila[1:]):
        archivo = FOTO.fullmatch(ruta)
        if not archivo:
            raise ValueError("Ruta de evidencia inesperada")
        foto = leer_adb(comando, "cat", "files/capturas/" + archivo[1])
        if not foto.startswith(b"\xff\xd8"):
            raise ValueError("Foto incompleta")
        guardar(salida / "imagenes" / f"{cid}_{tipo}.jpg", foto)
    guardar(destino, datos)
    print("Captura disponible:", cid, flush=True)


def sincronizar(comando, salida):
    while True:
        try:
            for fila in historial(comando):
                try:
                    copiar_fila(comando, salida, fila)
                except (ValueError, OSError, subprocess.SubprocessError) as error:
                    print("Evidencia pendiente:", type(error).__name__, flush=True)
        except (OSError, sqlite3.Error, subprocess.SubprocessError) as error:
            print("Esperando al POCO:", type(error).__name__, flush=True)
        time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb", help="Ruta a adb (por defecto se busca en PATH)")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--port", type=int, default=18124)
    args = parser.parse_args()
    clave_api = os.environ.pop("VALIDAT3B_TOKEN", "")
    clave = os.environ.pop("VALIDAT3B_AUDIT_TOKEN", "") or clave_api
    if not clave and sys.stdin.isatty():
        clave = getpass.getpass("Credencial de acceso al portal USB: ").strip()
    if not clave:
        parser.error("Define VALIDAT3B_AUDIT_TOKEN o VALIDAT3B_TOKEN para ejecutar sin terminal")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.serial):
        parser.error("Número de serie de dispositivo no válido")
    datos_locales = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    salida = Path(datos_locales) / "Validat3B" / "portal-usb" / args.serial

    class PortalUsb(Handler):
        audit_token = clave
        json_dir = salida / "json"
        img_dir = salida / "imagenes"

        def end_headers(self):
            if clave_api and self.path == "/auditoria/capturas":
                self.send_header("X-Consulta-Folio", "1")
            super().end_headers()

        def do_GET(self):
            if not self.path.startswith("/auditoria/remota/"):
                return super().do_GET()
            if not self._audit_access():
                return
            ruta = "/imagenes/" + self.path.removeprefix("/auditoria/remota/")
            if not clave_api or not IMG_RE.fullmatch(ruta):
                return self._send(404, {"error": "Evidencia no disponible."})
            conn = HTTPSConnection("api.jamp.digital", timeout=10)
            try:
                conn.request("GET", ruta, headers={"X-Api-Key": clave_api, "User-Agent": "Validat3B-Portal/1.0"})
                respuesta = conn.getresponse()
                if respuesta.status == 404:
                    return self._send(404, {"error": "La API no encontró esta foto. Revisa el folio en Historial."})
                if respuesta.status != 200 or respuesta.getheader("Content-Type", "").split(";")[0] != "image/jpeg":
                    return self._send(502, {"error": "La API no pudo entregar la evidencia."})
                foto = respuesta.read(MAX_BODY + 1)
                if len(foto) > MAX_BODY or not foto.startswith(b"\xff\xd8"):
                    return self._send(502, {"error": "La API devolvió una imagen inválida."})
            except (OSError, HTTPException):
                return self._send(502, {"error": "No se pudo conectar con la API pública."})
            finally:
                conn.close()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(foto)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(foto)

        def _authorized(self):
            return False  # Las fotos privadas de esta copia usan el acceso de auditoría.

        def do_POST(self):
            if self.path.startswith("/auditoria/capturas/"):
                return super().do_POST()
            return self._send(405, {"error": "El análisis se hace desde la app en la API del equipo."})

    for carpeta in (PortalUsb.json_dir, PortalUsb.img_dir):
        carpeta.mkdir(parents=True, exist_ok=True)
    with ThreadingHTTPServer(("127.0.0.1", args.port), PortalUsb) as http:
        threading.Thread(target=sincronizar, args=([args.adb, "-s", args.serial], salida), daemon=True).start()
        http.serve_forever()


if __name__ == "__main__":
    main()
