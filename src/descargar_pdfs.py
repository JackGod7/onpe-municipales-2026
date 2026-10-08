"""Descarga los PDF de las actas (escrutinio) en orden de prioridad, con SHA-256 y manifiesto de custodia. Reanudable.

Prioridad: 1) actas que NO están contabilizadas (envío al JEE / observadas): sin votos en la API, el PDF es la única fuente;
2) Ventanilla, elección distrital (4); 3) el resto. Por acta: actas/{id} (lista de archivos) -> actas/file?id= (URL firmada) -> PDF.
Si ONPE pide verificación (202/HTML) suena la alarma y espera a que una persona la resuelva en Chrome.
Salida: data/actas_pdf/<ubigeo>/<eleccion>/<mesa>_<tipo>.pdf y data/raw/pdfs_manifest.jsonl.
Uso: uv run python src/descargar_pdfs.py [limite] [ubigeo] [eleccion]   (vacío = sin filtro)
"""
import asyncio
import base64
import hashlib
import json
import logging
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import async_playwright

import alarma
from detalle_mesas import espera_reto

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
MESAS = RAW / "mesas.jsonl"
MANIFEST = RAW / "pdfs_manifest.jsonl"
PDFS = ROOT / "data" / "actas_pdf"
PROFILE = str(ROOT / "data" / ".chrome-profile")
TIPOS = {1: "escrutinio"}  # 2 = instalación y sufragio (no trae votos); se agrega después si hace falta
logger = logging.getLogger(__name__)


def prioridad(acta: dict) -> tuple:
    no_contab = acta["codigoEstadoActa"] != "C"
    ventanilla_dist = acta["idUbigeo"] == 240106 and acta["idEleccion"] == 4
    return (0 if no_contab else 1, 0 if ventanilla_dist else 1, acta["idUbigeo"] != 240106, acta["idEleccion"] != 4, acta["codigoMesa"])


def cola(ubigeo: int | None = None, eleccion: int | None = None) -> list[dict]:
    hechas = set()
    if MANIFEST.exists():
        hechas = {json.loads(ln)["acta_id"] for ln in MANIFEST.read_text().splitlines() if ln}
    actas = []
    for ln in MESAS.read_text().splitlines():
        for a in json.loads(ln)["data"]:
            if a["id"] in hechas or (ubigeo and a["idUbigeo"] != ubigeo) or (eleccion and a["idEleccion"] != eleccion):
                continue
            actas.append(a)
    return sorted(actas, key=prioridad)


async def _js(page, codigo: str, arg):
    r = await page.evaluate(codigo, arg)
    return r


async def pedir_json(page, ruta: str) -> dict | None:
    try:
        r = await page.evaluate(
            "async u => { const r = await fetch(u); return {s: r.status, t: await r.text()}; }", f"/presentacion-backend/{ruta}"
        )
        return json.loads(r["t"]) if r["s"] == 200 and r["t"] else None
    except Exception as e:  # noqa: BLE001
        logger.warning("fallo: %s", str(e)[:120])
        if "has been closed" in str(e):
            alarma.detener()
            sys.exit(3)
        return None


async def bajar_pdf(page, url: str) -> bytes | None:
    try:
        b64 = await page.evaluate(
            """async u => { const r = await fetch(u); if (!r.ok) return null; const b = new Uint8Array(await r.arrayBuffer());
            let s = ''; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768)); return btoa(s); }""",
            url,
        )
        return base64.b64decode(b64) if b64 else None
    except Exception as e:  # noqa: BLE001
        logger.warning("descarga falló: %s", str(e)[:120])
        return None


async def con_reto(page, intento_fn, etiqueta: str):
    """Ejecuta intento_fn() hasta que devuelva algo; mientras tanto avisa y espera al humano (mismo protocolo que detalle_mesas)."""
    res, n = await intento_fn(), 0
    while res is None:
        n += 1
        if n == 1:
            alarma.iniciar()
        if n % 2 == 1:
            alarma.traer_chrome_al_frente()
        espera = espera_reto(n)
        if espera is None:
            alarma.detener()
            logger.error("reto sin resolver 8 h en %s", etiqueta)
            sys.exit(1)
        logger.warning("reto WAF en %s (intento %d): resuélvelo en Chrome; sondeo en %d s", etiqueta, n, espera)
        await asyncio.sleep(espera)
        if n % 4 == 0:
            try:
                await page.reload()
            except Exception as e:  # noqa: BLE001
                logger.warning("reload falló: %s", str(e)[:120])
            await asyncio.sleep(5)
        res = await intento_fn()
    if n:
        alarma.detener()
        logger.info("reto resuelto, alarma apagada")
    return res


async def main(limite: int | None, ubigeo: int | None = None, eleccion: int | None = None) -> None:
    pendientes = cola(ubigeo, eleccion)[:limite]
    logger.info("actas por descargar: %d", len(pendientes))
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://resultadoelectoral.onpe.gob.pe/main/resumen")
        await asyncio.sleep(5)
        with MANIFEST.open("a") as fh:
            for i, a in enumerate(pendientes, 1):
                det = await con_reto(page, lambda a=a: pedir_json(page, f"actas/{a['id']}"), f"acta {a['id']}")
                for arch in (det.get("data") or {}).get("archivos") or []:
                    if arch.get("tipo") not in TIPOS:
                        continue
                    await asyncio.sleep(random.uniform(1.5, 2.5))
                    f = await con_reto(page, lambda arch=arch: pedir_json(page, f"actas/file?id={arch['id']}"), f"archivo {arch['id']}")
                    url = f["data"] if isinstance(f.get("data"), str) else (f.get("data") or {}).get("url")
                    pdf = await bajar_pdf(page, url) if url else None
                    if not pdf:
                        logger.warning("sin PDF para acta %s archivo %s", a["id"], arch["id"])
                        continue
                    ruta = PDFS / str(a["idUbigeo"]) / str(a["idEleccion"]) / f"{a['codigoMesa']}_{TIPOS[arch['tipo']]}.pdf"
                    ruta.parent.mkdir(parents=True, exist_ok=True)
                    ruta.write_bytes(pdf)
                    fh.write(json.dumps({
                        "acta_id": a["id"], "mesa": a["codigoMesa"], "ubigeo": a["idUbigeo"], "eleccion": a["idEleccion"],
                        "estado": a["codigoEstadoActa"], "archivo_id": arch["id"], "nombre_onpe": arch.get("nombre"),
                        "ruta": str(ruta.relative_to(ROOT / "data")), "bytes": len(pdf),
                        "sha256": hashlib.sha256(pdf).hexdigest(), "descargado": datetime.now(UTC).isoformat(timespec="seconds"),
                    }, ensure_ascii=False) + "\n")
                    fh.flush()
                if i % 25 == 0:
                    logger.info("%d/%d", i, len(pendientes))
                await asyncio.sleep(random.uniform(3.0, 5.0))
        await ctx.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argv = sys.argv[1:]
    limite = int(argv[0]) if len(argv) > 0 and argv[0] else None
    ubigeo = int(argv[1]) if len(argv) > 1 and argv[1] else None
    eleccion = int(argv[2]) if len(argv) > 2 and argv[2] else None
    asyncio.run(main(limite, ubigeo, eleccion))
