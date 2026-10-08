# API ONPE — ERM 2026 (mapeada 2026-10-08)

Base: `https://resultadoelectoral.onpe.gob.pe/presentacion-backend` (se consulta desde el navegador, misma origen).

| Dato | Valor |
| --- | --- |
| Proceso activo | `id=4` ERM2026 (el `id=2` de la elección anterior devuelve 403) |
| Menú de elecciones | `proceso/4/elecciones` → Regionales (`idEleccion=1`), Municipales (`idEleccion=3`) |
| Ubigeo Ventanilla | `240106` (Callao, provincia `240100`) |
| Ubigeo San Martín de Porres | `140126` (Lima, provincia `140100`). OJO: `140140` es San Borja |

## Endpoints que responden 200
- `proceso/proceso-electoral-activo`
- `ubigeos/departamentos?idEleccion=3&idAmbitoGeografico=1`
- `ubigeos/provincias?idEleccion=3&idAmbitoGeografico=1&idUbigeoDepartamento=140000`
- `ubigeos/distritos?idEleccion=3&idAmbitoGeografico=1&idUbigeoProvincia=140100`
- `actas?pagina={p}&tamanio=100&idAmbitoGeografico=1&idUbigeo={ubigeo}` — listado por mesa.
  `tamanio` máximo **100** (200 → 400). Cada mesa aparece una vez por elección (`idEleccion`).
  Campos: `id`, `codigoMesa`, `idEleccion`, `codigoEstadoActa` (C contabilizada / E envío al JEE), `descripcionEstadoActa`.

## Endpoint con reto anti-bot (NO se evade)
- `actas/{id}` (detalle con votos por organización, local, electores hábiles, archivos PDF) respondió **HTTP 202 sin cuerpo**
  con `access-control-expose-headers: x-amzn-waf-action` → AWS WAF pide un reto de navegador.
  Funcionó en la primera llamada y dejó de funcionar tras ~100 solicitudes seguidas.
- Decisión: no se resuelve ni se esquiva el reto. Se baja el ritmo (≥2 s entre llamadas, una sola pestaña) y, si el reto
  persiste, el detalle se obtiene navegando como usuario (la SPA lo carga) o se pide a ONPE/JEE por canal oficial.

## Conteos del listado (hoy, 18:40)
| Distrito | Mesas | Elecciones por mesa | Contabilizadas | Para envío al JEE |
| --- | --- | --- | --- | --- |
| Ventanilla | 858 | 4 (`idEleccion` 1–4) | 827 / 819 / 831 / 818 | 31 / 39 / 27 / 40 |
| San Martín de Porres | por medir (`140126`) | por confirmar | — | — |

Pendiente confirmar qué es cada `idEleccion` (1–4): Ventanilla tiene 4 (probable: gobernador regional, consejeros,
alcalde provincial, alcalde distrital); Lima Metropolitana solo 2 (3 y 4).

## Actualización 2026-10-08 (tarde)
- `idEleccion` confirmado por ONPE (según ERRATAS de fastestShipper/erm2026): **3 = alcalde provincial, 4 = alcalde distrital**;
  1 y 2 = gobierno regional (solo Ventanilla/Callao). Lima Metropolitana solo tiene 3 y 4.
- **`actas/buscar/mesa?codigoMesa=NNNNNN`**: una consulta devuelve todas las elecciones de la mesa con votos completos
  (claves `ad*`: `adDescripcion`, `adVotos`). Reduce 7017 consultas a 2644. Sin `archivos` (PDF): esos salen de `actas/{id}`.
- El reto WAF (202 vacío) reaparece a las ~90 consultas seguidas; lo resuelve una persona en Chrome. No se evade.
- No se usa la `cola` de peruvian.dev que consulta ese repo (envía códigos de mesa a un tercero).
