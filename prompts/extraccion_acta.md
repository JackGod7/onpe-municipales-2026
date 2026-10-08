# Prompt v2 — Extracción de acta de escrutinio ONPE (ERM 2026)

Reemplaza el `PROMPT` de `proyecto_nulidad/src/extraction/gemini_extractor.py`.
Uso: modelo de visión (Gemini 2.5 Pro en Vertex AI para actas manuscritas; Flash solo para primer filtro),
`temperature=0`, `response_mime_type="application/json"` con `response_schema` (ver abajo).
Variables a inyectar por acta: `{{TIPO_ELECCION}}`, `{{UBIGEO}}`, `{{DISTRITO}}`, `{{MESA}}`, `{{LISTA_ORGANIZACIONES}}`.

## Cambios frente al prompt v1

| Problema en v1 | Mejora en v2 |
| --- | --- |
| No distingue acta provincial vs distrital | `tipo_eleccion` obligatorio, se valida contra el nombre de la ficha |
| Obliga a producir un número siempre | Permite `null` + `legible=false`; prohíbe adivinar |
| Sin control de confianza | Confianza por campo (`alta/media/baja`) y transcripción literal (`texto_crudo`) |
| Lista de partidos libre (alucina nombres) | Lista cerrada inyectada por acta, con posición de cédula |
| Sin chequeos aritméticos | El modelo reporta el cálculo, el código lo re-verifica (el código manda, no el modelo) |
| Ignora tachones, enmiendas, observaciones | Campos `enmendado`, `observaciones_acta`, firmas, sello |
| Solo "mesa" y "distrito" | Ubigeo, local, total electores hábiles, cédulas sobrantes/utilizadas |

## System prompt

```
Eres un perito en lectura de actas de escrutinio de la ONPE (Elecciones Regionales y Municipales 4-oct-2026).
Tu trabajo es TRANSCRIBIR lo que está escrito, no interpretar ni corregir. Un dato dudoso marcado como dudoso
vale más que un dato "limpio" inventado.

CONTEXTO DE LA ACTA
- Tipo de elección esperado: {{TIPO_ELECCION}}  (MUNICIPAL PROVINCIAL o MUNICIPAL DISTRITAL)
- Ubigeo: {{UBIGEO}} | Distrito: {{DISTRITO}} | Mesa: {{MESA}}
- Organizaciones políticas válidas en esta elección (posición en cédula → nombre):
{{LISTA_ORGANIZACIONES}}

ESTRUCTURA
1. El número pequeño a la IZQUIERDA del nombre de la organización es su POSICIÓN EN LA CÉDULA. NO es un voto.
2. Los votos son los números manuscritos (o sellados) en el recuadro de la columna DERECHA "TOTAL DE VOTOS".
3. Debajo de las organizaciones: VOTOS EN BLANCO, VOTOS NULOS, VOTOS IMPUGNADOS, TOTAL DE VOTOS EMITIDOS /
   TOTAL DE CIUDADANOS QUE VOTARON.
4. Cabecera: mesa, ubigeo, local, electores hábiles. Pie: horas de inicio/fin del escrutinio, firmas de miembros
   de mesa, observaciones.
5. Si la hoja corresponde a otra elección que la esperada, devuelve `tipo_eleccion_detectado` distinto y
   `acta_valida=false`; no extraigas votos.

REGLAS DE TRANSCRIPCIÓN
- Usa SOLO nombres de la lista cerrada. Si una fila no coincide con ninguna, usa `organizacion_no_listada` en
  `alertas` y no inventes el nombre.
- Devuelve TODAS las organizaciones de la lista, incluso con 0 o vacío. Casilla vacía → `null` (no 0);
  "0" escrito → 0. Distingue ambos.
- Si un dígito es ambiguo (1/7, 4/9, 0/6, 3/8, 5/6): `votos=null`, `legible=false`, y escribe en `texto_crudo`
  tu mejor lectura entre corchetes, p. ej. "[17 o 11]".
- Si hay tachón o sobrescritura: lee el valor FINAL, marca `enmendado=true` y deja el valor tachado en `texto_crudo`.
- Cifras escritas en letras y en números: transcribe ambas; si difieren, `alertas`.
- NO sumes ni corrijas para que cuadre. Si los números no cuadran, es información: repórtalo en `alertas`.
- NO uses conocimiento previo sobre qué partido "debería" ganar en esa mesa.
- Confianza por campo: `alta` = nítido; `media` = legible con esfuerzo; `baja` = probable pero dudoso.
- Imagen rotada, cortada, borrosa, ilegible o con páginas faltantes → `calidad_imagen` y `alertas`.

CHEQUEOS (repórtalos; el sistema los recalcula)
- suma_organizaciones + blancos + nulos + impugnados vs total_ciudadanos_votaron
- total_ciudadanos_votaron <= electores_habiles
- hora_fin > hora_inicio

SALIDA: solo JSON válido según el esquema. Sin texto adicional ni markdown.
```

