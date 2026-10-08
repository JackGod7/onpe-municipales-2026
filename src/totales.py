"""Totales oficiales por distrito (resumen-general/totales y /participantes) para cuadrar la suma de las mesas.

Son pocas consultas y no activan el reto anti-bot. Se guardan en data/raw/totales_<ubigeo>_<eleccion>.json.
"""
import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlencode

RAW = Path(__file__).parent.parent / "data" / "raw"
# ubigeo: (departamento, provincia, elecciones a pedir)
DISTRITOS = {140126: (140000, 140100, (3, 4)), 240106: (240000, 240100, (1, 2, 3, 4))}
logger = logging.getLogger(__name__)


def _url(kind: str, elec: int, dep: int, prov: int, dist: int) -> str:
    q = {"idEleccion": elec, "tipoFiltro": "ubigeo_nivel_03", "idAmbitoGeografico": 1,
         "idUbigeoDepartamento": dep, "idUbigeoProvincia": prov, "idUbigeoDistrito": dist}
    return f"/presentacion-backend/resumen-general/{kind}?{urlencode(q)}"


async def bajar_totales(page) -> None:
    for dist, (dep, prov, elecs) in DISTRITOS.items():
        for elec in elecs:
            destino = RAW / f"totales_{dist}_{elec}.json"
            if destino.exists():
                continue
            salida = {}
            for kind in ("totales", "participantes"):
                try:
                    r = await page.evaluate(
                        "async u => { const r = await fetch(u); return {s: r.status, t: await r.text()}; }",
                        _url(kind, elec, dep, prov, dist),
                    )
                    salida[kind] = json.loads(r["t"]) if r["s"] == 200 and r["t"] else {"status": r["s"]}
                except Exception as e:  # noqa: BLE001
                    salida[kind] = {"error": str(e)[:120]}
                await asyncio.sleep(2)
            if all("status" not in v and "error" not in v for v in salida.values()):
                destino.write_text(json.dumps(salida, ensure_ascii=False))
                logger.info("totales %s elección %s guardados", dist, elec)
            else:
                logger.warning("totales %s elección %s incompletos: %s", dist, elec, {k: list(v)[:2] for k, v in salida.items()})
