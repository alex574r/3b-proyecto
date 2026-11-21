"""CLI: python run.py --data <capturas.json> --images <carpeta con imagenes/> --out <salida>

Escribe un JSON por captura en <out>/<id>.json (reanudable), rasgos de depuración en <out>/debug/,
tokens en <out>/usage.jsonl y el consolidado en <out>/resultados.json.
"""
import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from engine import decide, output, vision
from engine.data import image_paths, load_captures
from engine.local_checks import analyze


def process(cap, args, client):
    cid = cap["capture_id"]
    out_file = args.out / f"{cid}.json"
    dbg_file = args.out / "debug" / f"{cid}.json"
    if args.redecide and dbg_file.exists():  # recalcular decisión con local+vision guardados, sin tokens
        dbg = json.loads(dbg_file.read_text(encoding="utf-8"))
        if dbg.get("vision") is not None:
            res = decide.decide(cap, dbg["local"], dbg["vision"])
            out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
            return res
    if out_file.exists():  # reanudar
        return json.loads(out_file.read_text(encoding="utf-8"))
    dbg = {}
    try:
        paths = image_paths(cap, args.images)
        local = dbg["local"] = analyze(paths)
        vis = dbg["vision"] = None if client is None else vision.extract(cap, paths, client, args.out / "usage.jsonl")
        res = decide.decide(cap, local, vis)
        errs = output.validate(res)
        if errs:
            raise ValueError(f"salida inválida: {errs}")
    except Exception as e:  # noqa: BLE001 - nunca dejar una captura sin JSON válido
        res = output.fallback(cid, f"{type(e).__name__}: {e}")
        dbg["error"] = str(e)
    dbg_file.write_text(json.dumps(dbg, ensure_ascii=False, indent=1), encoding="utf-8")
    out_file.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("salida"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-llm", action="store_true", help="solo chequeos locales; no llama al endpoint")
    ap.add_argument("--redecide", action="store_true",
                    help="recalcula decisiones desde debug/ (respuestas de Haiku ya guardadas) sin llamar al endpoint")
    args = ap.parse_args()

    (args.out / "debug").mkdir(parents=True, exist_ok=True)
    caps = load_captures(args.data)[: args.limit]
    client = None if args.no_llm or args.redecide else vision.make_client()

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(lambda c: process(c, args, client), caps))

    (args.out / "resultados.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(Counter(r["decision"] for r in results), "| errores:", sum(r["reason_code"] == "ERROR_PROCESAMIENTO" for r in results))
    usage = args.out / "usage.jsonl"
    if usage.exists():
        rows = [json.loads(line) for line in usage.read_text(encoding="utf-8").splitlines()]
        print("tokens entrada/salida:", sum(r["input_tokens"] for r in rows), sum(r["output_tokens"] for r in rows),
              "| llamadas:", len(rows))


if __name__ == "__main__":
    sys.exit(main())
