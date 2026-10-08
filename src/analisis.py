"""Análisis por mesa: ranking, voto cruzado provincia vs distrito y aritmética del acta.

Criterios en prompts/analisis_inconsistencias.md. Todo hallazgo es un INDICIO a verificar en el PDF del acta.
Uso: uv run python src/analisis.py
"""
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
RAW = ROOT / "data" / "raw"
DETALLE = RAW / "detalle.jsonl"
UBIGEOS = {140126: "SAN MARTÍN DE PORRES", 240106: "VENTANILLA"}
REPORTS = ROOT / "reports"
CLIENTES_JSON = ROOT / "data" / "clientes.json"  # local, fuera de Git; ver clientes.example.json
ESPECIALES = {"VOTOS NULOS": "nulos", "VOTOS EN BLANCO": "blancos", "VOTOS IMPUGNADOS": "impugnados"}
MIN_VALIDOS = 100  # evita ruido de mesas chicas en el voto cruzado
logger = logging.getLogger(__name__)


def _actas_crudas():
    """Rinde actas en un formato único. Fuentes: mesas.jsonl (buscar/mesa, claves ad*) y detalle.jsonl (actas/{id}, claves n*)."""
    mesas = RAW / "mesas.jsonl"
    if mesas.exists():
        for linea in mesas.read_text().splitlines():
            for d in json.loads(linea)["data"]:
                yield d, "adDescripcion", "adVotos", None
    if DETALLE.exists():
        for linea in DETALLE.read_text().splitlines():
            d = json.loads(linea)
            yield d, "descripcion", "nVotos", any(a.get("tipo") == 1 for a in d.get("archivos") or [])


def cargar_clientes(ruta: Path = CLIENTES_JSON) -> dict[str, tuple[str, str]]:
    """{nombre: (organización, distrito)}. Sin archivo, no hay hojas por cliente (el resto del análisis corre igual)."""
    if not ruta.exists():
        logger.warning("sin %s: se omiten las hojas por cliente", ruta.name)
        return {}
    return {n: (c["organizacion"], c["distrito"]) for n, c in json.loads(ruta.read_text()).items()}


