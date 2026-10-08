"""Arma el paquete para el OCR: PDFs + data oficial + prompts + AGENTS.md, con SHA256SUMS. Salida: dist/onpe-ocr-<fecha>.tar.gz

Excluye el perfil de Chrome, los informes de análisis y cualquier .env. Uso: uv run python src/empaquetar.py
"""
import hashlib
import json
import tarfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
TOTAL_MESAS = {240106: 858, 140126: 1786}
INCLUIR = [
    (DATA / "actas_pdf", "actas_pdf"),
    (DATA / "raw" / "pdfs_manifest.jsonl", "raw/pdfs_manifest.jsonl"),
    (DATA / "raw" / "mesas.jsonl", "raw/mesas.jsonl"),
    (ROOT / "prompts", "prompts"),
    (ROOT / "docs" / "API_ONPE.md", "docs/API_ONPE.md"),
    (ROOT / "reports" / "jee_ventanilla_digitado.csv", "analisis/jee_ventanilla_digitado.csv"),
    (ROOT / "AGENTS.md", "AGENTS.md"),
]


def archivos() -> list[tuple[Path, str]]:
    out = [(p, arc) for p, arc in INCLUIR if p.is_file()]
    for p, arc in INCLUIR:
        if p.is_dir():
            out += [(f, f"{arc}/{f.relative_to(p)}") for f in sorted(p.rglob("*")) if f.is_file()]
    out += [(f, f"raw/{f.name}") for f in sorted((DATA / "raw").glob("totales_*.json"))]
    return out


def contenido() -> str:
    """PAQUETE.md: qué trae exactamente este paquete (para que quien lo reciba no asuma que está completo)."""
    pdfs = list((DATA / "actas_pdf").rglob("*.pdf"))
    por = {}
    for f in pdfs:
        k = f"{f.parent.parent.name}/elección {f.parent.name}"
        por[k] = por.get(k, 0) + 1
    mesas = {}
    mf = DATA / "raw" / "mesas.jsonl"
    for ln in mf.read_text().splitlines() if mf.exists() else []:
        r = json.loads(ln)
        mesas[r["ubigeo"]] = mesas.get(r["ubigeo"], 0) + 1
    lineas = [f"# Contenido del paquete ({date.today():%Y-%m-%d})", "", f"- PDF de actas: {len(pdfs)}"]
    lineas += [f"  - ubigeo {k}: {n}" for k, n in sorted(por.items())]
    lineas += ["- Mesas con datos oficiales (`raw/mesas.jsonl`):"]
    lineas += [f"  - ubigeo {u}: {n} de {TOTAL_MESAS.get(u, '?')}" for u, n in sorted(mesas.items())]
    lineas += ["", "Un distrito con menos mesas que el total está INCOMPLETO: no cuadrará con `raw/totales_*.json`.", ""]
    return "\n".join(lineas)


def main() -> Path:
    destino = ROOT / "dist"
    destino.mkdir(exist_ok=True)
    lista = archivos()
    paquete_md = destino / "PAQUETE.md"
    paquete_md.write_text(contenido())
    sumas = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {arc}\n" for p, arc in lista)
    sumas_path = destino / "SHA256SUMS"
    sumas_path.write_text(sumas)
    paquete = destino / f"onpe-ocr-{date.today():%Y%m%d}.tar.gz"
    with tarfile.open(paquete, "w:gz") as tar:
        for p, arc in lista:
            tar.add(p, arcname=f"onpe-ocr/{arc}")
        tar.add(sumas_path, arcname="onpe-ocr/SHA256SUMS")
        tar.add(paquete_md, arcname="onpe-ocr/PAQUETE.md")
    print(f"{paquete} ({len(lista)} archivos, {paquete.stat().st_size / 1e6:.1f} MB)")
    return paquete


if __name__ == "__main__":
    main()
