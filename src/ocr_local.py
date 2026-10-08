"""OCR local de la columna DISTRITAL de las actas con Ollama (qwen2.5vl:7b). Segunda lectura barata, no reemplaza al OCR principal.

Recorta la imagen: nombres de organizaciones + solo la columna distrital (quita la provincial para no confundir columnas).
Valida la suma contra el total de emitidos escrito en el acta y compara con lo digitado por ONPE.
Calibración (40 actas JEE Ventanilla, 8-oct-2026): se leen los dígitos como texto y se parsean (los ceros a la izquierda
"008" ya no se pierden). Sirve para filtrar, NO como prueba: toda diferencia se verifica a ojo.
Uso: uv run --group viz python src/ocr_local.py [mesa ...]  -> data/extraido/ocr_qwen/<mesa>.json + reports/ocr_qwen_ventanilla.csv
"""
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent.parent
PDFS = ROOT / "data" / "actas_pdf" / "240106" / "4"
OUT = ROOT / "data" / "extraido" / "ocr_qwen"
MODELO = "qwen2.5vl:7b"
FILAS = {"RP": "RENOVACIÓN POPULAR PERÚ", "PPC": "PARTIDO POPULAR CRISTIANO - PPC", "FP": "FUERZA POPULAR",
         "AN": "AHORA NACIÓN - AN", "SP": "PARTIDO DEMOCRÁTICO SOMOS PERÚ", "blancos": "VOTOS EN BLANCO",
         "nulos": "VOTOS NULOS", "impugnados": "VOTOS IMPUGNADOS"}
PROMPT = (
    "This is part of a Peruvian election tally sheet. Left: row labels. Right: ONE column of HANDWRITTEN vote counts; "
    "each number sits in up to 3 small boxes. Read the number of each row by concatenating ALL the digit boxes of that "
    "row. Examples: boxes 0-0-8 -> 8; boxes 1-3-2 -> 132; boxes 0-9-1 -> 91; all boxes empty -> null. "
    "Rows, top to bottom: RENOVACION POPULAR, (dark/blocked row), PARTIDO POPULAR CRISTIANO, (dark), FUERZA POPULAR, "
    "(dark), AHORA NACION, (dark), SOMOS PERU, VOTOS EN BLANCO, VOTOS NULOS, VOTOS IMPUGNADOS, TOTAL DE VOTOS EMITIDOS. "
    "Do not guess or fix sums. Answer ONLY JSON with the digits as written: "
    '{"RP":"digits"|null,"PPC":"digits"|null,"FP":"digits"|null,"AN":"digits"|null,"SP":"digits"|null,'
    '"blancos":"digits"|null,"nulos":"digits"|null,"impugnados":"digits"|null,"total":"digits"|null}'
)


def imagen_recortada(pdf: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "p.png"
        subprocess.run(["sips", "-s", "format", "png", "--resampleWidth", "1600", str(pdf), "--out", str(png)],
                       check=True, capture_output=True)
        im = Image.open(png).convert("L")
    w, h = im.size
    y0, y1 = int(0.26 * h), int(0.92 * h)             # desde RP hasta TOTAL EMITIDOS
    etiquetas = im.crop((int(0.08 * w), y0, int(0.37 * w), y1))
    distrital = im.crop((int(0.525 * w), y0, int(0.625 * w), y1))
    lienzo = Image.new("L", (etiquetas.width + distrital.width + 10, etiquetas.height), 255)
    lienzo.paste(etiquetas, (0, 0))
    lienzo.paste(distrital, (etiquetas.width + 10, 0))
    buf = io.BytesIO()
    lienzo.save(buf, format="PNG")
    return buf.getvalue()


def _num(v) -> int | None:
    """Valor del JSON del modelo -> entero o None. Acepta "008" (ceros a la izquierda) y descarta ruido."""
    if v is None or isinstance(v, int):
        return v
    digitos = re.sub(r"\D", "", str(v))
    return int(digitos) if digitos else None


def leer(pdf: Path) -> dict:
    cuerpo = json.dumps({"model": MODELO, "prompt": PROMPT, "images": [base64.b64encode(imagen_recortada(pdf)).decode()],
                         "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        crudo = json.loads(json.loads(r.read())["response"])
    return {k: _num(v) for k, v in crudo.items()}


def onpe_digitado() -> dict[str, dict]:
    out = {}
    for ln in (ROOT / "data" / "raw" / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        for a in r["data"]:
            if a["idUbigeo"] == 240106 and a["idEleccion"] == 4:
                v = {x["adDescripcion"]: x["adVotos"] for x in a["detalle"] or []}
                out[a["codigoMesa"]] = {k: v.get(n) for k, n in FILAS.items()}
    return out


def main(mesas: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = [p for p in sorted(PDFS.glob("*_escrutinio.pdf")) if not mesas or p.name[:6] in mesas]
    onpe = onpe_digitado()
    filas = []
    for i, pdf in enumerate(pdfs, 1):
        mesa = pdf.name[:6]
        destino = OUT / f"{mesa}.json"
        if destino.exists():
            ocr = json.loads(destino.read_text())
        else:
            t0 = time.time()
            ocr = leer(pdf)
            ocr["_segundos"] = round(time.time() - t0, 1)
            destino.write_text(json.dumps(ocr))
        vals = [ocr.get(k) for k in FILAS]
        suma = sum(v for v in vals if isinstance(v, int))
        fila = {"mesa": mesa, **{f"ocr_{k}": ocr.get(k) for k in FILAS}, "ocr_total": ocr.get("total"),
                "suma_ocr": suma, "cuadra": suma == ocr.get("total"),
                **{f"onpe_{k}": onpe.get(mesa, {}).get(k) for k in ("RP", "SP")}}
        fila["difiere_RP"] = fila["ocr_RP"] != fila["onpe_RP"]
        fila["difiere_SP"] = fila["ocr_SP"] != fila["onpe_SP"]
        filas.append(fila)
        print(f"[{i}/{len(pdfs)}] {mesa} RP={ocr.get('RP')} SP={ocr.get('SP')} total={ocr.get('total')} suma={suma} "
              f"{'OK' if fila['cuadra'] else 'NO CUADRA'} ({ocr.get('_segundos', 'cache')} s)", flush=True)
    import csv
    with (ROOT / "reports" / "ocr_qwen_ventanilla.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


if __name__ == "__main__":
    main(sys.argv[1:])
