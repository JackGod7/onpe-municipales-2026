"""Infografía de las actas JEE de un distrito: qué tan reñida está la elección y qué puede cambiar.

Lee los datos locales (mesas.jsonl y totales_*.json). Uso: uv run --group viz python src/infografia_jee.py
Salida: reports/infografia_ventanilla_jee.png (1080 x 1620).
"""
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import analisis  # noqa: E402

ROOT = Path(__file__).parent.parent
UBIGEO, ELECCION = 240106, 4
ORG_A, ORG_B = "RENOVACIÓN POPULAR PERÚ", "PARTIDO DEMOCRÁTICO SOMOS PERÚ"
AZUL, ROJO, GRIS, TINTA, FONDO = "#1F5FA8", "#D9482B", "#8A8F98", "#1B2430", "#F6F4EF"


def candidato(oficial: dict, org: str) -> str:
    for o in oficial["participantes"]["data"]:
        if o["nombreAgrupacionPolitica"] == org:
            return o["nombreCandidato"].title()
    return org


def tarjeta(ax, x, y, w, h, valor, texto, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.015", fc="white", ec="#DAD6CC", lw=1.2,
                                transform=ax.transAxes))
    ax.text(x + w / 2, y + h * 0.60, valor, ha="center", va="center", fontsize=30, fontweight="bold", color=color, transform=ax.transAxes)
    ax.text(x + w / 2, y + h * 0.20, texto, ha="center", va="center", fontsize=10.5, color=TINTA, transform=ax.transAxes)


