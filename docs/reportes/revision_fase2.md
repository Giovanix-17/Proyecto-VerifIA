# Revisión de la Fase 2 — VerifIA

**Fecha:** 16/11/2026
**Alcance:** verificar el corpus, la partición, la documentación y los scripts de la
Fase 2 contra `VerifIA_memoria_proyecto.md` (§8.2, §8.3 y §9) y la skill
`verifia-corpus`.
**Artefactos revisados:** `data/annotated/corpus.jsonl`,
`data/splits/{train,val,test}.jsonl`, `data/splits/split_manifest.json`,
`data/annotated/correcciones.csv`, `docs/guia_anotacion.md`,
`docs/reportes/cobertura_corpus.md`, `docs/reportes/fuentes_publicas_revisadas.md`,
`scripts/corpus_*.py` y `tests/test_corpus.py`.

## Veredicto

**La Fase 2 cumple los criterios de aceptación.** El corpus tiene 500 mensajes
balanceados, etiquetas confirmadas por el autor, ausencia de duplicados y de PII
bloqueante detectada, y una partición 70/15/15 reproducible con los sintéticos
solo en `train`.

Se identifican **observaciones no bloqueantes** (trazabilidad de la generación,
dominios no reservados, un caso de etiqueta débil y detalles documentales). Ninguna
invalida el corpus ni impide avanzar a la Fase 3.

## Checklist de aceptación

| Requisito | Estado | Evidencia |
|---|---|---|
| 500 mensajes (mínimo 400) | ✅ | 500 en `corpus.jsonl` |
| 100 por clase, 5 clases | ✅ | 100 en cada una de las 5 clases |
| Etiqueta definitiva del autor | ✅ | 500 con `revision_autor = confirmado`; 0 pendientes |
| Orígenes del catálogo | ✅ | `manual: 175`, `plantilla_legitima: 85`, `sintetico_llm: 240` |
| Sintéticos solo en `train` | ✅ | 240 en train; 0 en val y test |
| Partición 70/15/15 estratificada | ✅ | 350 / 75 / 75; 70 / 15 / 15 por clase |
| Sin duplicados exactos | ✅ | 500 textos únicos |
| Sin casi duplicados (coseno < 0.90) | ✅ | Máximo global: **0.6146** (`syn-0085` vs `syn-0107`) |
| Sin PII bloqueante | ✅ (preliminar) | 0 hallazgos en el corpus final; 6 descartes en fuentes (5 correos, 1 RFC) |
| Esquema de anotación válido | ✅ | 0 campos obligatorios vacíos; 0 señales fuera del catálogo |
| Partición reproducible | ✅ | `particionar(seed=42)` reproduce exactamente los ids de los tres splits; hashes del manifiesto verificados |
| Guía de anotación completa | ✅ | Definiciones, señales, fronteras, 5 ejemplos por clase y casos ambiguos |
| Reporte de cobertura | ✅ | Conteos por clase, split, origen y depuración |
| Pruebas automatizadas | ✅ | **22 pruebas pasan**; `ruff check` sin errores |

### Composición verificada

| Split | Total | Por clase | Orígenes |
|---|---:|---|---|
| `train` | 350 | 70 cada una | 240 sintéticos + 110 no sintéticos |
| `val` | 75 | 15 cada una | 63 manual + 12 plantilla |
| `test` | 75 | 15 cada una | 61 manual + 14 plantilla |

Fraude en `train`: 10 manuales + 60 sintéticos por clase. `legitimo` en `train`:
11 manuales + 59 plantillas. La partición es correcta; solo estratifica por
`tipologia`, como pide la memoria.

## Observaciones

### O1. Origen `publico` ausente (limitación declarada)

El corpus no contiene mensajes con `origen: publico`. La memoria pide recolectar
mensajes de fuentes públicas, pero las fuentes revisadas describen modalidades sin
publicar el texto completo. La decisión está documentada en
`docs/reportes/fuentes_publicas_revisadas.md` y no incumple los criterios de
aceptación de la skill (que no exigen ese origen). **No es bloqueante**, pero debe
declararse como limitación de representatividad en el reporte final.

### O2. Bitácora de generación sintética incompleta (histórica; corregida)

`data/synthetic/generation_log.jsonl` conserva **14 llamadas** (13 correctas y 1
error), mientras que `generated.jsonl` contiene **280 mensajes** generados entre
las 22:35 y las 22:54, distribuidos en **48 lotes con salida** (inferidos por
timestamps) más el fallo registrado. Es decir, faltan aproximadamente **35
llamadas** en la bitácora histórica.

La causa probable es que la bitácora se escribía al final de cada corrida y
algunas corridas se interrumpieron antes de guardarla, aunque `generated.jsonl`
sí se escribía después de cada lote. Los mensajes y sus metadatos (`modelo`,
`lote_semilla`, `tipologia_borrador`) están íntegros.

**Corrección aplicada:** `corpus_generate.py` ahora escribe la entrada de la
bitácora inmediatamente después de cada lote. La laguna histórica no se puede
reconstruir (faltan tokens y latencias), pero no se repetirá en futuras corridas.

### O3. Acuerdo borrador ↔ etiqueta humana (registrado)

Los 240 mensajes sintéticos conservan `tipologia_borrador` y **los 240 coinciden**
con la etiqueta final (100 %). El reporte de cobertura ya incluye la sección
“Acuerdo borrador ↔ etiqueta humana” con 240/240, aclarando que es evidencia
adicional y **no** sustituye el kappa del §8.7.

### O4. Política de dominios (confirmada)