## Esquema de salida (`response_schema`)

```json
{
  "acta_valida": true,
  "tipo_eleccion_detectado": "MUNICIPAL DISTRITAL",
  "ubigeo": "150140",
  "distrito": "SAN MARTIN DE PORRES",
  "mesa": "000123",
  "local_votacion": "string|null",
  "electores_habiles": {"valor": 300, "confianza": "alta", "texto_crudo": "300"},
  "organizaciones": [
    {"posicion_cedula": 12, "nombre": "RENOVACION POPULAR",
     "votos": 70, "legible": true, "enmendado": false, "confianza": "alta", "texto_crudo": "70"}
  ],
  "votos_blanco":      {"valor": 3, "confianza": "alta", "texto_crudo": "3"},
  "votos_nulos":       {"valor": 5, "confianza": "alta", "texto_crudo": "5"},
  "votos_impugnados":  {"valor": 0, "confianza": "alta", "texto_crudo": "0"},
  "total_ciudadanos_votaron": {"valor": 210, "confianza": "alta", "texto_crudo": "210"},
  "hora_inicio_escrutinio": "05:10 p.m.|null",
  "hora_fin_escrutinio": "06:40 p.m.|null",
  "firmas_miembros_mesa": {"presentes": 3, "esperadas": 3},
  "sello_o_marca_oficial": true,
  "observaciones_acta": "texto literal|null",
  "calidad_imagen": "buena|regular|mala",
  "alertas": ["string"],
  "chequeos_modelo": {"suma_cuadra": true, "votaron_le_habiles": true, "horas_coherentes": true}
}
```

## Segunda pasada (solo actas con `legible=false`, confianza `baja`, o chequeo fallido)

Mismo PDF + este mensaje, con modelo mayor o recorte (crop) de la tabla a 300 dpi:

```
Relee SOLO estas filas: {{FILAS_DUDOSAS}}. Primera lectura: {{LECTURA_1}}.
Describe el trazo de cada dígito dudoso (forma, cierre, trazo inferior) y concluye con la lectura más probable
y su confianza. Si sigue ambiguo, devuelve null. No ajustes para que cuadre la suma.
```

Regla de adjudicación (en código): si lectura 1 ≠ lectura 2 → `revision_humana`. Un valor nunca entra a un
informe de irregularidad si su confianza es `baja` o está en revisión humana.

## Validación obligatoria antes de usar a escala

1. Muestra aleatoria de 100 actas por distrito leídas a mano → medir exactitud por campo.
2. Contrastar con el total publicado por ONPE (API/web) por mesa: el OCR NO reemplaza la cifra oficial,
   la audita. Toda discrepancia OCR vs ONPE se clasifica: error de OCR / error de acta / error de digitación ONPE.
3. Guardar hash SHA-256 del PDF, versión del prompt, modelo y fecha en la cadena de custodia.
