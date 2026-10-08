"""Decisión acta por acta para las actas JEE de la elección distrital y escenarios por criterio uniforme del JEE.

A = organización propia (2.º lugar), B = rival (1.º lugar). d = votos_B − votos_A en cada acta (digitación ONPE).
Uso: uv run python src/decision_jee.py  -> reports/decision_actas_jee.xlsx + resumen en pantalla
"""
from pathlib import Path

import pandas as pd

import analisis

ROOT = Path(__file__).parent.parent
FORMA = ("firm", "impugn", "ilegib", "incomplet", "sin datos")
MARGEN_HOY = None  # se lee del total oficial


def es_forma(motivo: str) -> bool:
    """Observación de forma (firmas, impugnación, ilegible, incompleta): la que puede terminar en anulación."""
    return any(k in motivo.lower() for k in FORMA)


def accion(d: int, forma: bool) -> tuple[str, str]:
    if d < 0 and forma:
        return "DEFENDER", "Que se cuente: pedir cotejo con los otros ejemplares del acta y subsanación; personero y abogado en audiencia."
    if d < 0:
        return "DEFENDER", "Que se cuente: llevar el PDF y demostrar que los votos propios están bien; si el error afecta a otros, que se corrija sin anular."
    if d > 0 and forma:
        return "EXIGIR RIGOR", "Que el JEE aplique la causal tal cual: si el defecto es real y no se subsana con otro ejemplar, corresponde lo que diga el reglamento."
    if d > 0:
        return "VERIFICAR", "Leer el PDF: si los votos del rival son menores a lo digitado o la suma no cuadra, pedir corrección con prueba."
    return "SIN EFECTO", "Empate en el acta: no mueve la diferencia; no gastar recursos."


def esperado_por_mesa(ubigeo: int = 240106, shift_a: float = 0.28, shift_b: float = 4.07) -> dict[str, float]:
    """d esperado (B−A) en la distrital según el voto de la MISMA mesa en otra elección contabilizada (provincial, si no regional),
    más el cambio medio distrital−provincial observado en el distrito. Sirve para ver qué acta está mal digitada."""
    import json
    ra, rb = "RENOVACIÓN POPULAR PERÚ", "PARTIDO DEMOCRÁTICO SOMOS PERÚ"
    out = {}
    for ln in (analisis.RAW / "mesas.jsonl").read_text().splitlines():
        r = json.loads(ln)
        if r["ubigeo"] != ubigeo:
            continue
        por = {a["idEleccion"]: a for a in r["data"]}
        ref = next((por[e] for e in (3, 1, 2) if e in por and por[e]["codigoEstadoActa"] == "C"), None) or por.get(3)
        if ref is None:
            continue
        v = {x["adDescripcion"]: x["adVotos"] or 0 for x in ref["detalle"] or []}
        val = sum(x for k, x in v.items() if k not in analisis.ESPECIALES)
        if val:
            out[r["mesa"]] = ((v.get(rb, 0) / val + shift_b / 100) - (v.get(ra, 0) / val + shift_a / 100)) * val


    return out


def tabla(margen_hoy: int) -> pd.DataFrame:
    j = analisis.jee_distrital()
    j["d"] = j["votos_b"] - j["votos_a"]
    j["forma"] = j["motivo_jee"].map(es_forma)
    j[["accion", "objetivo"]] = j.apply(lambda r: pd.Series(accion(int(r["d"]), bool(r["forma"]))), axis=1)
    esp = esperado_por_mesa()
    j["d_esperado"] = j["mesa"].map(esp).round()
    j["efecto_si_se_reconstruye"] = (j["d"] - j["d_esperado"]).round()  # >0 favorece a A si el JEE fija el valor real
    j["sospecha_digitacion"] = j["efecto_si_se_reconstruye"].abs() >= 40
    j["votos_en_juego"] = j["d"].abs()
    j["prioridad"] = j["votos_en_juego"].rank(ascending=False, method="first").astype(int)
    return j.sort_values("prioridad")[["prioridad", "mesa", "local", "accion", "votos_a", "votos_b", "d", "votos_en_juego",
                                       "d_esperado", "efecto_si_se_reconstruye", "sospecha_digitacion", "motivo_jee", "objetivo"]]


def escenarios(j: pd.DataFrame, margen_hoy: int) -> pd.DataFrame:
    forma = j["motivo_jee"].map(es_forma)
    def margen(anuladas):
        return margen_hoy + int(j.loc[~anuladas, "d"].sum())
    filas = [
        ("JEE cuenta las 40 como están digitadas", margen(forma & False)),
        ("JEE anula todas las de forma y cuenta las aritméticas", margen(forma)),
        ("JEE salva las de forma y anula todas las aritméticas", margen(~forma)),
        ("JEE anula las 40", margen(forma | ~forma)),
        ("Mejor caso selectivo: caen solo las del rival", margen(j["d"] > 0)),
    ]
    return pd.DataFrame(filas, columns=["criterio", "ventaja_rival"])


def main() -> None:
    import json
    oficial = json.loads((analisis.RAW / "totales_240106_4.json").read_text())["participantes"]["data"]
    tot = {o["nombreAgrupacionPolitica"]: o["totalVotosValidos"] for o in oficial}
    margen_hoy = tot["PARTIDO DEMOCRÁTICO SOMOS PERÚ"] - tot["RENOVACIÓN POPULAR PERÚ"]
    t = tabla(margen_hoy)
    e = escenarios(t, margen_hoy)
    with pd.ExcelWriter(ROOT / "reports" / "decision_actas_jee.xlsx") as xw:
        t.to_excel(xw, sheet_name="acta_por_acta", index=False)
        e.to_excel(xw, sheet_name="escenarios", index=False)
    print(e.to_string(index=False))
    print(t.groupby("accion").agg(actas=("mesa", "size"), votos_en_juego=("votos_en_juego", "sum")).to_string())
    print("pronóstico si el JEE cuenta las 40 con su valor real esperado:", round(margen_hoy + t["d_esperado"].sum()))
    print(t[t["sospecha_digitacion"]][["mesa", "accion", "votos_a", "votos_b", "d", "d_esperado", "efecto_si_se_reconstruye"]].to_string(index=False))


if __name__ == "__main__":
    main()