Hay **29 enlaces** que usan **20 dominios fuera del conjunto reservado**
(`example.com`, `example.org`, `example.net`, `invalid`), por ejemplo
`pago-seguro-mx.com`, `seguridad.mx`, `empleo.net` y `citatorio-mx.net`.

**Decisión:** se mantiene la política ya planteada en la documentación. Los
dominios inventados forman parte del texto y la Fase 3 los reducirá a
`[ENLACE:dominio.tld]`; no se reescriben en la Fase 2. Se aclaró el comentario de
`scripts/corpus_common.py` y el reporte de cobertura advierte que no se verificó
su existencia. Riesgo residual: alguno podría existir realmente, pero no es PII y
el sanitizador lo elimina antes de cualquier análisis o publicación.

### O5. Señales: la guía decía 1–3 y hay 4 registros con 4 (corregido)

Cuatro mensajes tienen cuatro señales:
`man-ban-039`, `man-paq-001`, `man-paq-020` y `man-ext-023`. La guía ya dice
“de 1 a 4 señales (lo habitual es 1–3)”, que refleja el corpus. El esquema no
impone un tope y no hace falta recortar datos.

### O6. Caso de etiqueta débil: `syn-0147` (resuelto)

```text
Hola. Revisa tu oferta. Para confirmar la labor de medio tiempo, porfa llama al
55 0000 0000. Consulta detalles y requisitos.
```

Estaba etiquetado como `oferta_laboral_fraudulenta`, pero no pide dinero ni datos
antes de contratar, no suplanta una empresa concreta y no tiene señales.

**Decisión del autor:** descartarlo. `corpus_build.py` lo excluye mediante
`EXCLUIDOS_REVISION` y la exclusión queda registrada en el manifiesto
(`excluidos_revision`) y en el reporte de cobertura. Se sustituyó por `syn-0216`,
sintético de oferta con señales `suplantacion` y `solicitud_datos`. El corpus
conserva 500 mensajes (100 por clase) y `syn-0147` no aparece en ningún split.

### O7. Manifiesto sin conteos por split (corregido)

`split_manifest.json` ya incluye `conteos_por_split` con la distribución por
clase y por origen de `train`, `val` y `test`, además de los conteos globales y
los hashes.

### O8. Estado desactualizado en `docs/plan_trabajo.md` (corregido)

La línea 16 ya indica “Aprobado; Fase 1 y Fase 2 completadas (16/11/2026)”.

### O9. Artefactos sin versionar (menor, pendiente)

El repositorio ya es git, pero `data/annotated/`, `data/splits/`, `scripts/` y
`tests/` de la Fase 2 siguen sin commit. No afecta la validez del corpus; sí a la
reproducción y a la entrega. Es decisión del autor cuándo hacer el commit.

## Verificación de la API (16–17/11/2026)

| Rol | Modelo | Resultado |
|---|---|---|
| Corpus | `nvidia/nemotron-3.5-bolt-e4b` | ✅ Genera un mensaje válido; latencia ~14 s; con `max_tokens=2000` |
| Nivel 2 | `minimaxai/minimax-m3.1-flash` | ✅ Devuelve JSON válido; latencia < 6 s |
| Nivel 2 anterior | `deepseek-ai/deepseek-v4.1-flash` | ❌ **HTTP 410**; no aparece en `/v1/models` |
| Revisor | `mistralai/mistral-large-4-1t-a52b` | ✅ JSON válido; 8.24 s |
| Revisor alternativo | `nvidia/nemotron-3.5-lightning-30b-a3b` | ✅ JSON válido; 3.87 s (con `max_tokens=1500`) |

**Hallazgo crítico:** DeepSeek-V4.1-Flash ya no está disponible en la API de
NVIDIA (410 Gone). Se cambió `LLM_MODEL` a MiniMax-M3.1-Flash y se actualizaron
`.env.example`, la memoria (§6.1/§6.2/§9/§11) y la tabla de decisiones. El revisor
del §8.7 quedó definido como Mistral-Large-4-1T-A52B, distinto del Nivel 2. El
detalle y el comando reproducible están en `docs/reportes/verificacion_api.md` y
`scripts/verificar_api.py`.

## Limitaciones de la verificación

- La comprobación de PII de la Fase 2 es regex + Luhn/CLABE. **No cubre nombres**
  ni entidades que requieren NER. Quedan nombres genéricos como `MARÍA LÓPEZ`
  (`leg-007`) y `Ana` (`man-leg-013`, `syn-0175`); Presidio deberá procesarlos en
  la Fase 3.
- La calidad de las etiquetas se verificó por reglas, balance, señales y muestreo;
  no se reanotaron los 500 mensajes. La confirmación del autor es la fuente de
  verdad.
- No se verificó que los dominios inventados no existan en Internet. Por decisión
  del autor se conservan y la Fase 3 los enmascara; se reportan como riesgo
  residual de higiene, no como PII.

## Conclusión

**Fase 2 aprobada.** El corpus es utilizable para entrenar y evaluar la cascada.
Se aplicaron las correcciones O2 (bitácora por lote), O3 (acuerdo 240/240), O5
(guía 1–4), O6 (sustitución de `syn-0147` por `syn-0216`), O7 (manifiesto por
split) y O8 (estado del plan); O4 quedó resuelto con la política de dominios ya
documentada. O9 se cierra con el commit de los artefactos.

**Para la Fase 5:** DeepSeek-V4.1-Flash devuelve 410 y no está en el catálogo;
MiniMax-M3.1-Flash es el Nivel 2 principal y Nemotron funciona para el corpus.
El revisor del §8.7 es Mistral-Large-4-1T-A52B; la verificación está en
`docs/reportes/verificacion_api.md`.
