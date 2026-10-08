"""Segmenta la tabla del acta por su rejilla (14 filas de paso uniforme) y compone la imagen de las 9 filas objetivo numeradas.

Uso desde otro script: filas(png) -> lista de (y0, y1) de las 14 filas; recorte_objetivo(pdf) -> bytes PNG con las 9 filas.
"""
import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# índice 0-based de las 9 filas objetivo dentro de las 14 de la tabla
OBJETIVO = [1, 3, 5, 7, 9, 10, 11, 12, 13]  # RP, PPC, FP, AN, SP, blancos, nulos, impugnados, total
N_FILAS = 14


def _arr(pdf: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "p.png"
        subprocess.run(["sips", "-s", "format", "png", "--resampleWidth", "2000", str(pdf), "--out", str(png)],
                       check=True, capture_output=True)
        return np.asarray(Image.open(png).convert("L"))


def filas(arr: np.ndarray) -> list[tuple[int, int]]:
    """14 bandas (y0, y1) de la tabla. Usa los rellenos grises para estimar el paso y la línea del encabezado."""
    h, w = arr.shape
    zona = arr[int(0.18 * h):int(0.95 * h), int(0.50 * w):int(0.64 * w)] < 170
    prof = zona.mean(axis=1)
    rellenos, i = [], 0
    while i < len(prof):
        if prof[i] > 0.55:
            j = i
            while j < len(prof) and prof[j] > 0.55:
                j += 1
            if j - i > 50:
                rellenos.append(int(0.18 * h) + (i + j - 1) // 2)
            i = j
        else:
            i += 1
    if len(rellenos) < 3:
        return []
    paso = float(np.median(np.diff(rellenos))) / 2  # las filas grises van de dos en dos
    top = int(rellenos[0] - 0.55 * paso)
    return [(int(top + k * paso), int(top + (k + 1) * paso)) for k in range(N_FILAS)]


def columnas(arr: np.ndarray) -> list[int]:
    """x de las líneas verticales de la tabla (izquierda, fin de etiquetas, divisoria provincial/distrital, derecha)."""
    h, w = arr.shape
    zona = arr[int(0.25 * h):int(0.82 * h), :int(0.70 * w)] < 150
    prof = zona.mean(axis=0)
    xs = [int(v) for v in np.where(prof > 0.55)[0]]
    grupos, i = [], 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] - xs[j] <= 3:
            j += 1
        grupos.append((xs[i] + xs[j]) // 2)
        i = j + 1
    return grupos


def _cerca(xs: list[int], objetivo: float) -> int | None:
    return min(xs, key=lambda x: abs(x - objetivo)) if xs else None


def recorte_objetivo(pdf: Path) -> bytes:
    """PNG con las 9 filas objetivo: etiqueta + columna distrital, separadas por líneas negras y en orden conocido."""
    arr = _arr(pdf)
    h, w = arr.shape
    im = Image.fromarray(arr).convert("RGB")
    bandas = filas(arr)
    if not bandas:
        return b""
    cols = columnas(arr)
    etq_izq = _cerca([x for x in cols if x < 0.15 * w], 0.083 * w)
    etq_der = _cerca([x for x in cols if 0.35 * w < x < 0.50 * w], 0.437 * w)
    div = _cerca([x for x in cols if 0.48 * w < x < 0.56 * w], 0.526 * w)
    der = _cerca([x for x in cols if 0.58 * w < x < 0.68 * w], 0.616 * w)
    etq_x0 = (etq_izq or int(0.083 * w)) + 4
    etq_x1 = (etq_der or int(0.437 * w)) - 4
    vot_x0 = (div or int(0.526 * w)) + 5
    vot_x1 = (der or int(0.616 * w)) - 5
    ancho = (etq_x1 - etq_x0) + (vot_x1 - vot_x0) + 8
    alto = sum(bandas[k][1] - bandas[k][0] + 4 for k in OBJETIVO)
    lienzo = Image.new("RGB", (ancho, alto), (255, 255, 255))
    d = ImageDraw.Draw(lienzo)
    y = 0
    for k in OBJETIVO:
        y0, y1 = bandas[k]
        etiqueta = im.crop((etq_x0, y0, etq_x1, y1))
        votos = im.crop((vot_x0, y0, vot_x1, y1))
        lienzo.paste(etiqueta, (0, y))
        lienzo.paste(votos, (etiqueta.width + 8, y))
        d.line([(0, y + etiqueta.height + 1), (ancho, y + etiqueta.height + 1)], fill=(0, 0, 0), width=3)
        y += etiqueta.height + 4
    buf = io.BytesIO()
    lienzo.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    out = Path("/var/folders/hl/cqpm76c97kz568gc3fdv8ftc0000gn/T/opencode") / f"objetivo_{sys.argv[1]}.png"
    out.write_bytes(recorte_objetivo(Path(sys.argv[2])))
    print(out)
