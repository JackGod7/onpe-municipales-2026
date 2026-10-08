"""Doble lectura local de cada acta (dos prompts de estilos distintos) para filtrar diferencias contra la digitación ONPE.

Pasada A: pide enteros con null en celdas vacías (buen alineamiento de filas).
Pasada B: pide los dígitos como texto (conserva ceros a la izquierda: "008" = 8).
Una canditura solo se abre a verificación a ojo cuando alguna pasada la señala; el script no decide, filtra.
Uso: uv run --group viz python src/ocr_doble.py [mesa ...]  -> data/extraido/ocr_doble/<mesa>.json + reports/ocr_doble_ventanilla.csv
"""
import base64
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ocr_local as o  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "extraido" / "ocr_doble"
CAMPOS = ["RP", "PPC", "FP", "AN", "SP", "blancos", "nulos", "impugnados"]
PROMPT_A = (
    "This is part of a Peruvian election tally sheet. Left: row labels. Right: one column of HANDWRITTEN vote counts "
    "(each digit in its own small box). Read the handwritten number in each row. Rows, top to bottom: "
    "RENOVACION POPULAR, (dark/blocked row), PARTIDO POPULAR CRISTIANO, (dark), FUERZA POPULAR, (dark), AHORA NACION, "
    "(dark), SOMOS PERU, VOTOS EN BLANCO, VOTOS NULOS, VOTOS IMPUGNADOS, TOTAL DE VOTOS EMITIDOS. "
    "If a box is empty write null, not 0. Do not guess or fix sums. Answer ONLY JSON: "
    '{"RP":int|null,"PPC":int|null,"FP":int|null,"AN":int|null,"SP":int|null,"blancos":int|null,"nulos":int|null,'
    '"impugnados":int|null,"total":int|null}'
)
PROMPT_B = o.PROMPT


def leer(pdf: Path, prompt: str) -> dict:
    img = o.imagen_recortada(pdf)
    cuerpo = json.dumps({"model": o.MODELO, "prompt": prompt, "images": [base64.b64encode(img).decode()],
                         "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=cuerpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        crudo = json.loads(json.loads(r.read())["response"])
    return {k: o._num(v) for k, v in crudo.items()}


def digitado() -> tuple[dict, dict]:
    """{mesa: {campo: valor}} y {mesa: estado} desde mesas.jsonl (elección 4 de Ventanilla)."""
    por_mesa, estado = {}, {}
    for ln in (ROOT / "data" / "raw" / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        for a in r["data"]:
            if a["idUbigeo"] != 240106 or a["idEleccion"] != 4:
                continue
            v = {x["adDescripcion"]: x["adVotos"] for x in a["detalle"] or []}
            por_mesa[a["codigoMesa"]] = {k: v.get(n) for k, n in o.FILAS.items()} | {"total": a["totalVotosEmitidos"]}
            estado[a["codigoMesa"]] = a["codigoEstadoActa"]
    return por_mesa, estado


def _v(d: dict, k: str) -> int:
    return d.get(k) or 0


def analizar(mesa: str, a: dict, b: dict, onpe: dict, estado: str) -> dict:
    suma_a, suma_b = sum(_v(a, k) for k in CAMPOS), sum(_v(b, k) for k in CAMPOS)
    tot_a, tot_b = a.get("total"), b.get("total")
    cons_a, cons_b = tot_a is not None and suma_a == tot_a, tot_b is not None and suma_b == tot_b
    iguales = all(_v(a, k) == _v(b, k) for k in CAMPOS) and _v(a, "total") == _v(b, "total")
    dif_ab = ",".join(k for k in CAMPOS if _v(a, k) != _v(b, k)) or ("total" if _v(a, "total") != _v(b, "total") else "")
    if cons_a or cons_b:
        if cons_a and cons_b and not iguales:
            veredicto, motivo = "dudoso", "ambas pasadas cuadran pero difieren entre sí"
        else:
            ref, nombre = (a, "A") if cons_a else (b, "B")
            difs = [k for k in CAMPOS if _v(ref, k) != _v(onpe, k)]
            if difs:
                veredicto, motivo = "candidato_onpe", f"pasada {nombre} cuadra (suma {suma_a if cons_a else suma_b}); difiere de ONPE: {','.join(difs)}"
            else:
                veredicto, motivo = "ok", ""
    elif tot_a is not None and tot_b is not None:
        veredicto = "candidato_suma"
        motivo = f"acta no cuadra en ninguna pasada: A {suma_a}/{tot_a}, B {suma_b}/{tot_b}"
    else:
        veredicto, motivo = "dudoso", "sin total legible"
    dif_onpe = ",".join(k for k in CAMPOS if _v(a, k) == _v(b, k) != _v(onpe, k))
    fila = {"mesa": mesa, "estado": estado, "suma_a": suma_a, "total_a": tot_a, "ok_a": cons_a,
            "suma_b": suma_b, "total_b": tot_b, "ok_b": cons_b, "dif_ab": dif_ab, "dif_onpe": dif_onpe,
            "veredicto": veredicto, "motivo": motivo}
    for k in CAMPOS + ["total"]:
        fila[f"a_{k}"], fila[f"b_{k}"] = a.get(k), b.get(k)
    return fila


def procesar(pdf: Path) -> dict:
    mesa = pdf.name[:6]
    destino = OUT / f"{mesa}.json"
    if destino.exists():
        d = json.loads(destino.read_text())
        a, b = d["A"], d["B"]
    else:
        t0 = time.time()
        a, b = leer(pdf, PROMPT_A), leer(pdf, PROMPT_B)
        destino.write_text(json.dumps({"A": a, "B": b, "_segundos": round(time.time() - t0, 1)}))
    return a, b


def main(filtros: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = [p for p in sorted(o.PDFS.glob("*_escrutinio.pdf")) if not filtros or p.name[:6] in filtros]
    onpe, estados = digitado()
    filas = []
    pendientes = [p for p in pdfs if not (OUT / f"{p.name[:6]}.json").exists()]
    print(f"actas: {len(pdfs)} (nuevas: {len(pendientes)})", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        resultados = list(ex.map(procesar, pendientes))
    for pdf, (a, b) in zip(pendientes, resultados, strict=False):
        filas.append(analizar(pdf.name[:6], a, b, onpe.get(pdf.name[:6], {}), estados.get(pdf.name[:6], "?")))
    for pdf in pdfs:
        if (OUT / f"{pdf.name[:6]}.json").exists() and pdf not in pendientes:
            d = json.loads((OUT / f"{pdf.name[:6]}.json").read_text())
            filas.append(analizar(pdf.name[:6], d["A"], d["B"], onpe.get(pdf.name[:6], {}), estados.get(pdf.name[:6], "?")))
    filas.sort(key=lambda f: f["mesa"])
    import csv
    with (ROOT / "reports" / "ocr_doble_ventanilla.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    from collections import Counter
    for e in ("C", "E"):
        sub = [f for f in filas if f["estado"] == e]
        c = Counter(f["veredicto"] for f in sub)
        print(f"estado {e}: {len(sub)} -> {dict(c)}", flush=True)
    print("csv: reports/ocr_doble_ventanilla.csv", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
