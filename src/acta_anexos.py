"""Extrae con el modelo local los anexos del acta: personeros firmantes y texto de OBSERVACIONES (impugnaciones).

Uso: uv run --group viz python src/acta_anexos.py [mesa ...] -> data/extraido/anexos/<mesa>.json + reports/anexos_ventanilla.csv
"""
import base64
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import acta_filas as af  # noqa: E402
import ocr_local as o  # noqa: E402

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "extraido" / "anexos"
PROMPT_PERS = (
    "This is the right side of a Peruvian tally sheet (acta de escrutinio). Read the handwritten text inside the boxes "
    'under "FIRMA Y DATOS DE PERSONEROS". For each personero box output the organization written in "ORG. POLIT." '
    '(null if the box is empty). Answer ONLY JSON: {"personeros": ["org1"|null, "org2"|null, ...]}'
)
PROMPT_OBS = (
    "This is the bottom of a Peruvian tally sheet. Transcribe EXACTLY the handwritten text next to OBSERVACIONES "
    '(after the arrow). If there is nothing written, answer null. Answer ONLY JSON: {"observaciones": "texto"|null}'
)


def _leer(img: Image.Image, prompt: str) -> dict:
    import io
    import urllib.request
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    cuerpo = json.dumps({"model": o.MODELO, "prompt": prompt, "images": [base64.b64encode(buf.getvalue()).decode()],
                         "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    for _ in range(2):
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=cuerpo,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            texto = json.loads(r.read())["response"]
        try:
            return json.loads(texto)
        except json.JSONDecodeError:
            continue
    return {"_raw": texto[:2000]}


def procesar(pdf: Path) -> dict:
    mesa = pdf.name[:6]
    destino = OUT / f"{mesa}.json"
    if destino.exists():
        return json.loads(destino.read_text())
    arr = af._arr(pdf)
    h, w = arr.shape
    im = Image.fromarray(arr)
    pers = im.crop((int(0.62 * w), int(0.36 * h), w, int(0.84 * h)))
    escala = 1500 / pers.height
    pers = pers.resize((int(pers.width * escala), 1500))
    obs = im.crop((0, int(0.955 * h), w, h))
    out = {"personeros": _leer(pers, PROMPT_PERS).get("personeros"),
           "observaciones": _leer(obs, PROMPT_OBS).get("observaciones")}
    destino.write_text(json.dumps(out, ensure_ascii=False))
    return out


def main(filtros: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdfs = [p for p in sorted(o.PDFS.glob("*_escrutinio.pdf")) if not filtros or p.name[:6] in filtros]
    nuevas = [p for p in pdfs if not (OUT / f"{p.name[:6]}.json").exists()]
    print(f"actas: {len(pdfs)} (nuevas: {len(nuevas)})", flush=True)
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(procesar, nuevas))
    import csv
    filas = []
    for pdf in pdfs:
        d = json.loads((OUT / f"{pdf.name[:6]}.json").read_text())
        pers = d.get("personeros") or []
        filas.append({"mesa": pdf.name[:6], "personeros": " | ".join(str(p) for p in pers if p),
                      "observaciones": d.get("observaciones") or ""})
    with (ROOT / "reports" / "anexos_ventanilla.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    con_obs = sum(1 for f in filas if f["observaciones"])
    print(f"con observaciones: {con_obs} / {len(filas)} -> reports/anexos_ventanilla.csv", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
