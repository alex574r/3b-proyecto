"""Lectura de registros persistidos y decisiones humanas del portal."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone


def leer(path):
    contenido = path.read_bytes()
    caso = json.loads(contenido)
    caso["revision"] = hashlib.sha256(contenido).hexdigest()
    caso["recibida"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return caso


def conectar(carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(carpeta.parent / "auditoria.sqlite")
    db.execute("""CREATE TABLE IF NOT EXISTS resoluciones (
        captura TEXT, revision TEXT, decision TEXT, PRIMARY KEY (captura, revision))""")
    return db


def listar(carpeta):
    with closing(conectar(carpeta)) as db:
        decisiones = {(cid, rev): json.loads(dec) for cid, rev, dec in
                      db.execute("SELECT captura, revision, decision FROM resoluciones")}
    casos = []
    for path in carpeta.glob("*.json"):
        caso = leer(path)
        caso["auditoria"] = decisiones.get((caso["capture_id"], caso["revision"]))
        casos.append(caso)
    return sorted(casos, key=lambda caso: caso["recibida"], reverse=True)


def resolver(carpeta, cid, solicitud):
    path = carpeta / (cid + ".json")
    if not path.is_file():
        return 404, {"error": "Captura no encontrada"}
    caso = leer(path)
    if caso["decision_esperada"] != "revision_manual" or caso["revision"] != solicitud.get("revision"):
        return 409, {"error": "El caso cambió. Actualiza la bandeja."}
    estado = solicitud.get("estado")
    motivo, nota = solicitud.get("motivo", ""), solicitud.get("nota", "")
    if (estado not in ("aprobada", "rechazada") or not isinstance(motivo, str)
            or not isinstance(nota, str) or len(motivo) > 160 or len(nota) > 2000
            or (estado == "rechazada" and not (motivo.strip() and nota.strip()))):
        return 400, {"error": "Resolución inválida"}
    decision = {"estado": estado, "motivo": motivo.strip(), "nota": nota.strip(),
                "hora": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with closing(conectar(carpeta)) as db, db:
            db.execute("INSERT INTO resoluciones VALUES (?, ?, ?)",
                       (cid, caso["revision"], json.dumps(decision)))
    except sqlite3.IntegrityError:
        return 409, {"error": "La captura ya tiene una resolución. Actualiza la bandeja."}
    return 201, decision
