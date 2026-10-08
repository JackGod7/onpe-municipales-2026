"""Estudio cruzado por mesa entre las elecciones de un distrito (regional, provincial, distrital).

Pregunta: ¿el voto de cada organización en la elección distrital se comporta como en las otras elecciones de la misma
mesa (mismos electores), o hay patrones anómalos? Solo usa actas contabilizadas en las elecciones comparadas.
Uso: uv run python src/estudio_cruzado.py [ubigeo]   -> reports/estudio_cruzado_<ubigeo>.xlsx + resumen en pantalla
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
ESPECIALES = {"VOTOS NULOS": "nulos", "VOTOS EN BLANCO": "blancos", "VOTOS IMPUGNADOS": "impugnados"}
NOMBRE_ELECCION = {1: "gobernador regional", 2: "consejo regional", 3: "alcalde provincial", 4: "alcalde distrital"}
ORGS = {"RP": "RENOVACIÓN POPULAR PERÚ", "SP": "PARTIDO DEMOCRÁTICO SOMOS PERÚ"}
CRITICO_CHI2_9GL = 21.67  # p = 0.01, 9 grados de libertad


def tabla(ubigeo: int) -> pd.DataFrame:
    """Una fila por mesa × elección con totales y % de las organizaciones de interés (solo actas contabilizadas)."""
    filas = []
    for ln in (RAW / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        if r["ubigeo"] != ubigeo:
            continue
        for d in r["data"]:
            if d["codigoEstadoActa"] != "C":
                continue
            v = {x["adDescripcion"]: x["adVotos"] or 0 for x in d["detalle"] or []}
            fila = {"mesa": d["codigoMesa"], "local": d["nombreLocalVotacion"], "eleccion": d["idEleccion"],
                    "habiles": d["totalElectoresHabiles"], "emitidos": d["totalVotosEmitidos"], "validos": d["totalVotosValidos"],
                    **{c: v.get(k, 0) for k, c in ESPECIALES.items()}}
            for corto, org in ORGS.items():
                fila[f"v_{corto}"] = v.get(org, 0)
            filas.append(fila)
    df = pd.DataFrame(filas)
    for corto in ORGS:
        df[f"p_{corto}"] = 100 * df[f"v_{corto}"] / df["validos"].replace(0, np.nan)
    df["p_nulo_blanco"] = 100 * (df["nulos"] + df["blancos"]) / df["emitidos"].replace(0, np.nan)
    return df


def z_robusto(s: pd.Series) -> pd.Series:
    mad = (s - s.median()).abs().median() * 1.4826
    return (s - s.median()) / (mad if mad > 0 else s.std())


def ultimo_digito(valores: pd.Series) -> tuple[float, bool]:
    """Chi² de uniformidad del último dígito (solo conteos >= 10). True = se aparta de lo esperado (p<0.01)."""
    x = valores[valores >= 10] % 10
    obs = np.bincount(x.astype(int), minlength=10)
    esp = len(x) / 10
    chi2 = float(((obs - esp) ** 2 / esp).sum()) if esp else 0.0
    return chi2, chi2 > CRITICO_CHI2_9GL


def estudio(ubigeo: int) -> dict[str, pd.DataFrame]:
    df = tabla(ubigeo)
    elecs = sorted(df["eleccion"].unique())
    completas = df.groupby("mesa")["eleccion"].nunique()
    df = df[df["mesa"].isin(completas[completas == len(elecs)].index)]
    ancho = df.pivot_table(index=["mesa", "local"], columns="eleccion",
                           values=["emitidos", "p_RP", "p_SP", "p_nulo_blanco", "v_RP", "v_SP", "validos"])
    ancho.columns = [f"{m}_{e}" for m, e in ancho.columns]
    ancho = ancho.reset_index()
    em = ancho[[f"emitidos_{e}" for e in elecs]]
    ancho["dif_emitidos"] = em.max(axis=1) - em.min(axis=1)
    dist, prov = 4, 3
    for c in ("RP", "SP"):
        ancho[f"brecha_{c}"] = ancho[f"p_{c}_{dist}"] - ancho[f"p_{c}_{prov}"]
        ancho[f"z_{c}"] = z_robusto(ancho[f"brecha_{c}"])
    ancho["brecha_nulo_blanco"] = ancho[f"p_nulo_blanco_{dist}"] - ancho[f"p_nulo_blanco_{prov}"]
    ancho["z_nulo_blanco"] = z_robusto(ancho["brecha_nulo_blanco"])

    resumen = []
    for e in elecs:
        x = df[df["eleccion"] == e]
        resumen.append({"eleccion": e, "nombre": NOMBRE_ELECCION.get(e, e), "mesas": len(x), "emitidos": int(x["emitidos"].sum()),
                        "validos": int(x["validos"].sum()), "pct_nulo_blanco": round(100 * (x["nulos"] + x["blancos"]).sum() / x["emitidos"].sum(), 2),
                        "pct_RP": round(100 * x["v_RP"].sum() / x["validos"].sum(), 2),
                        "pct_SP": round(100 * x["v_SP"].sum() / x["validos"].sum(), 2)})
    digitos = []
    for e in elecs:
        x = df[df["eleccion"] == e]
        for c in ("RP", "SP"):
            chi2, raro = ultimo_digito(x[f"v_{c}"])
            digitos.append({"eleccion": e, "org": c, "chi2": round(chi2, 1), "se_aparta_p01": raro})
    locales = ancho.groupby("local").agg(mesas=("mesa", "size"), brecha_RP=("brecha_RP", "mean"), brecha_SP=("brecha_SP", "mean"),
                                         brecha_nulo_blanco=("brecha_nulo_blanco", "mean")).reset_index()
    locales["z_local_RP"] = z_robusto(locales["brecha_RP"])
    anomalas = ancho[(ancho["z_RP"].abs() > 3.5) | (ancho["z_SP"].abs() > 3.5) | (ancho["z_nulo_blanco"].abs() > 3.5) | (ancho["dif_emitidos"] > 3)]
    return {"resumen": pd.DataFrame(resumen), "mesas": ancho, "anomalas": anomalas.sort_values("z_RP"),
            "locales": locales.sort_values("brecha_RP"), "ultimo_digito": pd.DataFrame(digitos)}


def main(ubigeo: int) -> None:
    r = estudio(ubigeo)
    with pd.ExcelWriter(ROOT / "reports" / f"estudio_cruzado_{ubigeo}.xlsx") as xw:
        for nombre, t in r.items():
            t.to_excel(xw, sheet_name=nombre, index=False)
    m = r["mesas"]
    print(r["resumen"].to_string(index=False))
    print(f"\nmesas comparables: {len(m)}")
    print(f"corr %RP provincial vs distrital: {m['p_RP_3'].corr(m['p_RP_4']):.3f} | corr %SP: {m['p_SP_3'].corr(m['p_SP_4']):.3f}")
    print(f"corr cambio RP vs cambio SP (dist-prov): {m['brecha_RP'].corr(m['brecha_SP']):.3f}")
    print(f"brecha RP media {m['brecha_RP'].mean():+.2f} pp (mediana {m['brecha_RP'].median():+.2f}) | SP media {m['brecha_SP'].mean():+.2f} pp")
    print(f"mesas con emitidos distintos entre elecciones (>3): {(m['dif_emitidos'] > 3).sum()} | máx {int(m['dif_emitidos'].max())}")
    print(f"mesas anómalas (|z|>3.5 o emitidos>3): {len(r['anomalas'])}")
    print(r["anomalas"][["mesa", "local", "p_RP_3", "p_RP_4", "brecha_RP", "z_RP", "brecha_SP", "z_SP", "brecha_nulo_blanco", "dif_emitidos"]]
          .round(1).head(15).to_string(index=False))
    print("\nlocales con mayor caída de RP distrital vs provincial:")
    print(r["locales"].head(6).round(2).to_string(index=False))
    print("\núltimo dígito:", r["ultimo_digito"].to_dict("records"))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240106)
