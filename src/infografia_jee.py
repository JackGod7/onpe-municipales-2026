"""Infografía estratégica de las actas JEE de un distrito: cuánto necesita mover el 2.º lugar y dónde está cada voto.

Lee los datos locales (mesas.jsonl y totales_*.json). Uso: uv run --group viz python src/infografia_jee.py
Salida: reports/infografia_ventanilla_jee.png (1080 x 1620).
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import analisis  # noqa: E402

ROOT = Path(__file__).parent.parent
UBIGEO, ELECCION = 240106, 4
ORG_A, ORG_B = "RENOVACIÓN POPULAR PERÚ", "PARTIDO DEMOCRÁTICO SOMOS PERÚ"  # A = 2.º lugar, B = 1.º lugar
AZUL, ROJO, ROJO_CLARO, AZUL_CLARO = "#1F5FA8", "#D9482B", "#F0A08F", "#8FB3DE"
GRIS, TINTA, FONDO, BORDE = "#8A8F98", "#1B2430", "#F6F4EF", "#DAD6CC"
FORMA = ("firm", "impugn", "ilegib", "incomplet", "sin datos")


def es_forma(motivo: str) -> bool:
    """Observación de forma (firmas, impugnación, ilegible, incompleta): la que puede terminar en anulación."""
    return any(k in motivo.lower() for k in FORMA)


def apellido(oficial: dict, org: str) -> str:
    for o in oficial["participantes"]["data"]:
        if o["nombreAgrupacionPolitica"] == org and o["nombreCandidato"]:
            return o["nombreCandidato"].split()[-2].title()
    return org.title()


def caja(fig, x, y, w, h):
    ax = fig.add_axes([x, y, w, h]); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.005,rounding_size=0.03", fc="white", ec=BORDE, lw=1.2,
                                transform=ax.transAxes))
    return ax


def barra_apilada(ax, y, partes, total_ref, etiqueta):
    x = 0
    for valor, color, texto in partes:
        ax.barh(y, valor, left=x, color=color, height=0.55)
        if valor >= total_ref * 0.08:
            ax.text(x + total_ref * 0.015, y, texto, ha="left", va="center", fontsize=8.5, color="white", fontweight="bold")
        x += valor
    ax.text(-total_ref * 0.02, y, etiqueta, ha="right", va="center", fontsize=9, color=TINTA)


def main() -> Path:
    oficial = json.loads((ROOT / "data" / "raw" / f"totales_{UBIGEO}_{ELECCION}.json").read_text())
    tot = {o["nombreAgrupacionPolitica"]: o["totalVotosValidos"] for o in oficial["participantes"]["data"]}
    a, b = apellido(oficial, ORG_A), apellido(oficial, ORG_B)
    margen_hoy = tot[ORG_B] - tot[ORG_A]

    jee = analisis.jee_distrital(UBIGEO, ELECCION, ORG_A, ORG_B)
    jee = jee.assign(d=jee["votos_b"] - jee["votos_a"], forma=jee["motivo_jee"].map(es_forma))
    margen_todo = margen_hoy + int(jee["d"].sum())
    necesita = margen_todo + 1
    b_forma = jee[(jee.d > 0) & jee.forma]; b_arit = jee[(jee.d > 0) & ~jee.forma]
    a_forma = jee[(jee.d < 0) & jee.forma]; a_arit = jee[(jee.d < 0) & ~jee.forma]
    v = {k: int(abs(x["d"].sum())) for k, x in {"bf": b_forma, "ba": b_arit, "af": a_forma, "aa": a_arit}.items()}

    fig = plt.figure(figsize=(7.2, 10.8), dpi=150, facecolor=FONDO)
    fig.text(0.06, 0.968, "Ventanilla · alcalde distrital", fontsize=21, fontweight="bold", color=TINTA, va="top")
    fig.text(0.06, 0.938, f"Qué necesita {a} en las {len(jee)} actas del JEE", fontsize=14, color=AZUL, va="top", fontweight="bold")
    fig.text(0.06, 0.914, "Datos ONPE 8-oct-2026 · votos de esas actas = digitación provisional, a confirmar con el PDF",
             fontsize=8.3, color=GRIS, va="top")

    kp = fig.add_axes([0.06, 0.785, 0.88, 0.11]); kp.axis("off")
    for i, (val, txt, col) in enumerate([
        (f"{margen_hoy:,}", f"ventaja de {b}\ncon lo contado hoy", ROJO),
        (f"{margen_todo:,}", f"ventaja de {b} si las {len(jee)}\nse cuentan como están", ROJO),
        (f"{necesita:,}", f"votos netos que {a}\nnecesita mover", AZUL),
    ]):
        x = i * 0.34
        kp.add_patch(FancyBboxPatch((x, 0), 0.32, 1, boxstyle="round,pad=0.005,rounding_size=0.04", fc="white", ec=BORDE, lw=1.2,
                                    transform=kp.transAxes))
        kp.text(x + 0.16, 0.64, val, ha="center", va="center", fontsize=26, fontweight="bold", color=col, transform=kp.transAxes)
        kp.text(x + 0.16, 0.22, txt, ha="center", va="center", fontsize=8.6, color=TINTA, transform=kp.transAxes)

    ref = max(v["bf"] + v["ba"], v["af"] + v["aa"], necesita) * 1.05
    ax = fig.add_axes([0.36, 0.555, 0.58, 0.17], facecolor=FONDO)
    fig.text(0.06, 0.742, "Dónde están los votos en juego", fontsize=11.5, fontweight="bold", color=TINTA)
    fig.text(0.06, 0.727, "ventaja acumulada de cada candidato en las actas donde gana, por tipo de observación",
             fontsize=8, color=GRIS)
    barra_apilada(ax, 1, [(v["bf"], ROJO, f"forma {v['bf']}"), (v["ba"], ROJO_CLARO, f"aritmética {v['ba']}")], ref,
                  f"Actas donde gana {b}\n({len(b_forma) + len(b_arit)} actas)")
    barra_apilada(ax, 0, [(v["af"], AZUL, f"forma {v['af']}"), (v["aa"], AZUL_CLARO, f"aritmética {v['aa']}")], ref,
                  f"Actas donde gana {a}\n({len(a_forma) + len(a_arit)} actas)")
    ax.plot([necesita, necesita], [0.62, 1.42], color=TINTA, lw=1.4, ls="--")
    ax.text(necesita, 1.5, f"{a} necesita {necesita} de aquí", ha="center", fontsize=8.5, color=TINTA, fontweight="bold")
    ax.set_xlim(0, ref); ax.set_ylim(-0.5, 1.75); ax.axis("off")

    lect = caja(fig, 0.06, 0.345, 0.88, 0.18)
    lect.text(0.04, 0.88, "Lectura estratégica", fontsize=12, fontweight="bold", color=TINTA, va="top", transform=lect.transAxes)
    lineas = [
        f"• Si se anularan las {len(b_forma)} actas de forma de {b}, {a} recorta {v['bf']}: no alcanza ({necesita}).",
        f"• Para pasar adelante necesita además que caigan o se corrijan a su favor actas\n   aritméticas de {b} ({v['ba']} votos), que normalmente se corrigen, no se anulan.",
        f"• Riesgo propio: {len(a_forma)} actas de forma donde gana {a} ({v['af']} votos). Si se\n   anulan, la ventaja de {b} crece. Defenderlas es la primera prioridad.",
        "• Conclusión: camino estrecho. Se gana acta por acta con el PDF, no con la cifra digitada.",
    ]
    y = 0.70
    for ln in lineas:
        lect.text(0.04, y, ln, fontsize=8.7, color=TINTA, va="top", transform=lect.transAxes, linespacing=1.3)
        y -= 0.19 if "\n" in ln else 0.12

    dec = caja(fig, 0.06, 0.045, 0.88, 0.28)
    dec.text(0.04, 0.92, "Qué hacer ahora", fontsize=12, fontweight="bold", color=TINTA, va="top", transform=dec.transAxes)
    top_a = ", ".join(a_forma.sort_values("d")["mesa"].head(4))
    top_b = ", ".join(b_arit.sort_values("d", ascending=False)["mesa"].head(4))
    pasos = [
        f"1. DEFENDER: abogado y personero en la audiencia de las {len(a_forma)} actas de forma\n    propias (ej. {top_a}). Llevar el PDF y el acta de instalación.",
        f"2. VERIFICAR: leer el PDF de las {len(b_arit)} actas aritméticas de {b}\n    (ej. {top_b}). Si la cifra real difiere, pedir la corrección con prueba.",
        "3. IMPUGNAR SOLO CON CAUSAL REAL: firmas, ilegibilidad o actas incompletas,\n    documentadas. Un pedido sin sustento resta credibilidad ante el JEE.",
        "4. PLAZOS: las apelaciones al JNE corren en días. Calendario con el abogado hoy.",
        "5. COMUNICACIÓN: no declarar victoria ni fraude. Mensaje: «que se cuente cada voto».",
    ]
    y = 0.78
    for p in pasos:
        dec.text(0.04, y, p, fontsize=8.6, color=TINTA, va="top", transform=dec.transAxes, linespacing=1.3)
        y -= 0.165 if "\n" in p else 0.10
    fig.text(0.06, 0.015, "Fuente: ONPE · resultadoelectoral.onpe.gob.pe · indicios a verificar contra el acta; confirmar reglas y plazos con abogado.",
             fontsize=7, color=GRIS)

    salida = ROOT / "reports" / "infografia_ventanilla_jee.png"
    fig.savefig(salida, facecolor=FONDO)
    return salida


if __name__ == "__main__":
    print(main())
