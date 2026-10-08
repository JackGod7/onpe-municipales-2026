# ONPE Municipales 2026 — Ventanilla y San Martín de Porres

Auditoría de resultados de las Elecciones Regionales y Municipales 2026 (ONPE) para Ventanilla y San Martín de Porres.

Reutiliza lo construido para ERM/EG 2026:
- `JackGod7/proyecto_nulidad` — scraping Playwright (la API ONPE solo responde desde navegador), SQLite forense, OCR.
- `JackGod7/-auditoria-eg2026` — metodología y cadena de custodia.

> **Si vas a hacer el OCR: lee [`AGENTS.md`](AGENTS.md) primero.** Ahí está todo, incluido cómo bajar los datos.

## Alcance
- Elecciones: Municipal Distrital y Municipal Provincial (Lima), 4-oct-2026.
- Distritos: Ventanilla (Callao) y San Martín de Porres (Lima).
- Entregables: data completa por mesa, OCR de actas, ranking de mesas, voto cruzado provincia/distrito, informe.

## Estructura
- `prompts/` — prompt de extracción OCR v2 y criterios de análisis.
- `data/raw` (JSON ONPE), `data/actas_pdf`, `data/extraido` — ignorados por Git.
- `src/` — scraper, extractor, análisis. `reports/` — informes. `docs/` — notas.

## Uso rápido
```bash
uv sync
uv run python src/listar_actas.py      # listado de actas por distrito
uv run python src/detalle_mesas.py     # votos por mesa (Chrome real; si aparece el reto anti-bot, resolverlo a mano)
uv run python src/descargar_pdfs.py    # PDF de actas, priorizando las no contabilizadas (JEE)
uv run python src/analisis.py          # ranking, voto cruzado, aritmética, cuadre vs oficial
uv run python src/empaquetar.py        # paquete para OCR (PDF + data + prompts + AGENTS.md + SHA256SUMS)
./gate.sh                              # lint + tests, igual que el CI
```
Los candidatos a analizar van en `data/clientes.json` (local, fuera de Git; ver `clientes.example.json`).
Instrucciones para quien haga el OCR: `AGENTS.md`. Cómo se obtuvo la data: `docs/API_ONPE.md`.

El reto anti-bot de la ONPE no se evade: el script se detiene, suena una alarma y espera a que una persona lo resuelva.
