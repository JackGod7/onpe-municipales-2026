"""Sonda: ¿qué devuelve actas/buscar/mesa?codigoMesa=NNNNNN? (endpoint que usan los repos independientes)."""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE = str(Path(__file__).parent.parent / "data" / ".chrome-profile")


async def main(codigo: str) -> None:
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(PROFILE, channel="chrome", headless=False)
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await pg.goto("https://resultadoelectoral.onpe.gob.pe/main/resumen")
        await asyncio.sleep(5)
        r = await pg.evaluate(
            "async c => { const r = await fetch('/presentacion-backend/actas/buscar/mesa?codigoMesa=' + c); return {s: r.status, t: await r.text()}; }",
            codigo,
        )
        print("status", r["s"], "len", len(r["t"]))
        try:
            d = json.loads(r["t"])["data"]
            print(type(d).__name__, len(d))
            fila = d[0] if isinstance(d, list) else d
            print(json.dumps(fila, ensure_ascii=False)[:1500])
            if isinstance(d, list):
                print([(a.get("idEleccion"), a.get("totalVotosEmitidos"), len(a.get("detalle") or [])) for a in d])
        except Exception as e:  # noqa: BLE001
            print("ERR", e, r["t"][:200])
        await ctx.close()


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "047784"))