def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (actas, votos) en formato largo; votos solo de organizaciones, sin nulos/blancos."""
    actas, votos = [], []
    for d, kd, kv, pdf in _actas_crudas():
        base = {
            "id": d["id"], "eleccion": d["idEleccion"], "ubigeo": d.get("idUbigeo"),
            "distrito": d.get("ubigeoNivel03") or UBIGEOS.get(d.get("idUbigeo")), "mesa": d["codigoMesa"],
            "local": d["nombreLocalVotacion"], "estado": d["codigoEstadoActa"], "habiles": d["totalElectoresHabiles"],
            "emitidos": d["totalVotosEmitidos"], "validos": d["totalVotosValidos"], "asistentes": d.get("totalAsistentes"),
            "tiene_pdf": pdf,
        }
        esp = {v: 0 for v in ESPECIALES.values()}
        for x in d["detalle"] or []:
            if x[kd] in ESPECIALES:
                esp[ESPECIALES[x[kd]]] = x[kv] or 0
            else:
                votos.append({"id": d["id"], "org": x[kd], "votos": x[kv] or 0})
        actas.append({**base, **esp})
    a = pd.DataFrame(actas).drop_duplicates("id")
    v = pd.DataFrame(votos).drop_duplicates(["id", "org"])
    return a, v


def aritmetica(a: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    suma = v.groupby("id")["votos"].sum().rename("suma_orgs")
    a = a.join(suma, on="id")
    a["dif_validos"] = a["suma_orgs"] - a["validos"]
    a["dif_emitidos"] = a["suma_orgs"] + a["nulos"] + a["blancos"] + a["impugnados"] - a["emitidos"]
    mask = (a["dif_validos"].fillna(0) != 0) | (a["dif_emitidos"].fillna(0) != 0) | (a["emitidos"] > a["habiles"])
    return a[mask & a["emitidos"].notna()]


def avisos(a: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    """Revisiones adicionales tomadas de fastestShipper/erm2026 (collector/actas.py). Son avisos, no acusaciones."""
    top = v.sort_values("votos", ascending=False).drop_duplicates("id").set_index("id")
    x = a.join(top[["org", "votos"]].rename(columns={"org": "org_top", "votos": "votos_top"}), on="id")
    x["aviso_asistentes_ne_emitidos"] = x["asistentes"].notna() & x["emitidos"].notna() & (x["asistentes"] != x["emitidos"])
    x["aviso_participacion_100"] = x["habiles"].gt(0) & (x["emitidos"] >= x["habiles"])
    x["aviso_org_95pct"] = x["validos"].gt(0) & x["votos_top"].ge(50) & (x["votos_top"] / x["validos"] >= 0.95)
    cols = [c for c in x if c.startswith("aviso_")]
    return x[x[cols].any(axis=1)]


def cuadre(a: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    """Suma de las mesas CONTABILIZADAS vs total oficial del distrito (resumen-general/participantes).

    Las actas no contabilizadas (JEE/observadas) traen votos digitados en la API pero la ONPE no los suma al oficial;
    se informan aparte (votos_en_actas_no_contabilizadas): es lo que está en juego.
    """
    filas = []
    for f in sorted(RAW.glob("totales_*_*.json")):
        _, ub, elec = f.stem.split("_")
        ub, elec = int(ub), int(elec)
        oficial = json.loads(f.read_text())["participantes"]["data"] or []
        mesas = a[(a["ubigeo"] == ub) & (a["eleccion"] == elec)]
        cont, jee = mesas[mesas["estado"] == "C"], mesas[mesas["estado"] != "C"]
        suma = v[v["id"].isin(cont["id"])].groupby("org")["votos"].sum()
        pendiente = v[v["id"].isin(jee["id"])].groupby("org")["votos"].sum()
        for o in oficial:
            org = o["nombreAgrupacionPolitica"]
            propio = int(suma.get(org, 0))
            filas.append({"ubigeo": ub, "eleccion": elec, "org": org, "candidato": o["nombreCandidato"],
                          "oficial": o["totalVotosValidos"], "suma_mesas_contabilizadas": propio,
                          "dif": o["totalVotosValidos"] - propio, "mesas_contabilizadas": len(cont),
                          "mesas_no_contabilizadas": len(jee), "votos_en_actas_no_contabilizadas": int(pendiente.get(org, 0))})
    return pd.DataFrame(filas)


def jee_distrital(ubigeo: int = 240106, eleccion: int = 4, org_a: str = "RENOVACIÓN POPULAR PERÚ",
                  org_b: str = "PARTIDO DEMOCRÁTICO SOMOS PERÚ") -> pd.DataFrame:
    """Actas no contabilizadas (JEE/observadas) de un distrito con los votos que la ONPE digitó para dos organizaciones.

    Son valores provisionales (digitación), no la lectura del PDF. `motivo_jee` sale de la línea de tiempo del acta.
    """
    filas = []
    mesas = RAW / "mesas.jsonl"
    for linea in mesas.read_text().splitlines():
        r = json.loads(linea)
        if r["ubigeo"] != ubigeo:
            continue
        for d in r["data"]:
            if d["idEleccion"] != eleccion or d["codigoEstadoActa"] == "C":
                continue
            votos = {x["adDescripcion"]: x["adVotos"] or 0 for x in d["detalle"] or []}
            orgs = {k: x for k, x in votos.items() if k not in ESPECIALES}
            motivo = next((t["descripcionEstadoActaResolucion"] for t in d["lineaTiempo"] or []
                           if t["codigoEstadoActa"] == "E" and t["descripcionEstadoActaResolucion"]), "")
            filas.append({"mesa": d["codigoMesa"], "local": d["nombreLocalVotacion"], "habiles": d["totalElectoresHabiles"],
                          "votos_a": orgs.get(org_a, 0), "votos_b": orgs.get(org_b, 0),
                          "votos_organizaciones": sum(orgs.values()), "motivo_jee": motivo})
    out = pd.DataFrame(filas).sort_values("mesa")
    out.attrs["org_a"], out.attrs["org_b"] = org_a, org_b
    return out


def ranking(a: pd.DataFrame, v: pd.DataFrame, org: str) -> pd.DataFrame:
    x = v[v["org"] == org].merge(a, on="id")
    x = x[x["validos"] > 0].copy()
    x["pct"] = 100 * x["votos"] / x["validos"]
    return x.sort_values("pct", ascending=False)[["distrito", "eleccion", "mesa", "local", "votos", "validos", "pct"]]


def voto_cruzado(a: pd.DataFrame, v: pd.DataFrame, org: str, e_alto: int = 3, e_bajo: int = 4) -> pd.DataFrame:
    """Brecha = %org en elección e_alto (provincial) − %org en e_bajo (distrital), por mesa. z robusto por distrito."""
    r = ranking(a, v, org)
    r = r[r["validos"] >= MIN_VALIDOS]
    p = r.pivot_table(index=["distrito", "mesa", "local"], columns="eleccion", values="pct")
    if e_alto not in p or e_bajo not in p:
        return pd.DataFrame()
    p = p.dropna(subset=[e_alto, e_bajo]).copy()
    p["brecha"] = p[e_alto] - p[e_bajo]
    g = p.groupby("distrito")["brecha"]
    mad = g.transform(lambda s: (s - s.median()).abs().median()) * 1.4826
    escala = mad.where(mad > 0, g.transform("std"))  # MAD=0 (muchas brechas idénticas): se usa la desviación estándar
    p["z"] = (p["brecha"] - g.transform("median")) / escala.replace(0, np.nan)
    return p.reset_index().sort_values("z", key=abs, ascending=False)


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    a, v = cargar()
    logger.info("actas: %d  (por distrito/elección: %s)", len(a), a.groupby(["distrito", "eleccion"]).size().to_dict())
    with pd.ExcelWriter(REPORTS / "analisis_mesas.xlsx") as xw:
        aritmetica(a, v).to_excel(xw, sheet_name="aritmetica", index=False)
        avisos(a, v).to_excel(xw, sheet_name="avisos", index=False)
        a.to_excel(xw, sheet_name="actas_todas", index=False)
        cuadre(a, v).to_excel(xw, sheet_name="cuadre_oficial", index=False)
        jee_distrital().to_excel(xw, sheet_name="jee_ventanilla", index=False)
        for cliente, (org, distrito) in cargar_clientes().items():
            r = ranking(a, v, org)
            r = r[r["distrito"] == distrito]
            r.head(50).to_excel(xw, sheet_name=f"top_{cliente.split()[0]}", index=False)
            r.tail(50).iloc[::-1].to_excel(xw, sheet_name=f"bottom_{cliente.split()[0]}", index=False)
            vc = voto_cruzado(a, v, org)
            vc = vc[vc["distrito"] == distrito] if len(vc) else vc
            if len(vc):
                vc.head(100).to_excel(xw, sheet_name=f"cruzado_{cliente.split()[0]}", index=False)
    jee = jee_distrital()
    jee.rename(columns={"votos_a": "votos_RENOVACION_POPULAR", "votos_b": "votos_SOMOS_PERU"}).to_csv(
        REPORTS / "jee_ventanilla_digitado.csv", index=False)
    logger.info("reporte: %s", REPORTS / "analisis_mesas.xlsx")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
