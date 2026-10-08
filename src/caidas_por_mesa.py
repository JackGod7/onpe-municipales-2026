"""Mesas donde una organización vota parejo en región, consejo y provincia, pero cae (o sube) fuerte en la distrital.

Base = promedio de votos de la organización en las elecciones 1 (gobernador), 2 (consejo) y 3 (alcalde provincial) de la
MISMA mesa (mismos electores). "Parejo" = la diferencia entre esas tres no pasa de max(8 votos, 15 % de la base).
Caída = votos distritales − base. Incluye actas JEE (sus votos son la digitación provisional; columna estado_4).
Uso: uv run python src/caidas_por_mesa.py [ubigeo]  -> reports/caidas_por_mesa_<ubigeo>.xlsx
"""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
ORGS = {"RP": "RENOVACIÓN POPULAR PERÚ", "SP": "PARTIDO DEMOCRÁTICO SOMOS PERÚ"}


def tabla(ubigeo: int) -> pd.DataFrame:
    filas = []
    for ln in (ROOT / "data" / "raw" / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        if r["ubigeo"] != ubigeo:
            continue
        por = {a["idEleccion"]: a for a in r["data"]}
        if not all(e in por for e in (1, 2, 3, 4)):
            continue
        fila = {"mesa": r["mesa"], "local": por[4]["nombreLocalVotacion"],
                **{f"estado_{e}": por[e]["codigoEstadoActa"] for e in (1, 2, 3, 4)}}
        for corto, org in ORGS.items():
            for e in (1, 2, 3, 4):
                v = {x["adDescripcion"]: x["adVotos"] for x in por[e]["detalle"] or []}
                fila[f"{corto}_{e}"] = v.get(org)
        filas.append(fila)
    return pd.DataFrame(filas)


def caidas(df: pd.DataFrame, corto: str) -> pd.DataFrame:
    c = [f"{corto}_{e}" for e in (1, 2, 3)]
    x = df.dropna(subset=c).copy()
    x["base"] = x[c].mean(axis=1)
    x["dispersion_123"] = x[c].max(axis=1) - x[c].min(axis=1)
    x["parejo_123"] = x["dispersion_123"] <= (0.15 * x["base"]).clip(lower=8)
    x["distrital"] = x[f"{corto}_4"]
    x["cambio"] = x["distrital"] - x["base"]
    x["cambio_pct"] = 100 * x["cambio"] / x["base"].where(x["base"] > 0)
    return x


def main(ubigeo: int) -> None:
    df = tabla(ubigeo)
    hojas = {}
    for corto in ORGS:
        x = caidas(df, corto)
        p = x[x["parejo_123"] & x["distrital"].notna()]
        cols = ["mesa", "local", f"{corto}_1", f"{corto}_2", f"{corto}_3", "distrital", "cambio", "cambio_pct", "estado_4"]
        hojas[f"{corto}_mayor_caida"] = p.sort_values("cambio").head(30)[cols]
        hojas[f"{corto}_mayor_subida"] = p.sort_values("cambio", ascending=False).head(30)[cols]
        sin = x[x["distrital"].isna()][cols]
        if len(sin):
            hojas[f"{corto}_distrital_vacio"] = sin
        print(f"\n{corto}: {len(x)} mesas, {len(p)} parejas en 1-2-3; cambio medio {p['cambio'].mean():+.1f} votos")
        print("mayor CAÍDA en distrital:")
        print(hojas[f"{corto}_mayor_caida"].head(12).round(1).to_string(index=False))
        print("mayor SUBIDA en distrital:")
        print(hojas[f"{corto}_mayor_subida"].head(8).round(1).to_string(index=False))
    with pd.ExcelWriter(ROOT / "reports" / f"caidas_por_mesa_{ubigeo}.xlsx") as xw:
        for n, t in hojas.items():
            t.to_excel(xw, sheet_name=n[:31], index=False)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240106)
