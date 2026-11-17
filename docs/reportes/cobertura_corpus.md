# Cobertura del corpus — VerifIA (Fase 2)

Generado automáticamente por `scripts/corpus_build.py`.
Fecha: 2026-11-17T15:52:57+00:00 · Semilla: `42`.

## Totales

- Mensajes en el corpus: **500**
- Reparto: **350 train / 75 val / 75 test**
- Balance: {"extorsion": 100, "legitimo": 100, "oferta_laboral_fraudulenta": 100, "paqueteria_retenida": 100, "suplantacion_bancaria": 100}
- Orígenes: {"manual": 175, "plantilla_legitima": 85, "sintetico_llm": 240}

## Cobertura por clase

### Train

| Clase | Ejemplos |
|---|---:|
| `legitimo` | 70 |
| `suplantacion_bancaria` | 70 |
| `paqueteria_retenida` | 70 |
| `oferta_laboral_fraudulenta` | 70 |
| `extorsion` | 70 |
| **Total** | **350** |

### Validación

| Clase | Ejemplos |
|---|---:|
| `legitimo` | 15 |
| `suplantacion_bancaria` | 15 |
| `paqueteria_retenida` | 15 |
| `oferta_laboral_fraudulenta` | 15 |
| `extorsion` | 15 |
| **Total** | **75** |

### Prueba (reservada)

| Clase | Ejemplos |
|---|---:|
| `legitimo` | 15 |
| `suplantacion_bancaria` | 15 |
| `paqueteria_retenida` | 15 |
| `oferta_laboral_fraudulenta` | 15 |
| `extorsion` | 15 |
| **Total** | **75** |

## Origen por clase

| Clase | manual | plantilla_legitima | sintetico_llm |
|---|---:|---:|---:|
| `legitimo` | 15 | 85 | 0 |
| `suplantacion_bancaria` | 40 | 0 | 60 |
| `paqueteria_retenida` | 40 | 0 | 60 |
| `oferta_laboral_fraudulenta` | 40 | 0 | 60 |
| `extorsion` | 40 | 0 | 60 |

## Acuerdo borrador ↔ etiqueta humana

- Mensajes con `tipologia_borrador`: **240**
- Coincidencias con la etiqueta final: **240** (100.0 %)
- Discrepancias corregidas por el autor: **0**

Es evidencia adicional de calidad; **no** sustituye el kappa del §8.7.

## Depuración

| Concepto | Cantidad |
|---|---:|
| Duplicados exactos eliminados | 0 |
| Casi duplicados eliminados (coseno ≥ 0.90) | 0 |
| Mensajes descartados por PII bloqueante | 6 |
| Mensajes excluidos por revisión manual | 1 |
| Registros con errores de esquema | 0 |

Los pares descartados y sus similitudes están en `data/annotated/descartes_dedupe.json`.
No se guarda el valor de ningún dato personal detectado (regla 2); solo el tipo.

## Disponibilidad antes de seleccionar

| Clase | No sintéticos | Sintéticos | Seleccionados | Sintéticos usados |
|---|---:|---:|---:|---:|
| `legitimo` | 100 | 0 | 100 | 0 |
| `suplantacion_bancaria` | 40 | 69 | 100 | 60 |
| `paqueteria_retenida` | 40 | 69 | 100 | 60 |
| `oferta_laboral_fraudulenta` | 40 | 65 | 100 | 60 |
| `extorsion` | 40 | 70 | 100 | 60 |

## Verificación de reglas

- [x] 500 mensajes, 100 por clase.
- [x] Sin duplicados exactos ni casi duplicados (coseno < 0.90).
- [x] Sin PII real detectada por el chequeo de la Fase 2.
- [x] `sintetico_llm` solo en `train`.
- [x] Conjunto de prueba reservado (no usar para umbrales ni prompts).
- [x] Revisión humana de etiquetas: 500 confirmadas,
  0 pendientes (`revision_autor`; ver `docs/guia_anotacion.md`).

## Limitaciones y notas

- El corpus no contiene una colección `publico` verbatim. Los boletines y notas
  revisados (Condusef, Guardia Nacional CERT-MX, SSPC, prensa) describen las
  modalidades, pero no publican los mensajes completos; citarlos como ejemplos
  habría exigido inventar el texto. Se documenta como limitación y el esquema
  queda listo para incorporar capturas propias del autor.
- La etiqueta de los mensajes sintéticos se conserva en `tipologia_borrador`.
  La etiqueta final (`tipologia`) fue confirmada por el autor para los 500 mensajes.
- La verificación de PII de esta fase es un chequeo de regex + Luhn/CLABE.
  La Fase 3 la repetirá con Presidio sobre el corpus completo.
- Los enlaces usan dominios inventados (no reservados) y no se verificó que
  existan. La Fase 3 los reduce a `[ENLACE:dominio.tld]`; aquí se conservan como
  señal textual.
- Exclusiones de revisión manual: `syn-0147` — etiqueta débil: oferta sin señales verificables; sustituido por syn-0216.
