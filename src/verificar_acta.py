"""Verificación fina local: relee cada fila objetivo del acta en aislamiento (una imagen por fila) con qwen2.5vl.

Uso: uv run --group viz python src/verificar_acta.py <mesa> [mesa2 ...]
Compara: lectura por fila aislada vs lectura por bandas (ocr_acta) vs digitación ONPE.
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import acta_filas as af  # noqa: E402
import ocr_doble  # noqa: E402
import ocr_local as o  # noqa: E402

ROOT = Path(__file__).parent.parent
PROMPT = (
    "Read the handwritten number inside the small digit boxes on the right of this row of a Peruvian tally sheet. "
    "The number may have 2 or 3 digits; concatenate all boxes (0-0-8 -> 8; 1-4-7 -> 147). "
    "If the boxes are empty or shaded with no number, answer null. Answer ONLY JSON: {\"valor\": int|null}"
)


def leer_fila(img: Image.Image) -> int | None:
    buf = __import__("io").BytesIO()
    img.resize((img.width * 3, img.height * 3)).save(buf, format="PNG")
    cuerpo = json.dumps({"model": o.MODELO, "prompt": PROMPT, "images": [base64.b64encode(buf.getvalue()).decode()],
                         "format": "json", "stream": False, "options": {"temperature": 0}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=cuerpo,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        crudo = json.loads(json.loads(r.read())["response"])
    return o._num(crudo.get("valor")) if isinstance(crudo, dict) else None


def main(mesas: list[str]) -> None:
    onpe, estados = ocr_doble.digitado()
    for mesa in mesas:
        pdf = o.PDFS / f"{mesa}_escrutinio.pdf"
        arr = af._arr(pdf)
        h, w = arr.shape
        im = Image.fromarray(arr)
        bandas, cols = af.filas(arr), af.columnas(arr)
        div = af._cerca([x for x in cols if 0.48 * w < x < 0.56 * w], 0.526 * w) or int(0.526 * w)
        der = af._cerca([x for x in cols if 0.58 * w < x < 0.68 * w], 0.616 * w) or int(0.616 * w)
        cache = ROOT / "data" / "extraido" / "ocr_acta" / f"{mesa}.json"
        band = json.loads(cache.read_text()) if cache.exists() else {}
        print(f"--- {mesa} (estado {estados.get(mesa, '?')}) ---")
        for k, i in zip(list(o.FILAS) + ["total"], af.OBJETIVO, strict=False):
            y0, y1 = bandas[i]
            recorte = im.crop((div + 5, y0, der - 5, y1))
            v = leer_fila(recorte)
            print(f"  {k:10} fila={v}  bandas={band.get(k)}  onpe={onpe.get(mesa, {}).get(k)}")


if __name__ == "__main__":
    main(sys.argv[1:])