def main() -> Path:
    oficial = json.loads((ROOT / "data" / "raw" / f"totales_{UBIGEO}_{ELECCION}.json").read_text())
    tot = {o["nombreAgrupacionPolitica"]: o["totalVotosValidos"] for o in oficial["participantes"]["data"]}
    a_ofi, b_ofi = tot[ORG_A], tot[ORG_B]
    nombre_a, nombre_b = candidato(oficial, ORG_A), candidato(oficial, ORG_B)
    corto_a, corto_b = nombre_a.split()[-2], nombre_b.split()[-2]  # apellido paterno

    jee = analisis.jee_distrital(UBIGEO, ELECCION, ORG_A, ORG_B)
    d = jee["votos_b"] - jee["votos_a"]  # >0: favorece a B
    gana_b, gana_a = int(d[d > 0].sum()), int(-d[d < 0].sum())
    margen = b_ofi - a_ofi  # ventaja oficial de B hoy
    escenarios = [
        (f"Solo cuentan las actas que\nfavorecen a {corto_b}", margen + gana_b),
        ("Se cuentan las 40\ncomo fueron digitadas", margen + gana_b - gana_a),
        ("Ninguna se cuenta\n(todas anuladas)", margen),
        (f"Solo cuentan las actas que\nfavorecen a {corto_a}", margen - gana_a),
    ]
    motivos = Counter(m for fila in jee["motivo_jee"] for m in {x.strip() for x in fila.split(",")} if m)

    fig = plt.figure(figsize=(7.2, 10.8), dpi=150, facecolor=FONDO)
    fig.text(0.06, 0.965, "Ventanilla · alcalde distrital", fontsize=22, fontweight="bold", color=TINTA, va="top")
    fig.text(0.06, 0.935, f"{len(jee)} actas en el JEE pueden decidir la elección", fontsize=14, color=ROJO, va="top", fontweight="bold")
    fig.text(0.06, 0.912, "Datos ONPE (8-oct-2026). Votos de esas actas = digitación provisional, no la lectura del PDF.",
             fontsize=8.5, color=GRIS, va="top")

    ax = fig.add_axes([0, 0.745, 1, 0.15]); ax.axis("off")
    tarjeta(ax, 0.06, 0.05, 0.28, 0.9, f"{margen:,}", f"votos de ventaja\n{corto_b} hoy", ROJO)
    tarjeta(ax, 0.36, 0.05, 0.28, 0.9, f"{len(jee)}", f"actas sin contar\n({int(jee['habiles'].sum()):,} electores)", TINTA)
    tarjeta(ax, 0.66, 0.05, 0.28, 0.9, f"{int(jee['votos_organizaciones'].sum()):,}", "votos digitados\nen esas actas", AZUL)

    ax1 = fig.add_axes([0.30, 0.545, 0.64, 0.17], facecolor=FONDO)
    ax1.set_title("¿Cómo puede quedar la diferencia?",
                  fontsize=10.5, color=TINTA, loc="left", x=-0.45, fontweight="bold")
    y = range(len(escenarios))[::-1]
    for yi, (nom, val) in zip(y, escenarios, strict=True):
        ax1.barh(yi, val, color=ROJO if val > 0 else AZUL, height=0.62)
        ax1.text(val + (25 if val > 0 else -25), yi, f"{val:+,}", va="center", ha="left" if val > 0 else "right",
                 fontsize=11, fontweight="bold", color=TINTA)
    ax1.set_yticks(list(y)); ax1.set_yticklabels([n for n, _ in escenarios], fontsize=8.5, color=TINTA)
    ax1.axvline(0, color=TINTA, lw=1)
    ax1.text(1.0, 1.02, f"+ ventaja de {corto_b}   − ventaja de {corto_a}", transform=ax1.transAxes, ha="right", fontsize=8, color=GRIS)
    lim = max(abs(v) for _, v in escenarios) * 1.25
    ax1.set_xlim(-lim * 0.45, lim); ax1.set_xticks([])
    for s in ax1.spines.values():
        s.set_visible(False)
    ax1.tick_params(length=0)

    ax2 = fig.add_axes([0.30, 0.355, 0.64, 0.14], facecolor=FONDO)
    ax2.set_title("¿Por qué están en el JEE?", fontsize=10.5, color=TINTA, loc="left",
                  x=-0.45, fontweight="bold")
    ax2.text(1.0, 1.02, "un acta puede tener varios motivos", transform=ax2.transAxes, ha="right", fontsize=8, color=GRIS)
    items = motivos.most_common()[::-1]
    ax2.barh([i[0].replace("Acta ", "").capitalize() for i in items], [i[1] for i in items], color=GRIS, height=0.6)
    for i, (_, n) in enumerate(items):
        ax2.text(n + 0.3, i, str(n), va="center", fontsize=9.5, color=TINTA, fontweight="bold")
    ax2.set_xticks([]); ax2.tick_params(length=0, labelsize=8.5)
    for s in ax2.spines.values():
        s.set_visible(False)

    top = jee.assign(d=d, ad=d.abs()).sort_values("ad", ascending=False).head(5)
    lineas = ["Actas con mayor peso (diferencia entre ambos): " + ", ".join(
        f"{r.mesa} ({'+' if r.d > 0 else '−'}{int(r.ad)} {corto_b if r.d > 0 else corto_a})" for r in top.itertuples())]
    ax3 = fig.add_axes([0.06, 0.04, 0.88, 0.27]); ax3.axis("off")
    ax3.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0.01,rounding_size=0.02", fc="white", ec="#DAD6CC", lw=1.2,
                                 transform=ax3.transAxes))
    ax3.text(0.04, 0.92, "Qué decidir", fontsize=14, fontweight="bold", color=TINTA, va="top", transform=ax3.transAxes)
    pasos = [
        f"1. Leer primero las {motivos.get('Acta con error aritmético', 0)} actas con error aritmético: ahí la digitación\n    puede estar mal y un acta puede mover decenas de votos.",
        f"2. Preparar sustento para las {motivos.get('Acta impugnada', 0)} impugnadas y {motivos.get('Acta sin firmas', 0)} sin firmas: las\n    resuelve el JEE; llevar el PDF y el acta de instalación.",
        "3. El resultado real depende de lo que diga cada PDF y de la\n    resolución del JEE, no de la cifra digitada. Por eso: OCR + revisión manual.",
        lineas[0],
    ]
    yy = 0.78
    for p in pasos[:3]:
        ax3.text(0.04, yy, p, fontsize=9.5, color=TINTA, va="top", transform=ax3.transAxes, linespacing=1.35)
        yy -= 0.22
    ax3.text(0.04, yy, "\n".join(_ajustar(pasos[3], 62)), fontsize=8.8, color=GRIS, va="top", transform=ax3.transAxes, linespacing=1.3)
    fig.text(0.06, 0.012, "Fuente: ONPE · resultadoelectoral.onpe.gob.pe · indicios a verificar contra el acta, no conclusiones.",
             fontsize=7.5, color=GRIS)

    salida = ROOT / "reports" / "infografia_ventanilla_jee.png"
    fig.savefig(salida, facecolor=FONDO)
    return salida


def _ajustar(texto: str, ancho: int) -> list[str]:
    import textwrap
    return textwrap.wrap(texto, ancho)


if __name__ == "__main__":
    print(main())
