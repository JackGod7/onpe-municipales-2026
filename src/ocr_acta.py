"""Lectura local de la columna distrital por filas segmentadas y numeradas (9 bandas), un solo pase por acta.

Recorta la tabla del acta por su rejilla (src/acta_filas.py), pide los 9 valores a qwen2.5vl y compara con la digitación ONPE.
Uso: uv run --group viz python src/ocr_acta.py [mesa ...] -> data/extraido/ocr_acta/<mesa>.json + reports/ocr_acta_ventanilla.csv
"""
import base64
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import acta_filas  # noqa: E402
import ocr_doble  # noqa: E402
import ocr_local as o  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "extraido" / "ocr_acta"
CAMPOS = ["RP", "PPC", "FP", "AN", "SP", "blancos", "nulos", "impugnados", "total"]
PROMPT = (
    "Image: 9 strips of ONE column (municipal distrital) of a Peruvian tally sheet, top to bottom, separated by black "
    "lines, in this exact order: RENOVACION POPULAR, PARTIDO POPULAR CRISTIANO, FUERZA POPULAR, AHORA NACION, "
    "SOMOS PERU, VOTOS EN BLANCO, VOTOS NULOS, VOTOS IMPUGNADOS, TOTAL DE VOTOS EMITIDOS. Each strip has the row title "
    "on the left and a HANDWRITTEN number in small digit boxes on the right. A number may have 2 or 3 digits: "
    "concatenate ALL digit boxes of that strip into one number (0-0-8 -> 8; 1-4-7 -> 147). If the boxes are empty or "
    "shaded with no number, write null. Do not fix or guess sums. "
    'Answer ONLY JSON with exactly 9 values in the order above: {"filas":[9 values]}'
)


def leer(pdf: Path) -> dict | None:
    img = acta_filas.recorte_objetivo(pdf)
    if not img:
        return None
    cuerpo = json.dumps({"model": o.MODELO, "prompt": PROMPT, "images": [base64.b64encode(img).decode()],
                         "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=cuerpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        crudo = json.loads(json.loads(r.read())["response"])
    vals = crudo.get("filas") if isinstance(crudo, dict) else crudo
    if not isinstance(vals, list) or len(vals) != 9:
        return {"_crudo": crudo}
    return dict(zip(CAMPOS, (o._num(v) for v in vals), strict=False))


def analizar(mesa: str, ocr: dict, onpe: dict, estado: str) -> dict:
    fila = {"mesa": mesa, "estado": estado, **{k: ocr.get(k) for k in CAMPOS}}
    if "_crudo" in ocr:
        fila |= {"suma": None, "cuadra": None, "dif_onpe": "", "veredicto": "dudoso_formato", "motivo": "respuesta fuera de formato"}
        return fila
    base = {k: (ocr.get(k) or 0) for k in CAMPOS[:-1]}
    onpe_v = {k: (onpe.get(k) or 0) for k in CAMPOS[:-1]}
    suma = sum(base.values())
    total = ocr.get("total")
    dif = [k for k in CAMPOS[:-1] if base[k] != onpe_v[k]]
    fila |= {"suma": suma, "cuadra": total is not None and suma == total, "dif_onpe": ",".join(dif)}
    if total is None:
        fila |= {"veredicto": "dudoso", "motivo": "sin total legible"}
        return fila
    if suma == total:
        if dif:
            fila |= {"veredicto": "candidato_onpe", "motivo": f"acta cuadra pero difiere de ONPE: {','.join(dif)}"}
        else:
            fila |= {"veredicto": "ok", "motivo": ""}
        return fila
    # el acta no cuadra: probar si el descuadre se explica por lectura OCR mala (usar valor ONPE en 1 o 2 campos)
    fix = [k for k in dif if suma - base[k] + onpe_v[k] == total]
    if not fix:
        for i, k1 in enumerate(dif):
            for k2 in dif[i + 1:]:
                if suma - base[k1] + onpe_v[k1] - base[k2] + onpe_v[k2] == total:
                    fix = [k1, k2]
                    break
            if fix:
                break
    if fix:
        det = ", ".join(f"{k}: OCR {base[k]} vs ONPE {onpe_v[k]}" for k in fix)
        fila |= {"veredicto": "ok_ruido_ocr", "motivo": f"con ONPE cuadra ({det})"}
    else:
        fila |= {"veredicto": "candidato_suma", "motivo": f"acta no cuadra: suma {suma} vs total {total}"}
    return fila


def procesar(pdf: Path) -> dict | None:
    mesa = pdf.name[:6]
    destino = OUT / f"{mesa}.json"
    if destino.exists():
        return json.loads(destino.read_text())
    t0 = time.time()
    ocr = leer(pdf)
    if ocr is not None:
        ocr["_segundos"] = round(time.time() - t0, 1)
        destino.write_text(json.dumps(ocr))
    return ocr


def main(filtros: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = [p for p in sorted(o.PDFS.glob("*_escrutinio.pdf")) if not filtros or p.name[:6] in filtros]
    onpe, estados = ocr_doble.digitado()
    nuevas = [p for p in pdfs if not (OUT / f"{p.name[:6]}.json").exists()]
    print(f"actas: {len(pdfs)} (nuevas: {len(nuevas)})", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(procesar, nuevas))
    filas = []
    for pdf in pdfs:
        ocr = json.loads((OUT / f"{pdf.name[:6]}.json").read_text())
        filas.append(analizar(pdf.name[:6], ocr, onpe.get(pdf.name[:6], {}), estados.get(pdf.name[:6], "?")))
    import csv
    with (ROOT / "reports" / "ocr_acta_ventanilla.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    from collections import Counter
    for e in ("C", "E"):
        sub = [f for f in filas if f["estado"] == e]
        print(f"estado {e}: {len(sub)} -> {dict(Counter(f['veredicto'] for f in sub))}", flush=True)
    print("csv: reports/ocr_acta_ventanilla.csv", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
