"""Costo operativo sobre el set de desarrollo: python evaluate.py --data capturas.json --results salida/resultados.json

shortcut: réplica de la tabla del reto. Supuesto abierto: la etiqueta `revision_manual` se trata como ambigua
(manual=1, aprobar=10, rechazar=3). Sustituir por el script oficial cuando se descargue.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

COST = {  # (esperada, predicha) -> puntos
    ("aprobada", "aprobada"): 0, ("aprobada", "rechazada"): 3, ("aprobada", "revision_manual"): 1,
    ("rechazada", "rechazada"): 0, ("rechazada", "aprobada"): 10, ("rechazada", "revision_manual"): 1,
    ("revision_manual", "revision_manual"): 1, ("revision_manual", "aprobada"): 10, ("revision_manual", "rechazada"): 3,
}


def evaluate(expected, predicted):
    """expected/predicted: dict capture_id -> decision. Devuelve métricas."""
    pairs = [(expected[c], predicted[c]) for c in expected if c in predicted]
    approved = [e for e, p in pairs if p == "aprobada"]
    return {
        "n": len(pairs),
        "costo": sum(COST[x] for x in pairs),
        "precision_aprobaciones": (approved.count("aprobada") / len(approved)) if approved else None,
        "confusion": dict(Counter(pairs)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    a = ap.parse_args()
    exp = {c["capture_id"]: c["decision_esperada"] for c in json.loads(a.data.read_text(encoding="utf-8-sig"))}
    pred = {r["capture_id"]: r["decision"] for r in json.loads(a.results.read_text(encoding="utf-8"))}
    m = evaluate(exp, pred)
    print(f"n={m['n']}  costo={m['costo']}  precisión aprobaciones={m['precision_aprobaciones']}")
    for (e, p), n in sorted(m["confusion"].items()):
        print(f"  esperada={e:16} predicha={p:16} {n}")


if __name__ == "__main__":
    main()
