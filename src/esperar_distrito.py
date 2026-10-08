"""Sale con 0 cuando todas las mesas de un ubigeo ya están en mesas.jsonl. Uso: esperar_distrito.py 140126"""
import json
import sys
import time
from pathlib import Path

raw = Path(__file__).parent.parent / "data" / "raw"
ub = int(sys.argv[1])
mesas = {r["codigoMesa"] for r in json.loads((raw / f"actas_{ub}.json").read_text())}
while True:
    f = raw / "mesas.jsonl"
    hechas = {json.loads(ln)["mesa"] for ln in f.read_text().splitlines() if ln} if f.exists() else set()
    if not (mesas - hechas):
        print(f"{ub}: completo ({len(mesas)} mesas)")
        break
    time.sleep(60)
