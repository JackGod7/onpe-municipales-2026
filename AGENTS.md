# Instrucciones para el OCR de actas — ONPE ERM 2026 (Ventanilla y San Martín de Porres)

Eres un agente (o una persona) que recibe un paquete con actas de escrutinio en PDF y debe **transcribirlas con OCR (Vertex AI)**
para auditar los resultados oficiales de la ONPE. Lee esto completo antes de empezar.

## Objetivo
1. Transcribir los votos de cada acta tal como están escritos (no corregir, no adivinar).
2. Compararlos con la cifra oficial de la ONPE (`mesas.jsonl`) y clasificar cada diferencia.
3. **Prioridad 1:** actas que la ONPE NO contabilizó (`estado` distinto de `C`: "Para envío al JEE", observadas). En la API
   sus votos están vacíos; el PDF es la única fuente. Ventanilla distrital (elección 4) está a pocos votos: ahí cada acta cuenta.

## Contenido del paquete
| Ruta | Qué es |
| --- | --- |
| `actas_pdf/<ubigeo>/<eleccion>/<mesa>_escrutinio.pdf` | Acta de escrutinio escaneada. ubigeo 240106 = Ventanilla, 140126 = San Martín de Porres |
| `raw/pdfs_manifest.jsonl` | Un registro por PDF: mesa, elección, estado, SHA-256, bytes, fecha. **Verifica el hash antes de procesar** |
| `raw/mesas.jsonl` | Cifras oficiales de la ONPE por mesa (todas las elecciones): votos por organización, hábiles, emitidos, estado, línea de tiempo/motivo JEE |
| `raw/totales_<ubigeo>_<eleccion>.json` | Total oficial del distrito (para cuadrar la suma de mesas) |
| `prompts/extraccion_acta.md` | **Prompt v2 de extracción**, esquema JSON de salida y segunda pasada. Úsalo tal cual |
| `prompts/analisis_inconsistencias.md` | Qué se analiza después (lo hace el analista, no el OCR) |
| `docs/API_ONPE.md` | Cómo se obtuvo la data |

`idEleccion`: **3 = alcalde provincial, 4 = alcalde distrital**; 1 y 2 = gobierno regional (solo Ventanilla/Callao).

## Cómo ejecutar el OCR
- Modelo: Gemini 2.5 Pro en Vertex AI (`gemini-2.5-flash` solo como primer filtro barato). `temperature=0`,
  `response_mime_type="application/json"` con el `response_schema` de `prompts/extraccion_acta.md`.
- Inyecta por acta: tipo de elección, ubigeo, distrito, mesa y la **lista cerrada de organizaciones** (sácala de `mesas.jsonl`).
- Orden: primero estados `E`/`H` (JEE/observadas), luego Ventanilla elección 4, luego el resto.
- Guarda un JSON por acta en `ocr/<ubigeo>/<eleccion>/<mesa>.json` y un `ocr/ocr_log.jsonl` con: modelo, versión del prompt,
  fecha, SHA-256 del PDF, tokens. Credenciales por variables de entorno (`GOOGLE_APPLICATION_CREDENTIALS`); **nunca** en archivos del paquete.
- Reglas del prompt que no se negocian: casilla vacía = `null` (no 0); dígito ambiguo = `null` + `legible=false`; tachón = valor final + `enmendado=true`.

## Validación (antes de dar nada por bueno)
1. Muestra de 100 actas por distrito leídas a mano → exactitud por campo. Reporta el número.
2. Segunda pasada solo para actas con campos ilegibles, confianza baja o chequeo aritmético fallido. Si las dos lecturas difieren → `revision_humana`.
3. Compara OCR vs `mesas.jsonl` por mesa y organización. Clasifica cada diferencia: error de OCR / error del acta / error de digitación ONPE / acta no contabilizada.
4. Cuadre: suma de votos por organización (ONPE y OCR) vs `totales_*.json`.

## Entregable
- `ocr/` (JSON por acta) + `ocr_vs_onpe.csv` (una fila por mesa×organización: oficial, OCR, diferencia, confianza, clasificación).
- Lista aparte de actas JEE/observadas con sus votos según OCR y la suma de ajuste que implicarían sobre el total del distrito.
- Todo hallazgo es un **indicio**, nunca una acusación: se verifica a ojo contra el PDF antes de presentarlo.

## Límites
- No consultes ni raspes la web de la ONPE desde este paquete: la data ya está aquí. La ONPE usa verificación anti-bot y no se evade.
- Es información electoral pública, pero el análisis es confidencial del cliente: no lo publiques ni lo subas a servicios abiertos.
