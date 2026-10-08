"""Lista las actas (una fila por mesa y elección) de los distritos del proyecto.

Usa el Chrome instalado (channel="chrome", sin descargas). Obscura sin --stealth recibe 403 de ONPE (probado
2026-10-08) y no se usa --stealth. Ritmo humano. No intenta evadir el reto anti-bot de ONPE: si una respuesta llega como 202 vacío, se detiene.
"""
import asyncio
import json
import logging
import random
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "/presentacion-backend"
DISTRITOS = {"VENTANILLA": 240106, "SAN MARTIN DE PORRES": 140126}
RAW = Path(__file__).parent.parent / "data" / "raw"
PROFILE = str(Path(__file__).parent.parent / "data" / ".chrome-profile")
PAGE_SIZE = 100  # máximo aceptado por la API
logger = logging.getLogger(__name__)


class RetoAntiBot(RuntimeError):
    pass


async def _get(page, path: str) -> dict:
    res = await page.evaluate(
        "async p => { const r = await fetch(p); return {s: r.status, t: await r.text()}; }",
        f"{BASE}/{path}",
    )
    if res["s"] == 202 or not res["t"]:
        raise RetoAntiBot(f"{path}: HTTP {res['s']} sin cuerpo (reto WAF)")
    return json.loads(res["t"])


async def listar(page, nombre: str, ubigeo: int) -> list[dict]:
    filas, pag, total_pag = [], 0, 1
    while pag < total_pag:
        j = await _get(page, f"actas?pagina={pag}&tamanio={PAGE_SIZE}&idAmbitoGeografico=1&idUbigeo={ubigeo}")
        total_pag = j["data"]["totalPaginas"]
        filas.extend(j["data"]["content"])
        pag += 1
        logger.info("%s %d/%d", nombre, pag, total_pag)
        await asyncio.sleep(random.uniform(2.0, 3.5))
    return filas


async def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False, viewport={"width": 1280, "height": 800}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://resultadoelectoral.onpe.gob.pe/main/resumen")
        await asyncio.sleep(4)
        for nombre, ubigeo in DISTRITOS.items():
            filas = await listar(page, nombre, ubigeo)
            (RAW / f"actas_{ubigeo}.json").write_text(json.dumps(filas, ensure_ascii=False))
            logger.info("%s: %d filas", nombre, len(filas))
        await context.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
