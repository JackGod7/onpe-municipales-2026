"""Coordenadas aproximadas de los locales de votación de un distrito, buscando cada colegio por nombre en OpenStreetMap (Nominatim).

Solo se envían nombres de colegios y el distrito; ningún dato de votación. Máx. 1 consulta por segundo (política de uso de Nominatim).
Resultado en data/raw/geo_<ubigeo>.json (cache reanudable). Los no encontrados quedan con lat/lon nulos. Uso: ... geocodificar_locales.py [ubigeo]
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DISTRITOS = {140126: "San Martín de Porres, Lima, Perú", 240106: "Ventanilla, Callao, Perú"}
UA = "onpe-municipales-2026-auditoria/1.0 (analisis electoral; contacto: jaaguilar@acity.com.pe)"


def locales(ubigeo: int) -> list[str]:
    vistos = set()
    for ln in (ROOT / "data" / "raw" / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        if r["ubigeo"] == ubigeo and r["data"]:
            vistos.add(r["data"][0]["nombreLocalVotacion"])
    return sorted(vistos)


def variantes(nombre: str, distrito: str) -> list[str]:
    limpio = re.sub(r"\b(IEI|IEP|IE|I\.E\.|CEBA|CEBE|CETPRO)\b\.?", "", nombre).strip()
    limpio = re.sub(r"\s+", " ", limpio)
    sin_num = re.sub(r"\b\d{3,5}\b", "", limpio).strip()
    return [f"{nombre}, {distrito}", f"{limpio}, {distrito}", f"colegio {sin_num}, {distrito}" if sin_num else f"{limpio}, {distrito}"]


def buscar(q: str) -> dict | None:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "pe"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        res = json.loads(r.read())
    time.sleep(1.1)
    return {"lat": float(res[0]["lat"]), "lon": float(res[0]["lon"]), "match": res[0]["display_name"][:120]} if res else None


def main(ubigeo: int) -> None:
    destino = ROOT / "data" / "raw" / f"geo_{ubigeo}.json"
    geo = json.loads(destino.read_text()) if destino.exists() else {}
    for i, nombre in enumerate(locales(ubigeo), 1):
        if nombre in geo:
            continue
        hallado = None
        for q in variantes(nombre, DISTRITOS[ubigeo]):
            try:
                hallado = buscar(q)
            except Exception as e:  # noqa: BLE001
                print("fallo", nombre, str(e)[:80])
                time.sleep(5)
            if hallado:
                break
        geo[nombre] = hallado or {"lat": None, "lon": None, "match": None}
        destino.write_text(json.dumps(geo, ensure_ascii=False, indent=0))
        print(f"[{i}] {nombre[:40]:40s} {'OK' if hallado else '--'}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 140126)
