# Criterios de análisis de inconsistencias (determinístico, en código — no en el LLM)

El LLM solo transcribe. Las irregularidades se detectan con SQL/pandas sobre los datos extraídos, para que sean
reproducibles y defendibles.

## 1. Mesas más y menos votadas (por candidato cliente)
- `pct_candidato = votos_candidato / votos_validos` por mesa y por elección (distrital y provincial).
- Ranking top-N y bottom-N por distrito y por local de votación.
- Reportar también `participación = total_votaron / electores_habiles`.

## 2. Voto cruzado provincia vs distrito (el caso principal)
Para cada mesa con ambas actas, y cada organización O (partido/alianza/movimiento regional):
- `p_prov = votos_prov(O) / validos_prov` ; `p_dist = votos_dist(O) / validos_dist`
- `brecha = p_prov - p_dist`
- Anomalía si `brecha` supera el percentil 99 del distrito **o** z-score robusto (mediana/MAD) > 3.5
  respecto de las mesas del mismo distrito, y la mesa tiene ≥ 100 votos válidos (evita ruido de mesas chicas).
- Contexto: el voto dividido es legítimo; la señal es la **concentración** (mesas/locales/miembros de mesa
  repetidos), no una mesa aislada. Agrupar anomalías por local de votación y por rangos de mesa contiguos.

## 3. Aritmética del acta
- `suma_orgs + blancos + nulos + impugnados ≠ total_votaron`
- `total_votaron > electores_habiles`
- Votos válidos de un candidato > votos válidos totales.
- Mesas con 0 votos para una organización que tiene > 20 % en las mesas vecinas del mismo local.

## 4. Acta vs resultado oficial publicado
- Comparar OCR vs ONPE (`resultadoelectoral.onpe.gob.pe/presentacion-backend`) por mesa y organización.
- Estados ONPE: contabilizada, observada, anulada, enviada al JEE — cruzar con las anomalías.

## 5. Integridad documental
- Firmas incompletas, sin sello, horas incoherentes (fin < inicio, escrutinio fuera de horario),
  enmiendas (`enmendado=true`), observaciones del acta, calidad de imagen mala.

## 6. Salida por hallazgo
`mesa, distrito, tipo, valores observados, valor esperado, métrica (z/brecha), confianza OCR, enlace al PDF, sha256`.
Cada hallazgo se etiqueta **indicio** hasta verificarlo contra el acta física/PDF a ojo. Nunca se presenta
como fraude: es una lista priorizada para revisión y sustento ante el JEE/JNE.
