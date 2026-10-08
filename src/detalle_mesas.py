"""Descarga TODAS las actas de cada mesa con una sola consulta por mesa (actas/buscar/mesa?codigoMesa=).

Endpoint descubierto en los repos independientes (fastestShipper/erm2026): 1 llamada = todas las elecciones de
la mesa con votos completos. 2644 consultas en vez de 7017. Reanudable.
Salida: data/raw/mesas.jsonl, una línea {"mesa", "ubigeo", "data": [actas]}.
Si ONPE responde 202/HTML (reto WAF) espera hasta 60 min a que una persona lo resuelva en la ventana de Chrome.
"""
import asyncio
import json
import logging
import random
import sys
from pathlib import Path

from playwright.async_api import async_playwright

import alarma
from totales import bajar_totales

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
OUT = RAW / "mesas.jsonl"
PROFILE = str(ROOT / "data" / ".chrome-profile")
ORDEN = ["actas_240106.json", "actas_140126.json"]  # Ventanilla primero (resultado a 328 votos), luego San Martín de Porres
logger = logging.getLogger(__name__)


def pendientes() -> list[tuple[str, int]]:
    hechas = set()
    if OUT.exists():
        hechas = {json.loads(ln)["mesa"] for ln in OUT.read_text().splitlines() if ln}
    cola = []
    for nombre in ORDEN:
        ub = int(nombre.split("_")[1].split(".")[0])
        mesas = sorted({r["codigoMesa"] for r in json.loads((RAW / nombre).read_text())})
        cola += [(m, ub) for m in mesas if m not in hechas]
    return cola


def espera_reto(intento: int) -> int | None:
    """Pausa escalonada entre sondeos con el reto activo: 30 s (10 min), 2 min (20 min), 5 min (hasta 8 h). Un sondeo es 1 consulta."""
    if intento <= 20:
        return 30
    if intento <= 30:
        return 120
    if intento <= 30 + 90:
        return 300
    return None


async def pedir(page, mesa: str) -> list[dict] | None:
    """None = sin datos (reto WAF, red caída, suspensión): el llamador espera y reintenta."""
    try:
        r = await page.evaluate(
            "async c => { const r = await fetch('/presentacion-backend/actas/buscar/mesa?codigoMesa=' + c); return {s: r.status, t: await r.text()}; }",
            mesa,
        )
        if r["s"] != 200 or not r["t"]:
            return None
        return json.loads(r["t"])["data"]
    except Exception as e:  # noqa: BLE001
        logger.warning("fallo de red/página: %s", str(e)[:120])
        if "has been closed" in str(e):  # cerraron la ventana de Chrome: salir y dejar que el lanzador abra otra
            alarma.detener()
            sys.exit(3)
        return None


async def main(limit: int | None) -> None:
    cola = pendientes()[:limit]
    logger.info("mesas pendientes: %d", len(cola))
    if not cola:
        return
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://resultadoelectoral.onpe.gob.pe/main/resumen")
        await asyncio.sleep(5)
        await bajar_totales(page)
        with OUT.open("a") as fh:
            for i, (mesa, ub) in enumerate(cola, 1):
                data = await pedir(page, mesa)
                intentos = 0
                while data is None:
                    intentos += 1
                    if intentos == 1:
                        alarma.iniciar()
                    if intentos % 2 == 1:
                        alarma.traer_chrome_al_frente()
                    espera = espera_reto(intentos)
                    if espera is None:
                        logger.error("reto sin resolver 8 h: detenido en %d/%d", i, len(cola))
                        alarma.detener()
                        await ctx.close()
                        sys.exit(1)
                    logger.warning("reto WAF en mesa %s (intento %d): resuélvelo en la ventana de Chrome; sondeo en %d s", mesa, intentos, espera)
                    await asyncio.sleep(espera)
                    if intentos % 4 == 0:
                        try:
                            await page.reload()
                        except Exception as e:  # noqa: BLE001
                            logger.warning("reload falló: %s", str(e)[:120])
                        await asyncio.sleep(5)
                    data = await pedir(page, mesa)
                if intentos:
                    alarma.detener()
                    logger.info("reto resuelto, alarma apagada")
                fh.write(json.dumps({"mesa": mesa, "ubigeo": ub, "data": data}, ensure_ascii=False) + "\n")
                fh.flush()
                if i % 25 == 0:
                    logger.info("%d/%d", i, len(cola))
                await asyncio.sleep(random.uniform(3.0, 5.0))
        await ctx.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
