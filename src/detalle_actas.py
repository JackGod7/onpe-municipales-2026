"""Descarga el detalle (votos por organización) de TODAS las actas listadas. Reanudable.

Salida: data/raw/detalle.jsonl (una línea por acta). Ritmo 2-3.5 s. Si ONPE responde 202 vacío (reto WAF)
espera (hasta 60 min) a que una persona lo resuelva en la ventana de Chrome; no intenta resolverlo.
"""
import asyncio
import json
import logging
import random
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "detalle.jsonl"
PROFILE = str(ROOT / "data" / ".chrome-profile")
ELECCIONES = None  # None = todas las elecciones listadas (Ventanilla: 1-4, SMP: 3-4)
logger = logging.getLogger(__name__)


def pendientes() -> list[dict]:
    hechas = set()
    if OUT.exists():
        hechas = {json.loads(ln)["id"] for ln in OUT.read_text().splitlines() if ln}
    filas = []
    for f in sorted(RAW.glob("actas_*.json")):
        filas += [r for r in json.loads(f.read_text()) if (ELECCIONES is None or r["idEleccion"] in ELECCIONES) and r["id"] not in hechas]
    return filas


async def pedir(page, acta_id: int) -> dict | None:
    """None = sin datos (reto WAF, red caída o equipo suspendido); el llamador espera y reintenta."""
    try:
        return await _pedir(page, acta_id)
    except Exception as e:  # noqa: BLE001 — red cortada por suspensión, página recargándose, etc.
        logger.warning("fallo de red/página: %s", str(e)[:120])
        return None


async def _pedir(page, acta_id: int) -> dict | None:
    r = await page.evaluate(
        "async i => { const r = await fetch('/presentacion-backend/actas/' + i); return {s: r.status, t: await r.text()}; }",
        acta_id,
    )
    return json.loads(r["t"])["data"] if r["s"] == 200 and r["t"] else None


async def main(limit: int | None) -> None:
    cola = pendientes()[:limit]
    logger.info("pendientes: %d", len(cola))
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://resultadoelectoral.onpe.gob.pe/main/resumen")
        await asyncio.sleep(5)
        with OUT.open("a") as fh:
            for i, fila in enumerate(cola, 1):
                data = await pedir(page, fila["id"])
                intentos = 0
                while data is None:
                    intentos += 1
                    if intentos > 120:
                        logger.error("reto sin resolver 60 min: detenido en %d/%d", i, len(cola))
                        await ctx.close()
                        return
                    logger.warning("reto WAF en %s (intento %d): resuélvelo en la ventana de Chrome", fila["id"], intentos)
                    await asyncio.sleep(30)
                    if intentos % 4 == 0:
                        try:
                            await page.reload()
                        except Exception as e:  # noqa: BLE001
                            logger.warning("reload falló: %s", str(e)[:120])
                        await asyncio.sleep(5)
                    data = await pedir(page, fila["id"])
                fh.write(json.dumps(data, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 50 == 0:
                    logger.info("%d/%d", i, len(cola))
                await asyncio.sleep(random.uniform(3.0, 5.0))
        await ctx.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
