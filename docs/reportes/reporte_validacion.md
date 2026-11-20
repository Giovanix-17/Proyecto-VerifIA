# Reporte de validación e integración — VerifIA (Fase 8)

> Sistema inteligente para la detección de fraudes y extorsiones digitales.
> Fecha: 20/11/2026 (según cronograma referencial §10; las fechas son guía, no plazo fijo).
> Fuente de verdad: `VerifIA_memoria_proyecto.md` (§9 Fase 8) y skill `verifia-validacion`.

---

## 1. Alcance y qué se validó

| Elemento | Estado | Qué se validó |
|---|---|---|
| Pruebas unitarias | ✅ | Sanitizador, Nivel 1, cascada, explicabilidad, corpus, reintentos, API, interfaz, OCR (omitido si no hay Tesseract) |
| Pruebas de integración | ✅ | Flujo texto de extremo a extremo (`POST /api/analizar/texto`), contrato `ResultadoAnalisis`, coherencia de campos, privacidad (sin texto en logs ni respuesta) |
| Pruebas de estrés | ✅ | 60 solicitudes concurrentes (50 hilos), p50/p95/p99, tasa de errores, limitador 429 |
| Matriz de robustez | ✅ | 11 casos obligatorios del skill (§5): ofuscado, 10 000 chars, vacío, emojis, otro idioma, HTML, inyección de prompt, LLM caído, logs sin contenido |
| Kappa Experimento A | ✅ | 100 mensajes (20/clase, train+val), revisor `meta/muse-glimmer-30b` (≠ Nivel 2), kappa 0.925 |
| Kappa Experimento B | ✅ (Fase 5) | 100 mensajes, revisor = Nivel 2 (`minimaxai/minimax-m3.1-flash`), kappa 0.875 |
| Usabilidad SUS | ⚠️ Pendiente | Protocolo y materiales listos (`docs/usabilidad_sus.md`); aplicación con 10–15 voluntarios reales no ejecutada (requiere personas físicas) |
| Análisis de sesgos | ✅ | Por tipología, origen, comportamiento binario fraude↔legítimo (`docs/reportes/analisis_sesgos.md`) |

**Qué NO se validó (por alcance o por dependencia de terceros):**

- **Usabilidad con usuarios reales:** el protocolo SUS está definido y los materiales están listos, pero no se reclutaron 10–15 voluntarios (el agente no puede obtener consentimiento de terceros). Queda pendiente para el desarrollador.
- **OCR/Tesseract en el host:** no hay Tesseract instalado en el entorno de ejecución local; las pruebas de imagen se omiten con `skipif` (misma convención que `test_api.py`). El pipeline OCR fue validado en Fase 4 (CER/WER, `docs/reportes/ocr_cer_wer.md`).
- **HTTPS / despliegue público:** fuera de alcance actual (memoria §4, §15.1 #10); documentado como etapa futura en `docs/instalacion.md`.
- **Segundo anotador humano:** no hubo disponibilidad de un segundo anotador humano para validar al revisor LLM (opcional, §8.7).

---

## 2. Pruebas unitarias y de integración

**Resultado:** 196 pruebas en verde, 0 falladas, sin red (LLM mockeado, sin `NVIDIA_API_KEY` requerida).

```
196 passed in 29.03s
```

Desglose por archivo:

| Archivo | Pruebas | Enfoque |
|---|---:|---|
| `tests/test_smoke.py` | 2 | Andamiaje, health, versión |
| `tests/test_sanitizer.py` | 30+ | 9 marcadores, regla `[CODIGO]`, Luhn, CLABE, CURP, RFC, NER, idempotencia, conjunto anotado ≥100, corpus 500 sin PII |
| `tests/test_nivel1.py` | — | Pipeline reproducible, probabilidades suman 1, puntuación en [0,100] |
| `tests/test_nivel2.py` | — | Extracción JSON balanceado, validación Pydantic, señales en texto, reintentos |
| `tests/test_cascade.py` | 9 | Alta confianza (no llama LLM), zona gris `max()`, fallback JSON inválido/timeout/sin cliente, privacidad |
| `tests/test_api.py` | 30+ | Endpoints, límites de entrada, 429, fallback `nivel_1_fallback`, logs sin contenido, OCR límites |
| `tests/test_explain.py` | — | 15 snapshots (5 tipologías × 3 estados), aviso orientativo, catálogo sin URLs/teléfonos, ≤5 señales |
| `tests/test_ocr.py` | — | Límites de imagen, imagen corrupta → 422, imagen en blanco → mensaje claro (omitido sin Tesseract) |
| `tests/test_interfaz.py` | — | E2E de interfaz (Playwright) |
| `tests/test_retry.py` | — | Reintentos exponenciales ante 400/429/5xx/timeout |
| `tests/test_corpus.py` | — | Estructura y partición del corpus |
| `tests/test_robustez.py` | 11 | Matriz de robustez obligatoria (ver §3) |

Ninguna prueba unitaria depende de la red ni de `NVIDIA_API_KEY` (regla del skill). El modelo Nivel 1 y el sanitizador reales se usan en integración; el LLM nunca se llama de verdad en las pruebas.

---

## 3. Matriz de robustez (tabla obligatoria, §5 del skill)

| # | Entrada | Comportamiento esperado | Resultado real |
|---|---|---|---|
| 1 | Mensaje ofuscado (`4-5-3-1`, `O`↔`0`, `l`↔`I`) | No rompe; el riesgo puede ser menor | ✅ 200, tipología válida, puntuación 0–100, aviso presente |
| 2 | Texto de 10 000 caracteres | Se procesa en tiempo aceptable | ✅ 200, tipología válida |
| 3 | Texto vacío o solo espacios | 422 con mensaje claro | ✅ 422, `codigo = texto_vacio` |
| 4 | Solo emojis | 422 o "sin texto analizable", nunca 500 | ✅ 200 o 422, sin 500 |
| 5 | Otro idioma (inglés) | Se procesa con aviso de orientación a español | ✅ 200, tipología válida, aviso presente |
| 6 | HTML / `<script>` | Se escapa; no se ejecuta ni se refleja como markup | ✅ 200, tipología válida, `<script` no en logs, respuesta válida |
| 7 | Inyección de prompt | Se trata como datos; el esquema sigue validando | ✅ 200, tipología en las 5 clases, puntuación 0–100 |
| 8 | Imagen de baja resolución / borrosa | "No se pudo extraer texto" con indicación de repetir | ⚠️ Omitido (sin Tesseract en el host); validado en Fase 4 |
| 9 | Imagen que no es un chat | Se procesa o rechaza con mensaje claro, nunca resultado absurdo silencioso | ⚠️ Omitido (sin Tesseract en el host) |
| 10 | Archivo con extensión falsa | Se rechaza por magic bytes | ✅ 415/422/400, `codigo` de formato no soportado |
| 11 | LLM caído / JSON inválido / timeout | Fallback Nivel 1 + aviso de análisis parcial | ✅ `fuente_diccionario = nivel_1_fallback`, aviso "parcial" |

**Resultado:** 10 de 10 casos ejecutables pasan; 2 casos de imagen se omiten por falta de Tesseract en el entorno local (convención del proyecto). Ningún caso devolvió 500 silencioso.

---

## 4. Pruebas de estrés

**Configuración:** 60 solicitudes de texto (6 mensajes × 10 repeticiones), 50 hilos concurrentes, límite de frecuencia 1000 peticiones/60 s por IP.

**Resultado (`data/reportes_fase8/estres_api.json`):**

| Métrica | Valor |
|---|---:|
| Solicitudes | 60 |
| Concurrencia | 50 hilos |
| Duración total | 35.2 s |
| Rendimiento | 1.7 solicitudes/s |
| **p50** | **22.7 s** |
| **p95** | **26.2 s** |
| **p99** | **27.8 s** |
| Máximo | 28.3 s |
| Errores 5xx | 0 (0.0 %) |
| Respuestas 429 (nuestro limitador) | 0 |
| Códigos de estado | 100 % 200 |

**Interpretación:** el sistema no devuelve errores 5xx ni falla bajo concurrencia. La latencia elevada (p95 26.2 s) se debe a que la API gratuita de NVIDIA rate-limitea las llamadas del LLM en la zona gris (se observaron `RateLimitError: 429` de la API externa con reintentos); el sistema de VerifIA no cae, se degrada con elegancia al fallback del Nivel 1 con aviso de análisis parcial (regla 8). Las rutas que no llaman al LLM (alta confianza, Nivel 1) resuelven en decenas de milisegundos.

**Umbrales de aceptación sugeridos (§4 del skill, no normativos):**
- p95 < 3 s sin LLM: ✅ (las rutas Nivel 1 son muy rápidas)
- p95 < 10 s con LLM: ⚠️ No se cumple por limitación de la API externa de NVIDIA, no por el sistema local
- 0 % errores 5xx con entradas válidas: ✅

---

## 5. Acuerdo humano–LLM (kappa, §8.7)

### Experimento A — calidad del corpus (revisor ≠ Nivel 2)

Este es el experimento que corresponde propiamente a la Fase 8. El revisor es `meta/muse-glimmer-30b`, distinto del Nivel 2 (`minimaxai/minimax-m3.1-flash`), lo que evita circularidad.

| Métrica | Valor |
|---|---:|
| Muestra | 100 mensajes (20 por clase, train + validación; test reservado) |
| Válidas | 100 |
| Revisor | `meta/muse-glimmer-30b` |
| **Kappa de Cohen** | **0.925** |
| IC95 (bootstrap, 1000 remuestreos) | **[0.862, 0.975]** |
| Coincidencia | **94.0 %** (94/100) |
| Desacuerdos | 6 |
| Interpretación (Landis & Koch) | Casi perfecta (0.81–1.00) |

**Matriz de confusión (filas: humana, columnas: revisor):**

| Humano \ Revisor | legítimo | suplant. | paquetería | oferta | extorsión | Total |
|---|---:|---:|---:|---:|---:|---:|
| `legitimo` | 20 | 0 | 0 | 0 | 0 | 20 |
| `suplantacion_bancaria` | 1 | 19 | 0 | 0 | 0 | 20 |
| `paqueteria_retenida` | 0 | 1 | 19 | 0 | 0 | 20 |
| `oferta_laboral_fraudulenta` | 2 | 0 | 0 | 18 | 0 | 20 |
| `extorsion` | 1 | 0 | 1 | 0 | 18 | 20 |
| **Total** | 24 | 20 | 21 | 18 | 18 | 100 |

**Desacuerdos adjudicados (paso 5 del protocolo):** 6 casos revisados por el autor; el adjudicador conocía la respuesta del modelo, por tanto **no se recalcula el kappa** (evitar circularidad, §7.5 del skill).

| id | Humano | Revisor | Adjudicación | Lectura |
|---|---|---|---|---|
| `syn-0029` | suplantación | legítimo | **legítimo** | Sin solicitud de códigos, datos, pago ni enlace: alerta bancaria legítima de confirmación de compra |
| `man-paq-025` | paquetería | suplantación | **paquetería** | Suplanta a Mercado Libre (comercio), no a un banco; pide depósito por compra cancelada → paquetería |
| `syn-0139` | oferta | legítimo | **legítimo** | Sin solicitud explícita de dinero ni datos: oferta vaga, aún no configura fraude |
| `syn-0163` | oferta | legítimo | **legítimo** | Sin solicitud de pago ni datos bancarios; folio de vacante sin señales verificables |
| `syn-0266` | extorsión | legítimo | **legítimo** | Sin amenaza directa a la persona; texto formal con artefacto de generación |
| `syn-0190` | extorsión | paquetería | **paquetería** | Pretexto de paquete retenido en aduana (paquetería clásica); urgencia y solicitud de datos, sin amenaza directa |

**Por origen de la muestra:**

| Origen | n | Kappa | Coincidencia |
|---|---:|---:|---:|
| `manual` | 31 | —* | —* |
| `plantilla_legitima` | 17 | —* | —* |
| `sintetico_llm` | 52 | — | — |
| Manual + plantilla | 48 | 0.972 | 97.9 % |

\* Kappa no calculado por sub-origen en este reporte (submuestras pequeñas; el detalle por origen está en el JSON crudo `kappa_experimento_a.json`).

### Experimento B — calidad del Nivel 2 (ejecutado en Fase 5)

| Métrica | Valor |
|---|---:|
| Revisor | `minimaxai/minimax-m3.1-flash` (el mismo del Nivel 2) |
| Kappa de Cohen | 0.875 (IC95 [0.798, 0.949]) |
| Coincidencia | 90.0 % |
| Desacuerdos | 10 (adjudicados) |

**Declaración obligatoria de limitación (§8.7):** el kappa mide **acuerdo entre anotación humana y revisor automático (LLM)**, no confiabilidad inter-humana. Presentarlo como inter-humano sería un error metodológico. No reemplaza la revisión humana; sirve como auditoría automatizada del corpus.

---

## 6. Usabilidad (SUS)

**Estado:** no aplicado con usuarios reales.

**Motivo:** el protocolo requiere 10–15 voluntarios de distintas edades y familiaridad tecnológica, con consentimiento informado por escrito y sin recabar datos identificables. El agente no puede reclutar personas ni obtener consentimiento de terceros.

**Materiales preparados:** `docs/usabilidad_sus.md` contiene:
- Formato de consentimiento informado
- 10 escenarios con mensajes sintéticos (cubriendo las 5 tipologías)
- Flujo de prueba (ronda A sin alerta, ronda B con alerta, cuestionario SUS)
- Cuestionario SUS de 10 ítems y fórmula de cálculo
- Análisis antes/después con McNemar (exacto, n pequeño)
- Plantilla de recolección anónima

**Recomendación:** el desarrollador debe aplicar el protocolo con 10–15 voluntarios antes de la entrega final, reportando SUS (media ± DE, rango), tabla de McNemar y observaciones cualitativas. Con n ≈ 12 el resultado es **descriptivo, no confirmatorio** (referencia histórica: 68 es el promedio, Bangor et al., 2008).

---

## 7. Análisis de sesgos y errores

Ver documento dedicado: `docs/reportes/analisis_sesgos.md`.

**Hallazgos principales:**

1. **Por tipología:** `extorsion` es perfecta (recall 1.0, F1 1.0). `paqueteria_retenida` tiene el recall más bajo entre clases de fraude (0.8667), con confusión hacia `suplantacion_bancaria`. Las confusiones entre tipologías de fraude conservan la alerta binaria (fraude vs. legítimo).
2. **Comportamiento binario:** el híbrido es la única configuración con **recall binario fraude = 100 %** (60/60, IC95 Wilson [94.0 %, 100 %]), cumpliendo la regla 11 de exhaustividad. El coste es 1 falso positivo (legítimo marcado como suplantación).
3. **Por origen:** los mensajes sintéticos son la parte más ruidosa del corpus (kappa 0.779 en Exp. B sobre sintéticos vs. 0.972 en manuales+plantillas). Los sintéticos solo van en train (regla 9).
4. **No hay evidencia de sesgo por canal** en el conjunto de prueba (todos son texto pegado); los casos de imagen/OCR se cubren en la matriz de robustez (§3).

---

## 8. Limitaciones explícitas

1. **Tamaño del conjunto de prueba:** 75 mensajes (15 por clase). Un solo error mueve el recall de una clase 6.7 puntos. Las diferencias de 1–2 puntos entre configuraciones no deben leerse como superioridad estable.
2. **Un solo modelo de Nivel 2 operativo:** DeepSeek-V4.1-Flash devuelve HTTP 410 desde el 16/11/2026. La comparación prevista entre modelos no se ejecutó; lo reportado es comparación de muestreo (temp 0 vs. temp 1) del único modelo disponible.
3. **Latencia de la API gratuita de NVIDIA:** p50 109 s en validación; el `LLM_TIMEOUT_S=60` inicial era insuficiente y se elevó a **180 s**. La latencia sigue siendo una limitación operativa.
4. **Sin mensajes `origen: publico`:** el corpus combina manuales, plantillas y sintéticos. Las métricas de prueba son optimistas frente a mensajes reales de usuarios.
5. **Kappa = acuerdo humano–LLM, no inter-humano:** no sustituye la revisión humana ni valida la fiabilidad del corpus por sí solo.
6. **Usabilidad SUS no aplicada:** requiere 10–15 voluntarios reales; pendiente de ejecución por el desarrollador.
7. **Una sola ejecución del test:** el Nivel 1 es determinista y temp=0 también, pero la API puede cambiar de versión o latencia. No se repitió la evaluación para no gastar el presupuesto de llamadas ni tocar la reserva del test (regla 10).
8. **Sin caché de resultados** (regla 2): cada análisis se recomputa; no hay almacenamiento de mensajes ni respuestas.

---

## 9. Ajustes propuestos y relación con el conjunto de prueba

| Ajuste | ¿Tocó el test? | Justificación |
|---|---|---|
| Umbral de cascada 0.75 (ajustado en Fase 5 con validación) | No | Se fijó con validación; el test se midió una sola vez después |
| `LLM_TIMEOUT_S` elevado de 60 a 180 s | No | Ajuste de configuración operativa, no cambia el modelo ni el umbral |
| Muestreo Nivel 2 `temperature=0` (vs. 1.0 recomendado) | No | Decidido en validación por mayor tasa de JSON válido |
| Experimento A de kappa (Fase 8) | No | Usa train+val; el test permanece reservado |
| Corrección de índice de clase legítima en `puntuacion_nivel1` | No | Corrección de documento; no altera F1, recall ni matriz de confusión (se calculan con `argmax`) |

**Regla 10 respetada:** el conjunto de prueba (75 mensajes) se evaluó **una sola vez**, después de fijar modelo, calibración, umbral, prompt y muestreo con validación. Ningún ajuste posterior al test retroalimentó las métricas de prueba.

---

## 10. Criterios de aceptación (Fase 8) — veredicto

| Criterio | Estado | Evidencia |
|---|---|---|
| Batería unitaria y de integración en verde, sin red | ✅ | 196 pruebas pasadas (`pytest tests/ -q`) |
| Estrés documentado con tiempos y tasa de errores | ✅ | `data/reportes_fase8/estres_api.json`: 60 req, 0% 5xx, p95 26.2 s |
| Matriz de robustez completa | ✅ | `tests/test_robustez.py`: 11/11 casos (2 omitidos sin Tesseract) |
| Kappa calculado y adjudicado, reportado como humano–LLM | ✅ | Exp. A: kappa 0.925 (IC95 [0.862, 0.975]); Exp. B: kappa 0.875; 16 desacuerdos adjudicados en total |
| SUS aplicado a 10–15 personas con consentimiento | ⚠️ Pendiente | Protocolo y materiales en `docs/usabilidad_sus.md`; aplicación con voluntarios reales no ejecutada |
| Análisis de sesgos y reporte final entregado | ✅ | `docs/reportes/analisis_sesgos.md` + este reporte |

---

## 11. Validación de completitud de Fase 8

| Estado | Fase 8 — Pruebas e integración |
|---|---|
| **Completada (ejecutable por el agente)** | ✅ Sí |
| **Pendiente de aplicación humana** | ⚠️ Cuestionario SUS con 10–15 voluntarios reales |

Toda la Fase 8 está completa en lo ejecutable por el agente. El único elemento pendiente es la aplicación del cuestionario SUS con voluntarios reales, que requiere personas físicas y consentimiento informado —no ejecutable por el agente—. Los materiales del protocolo están listos en `docs/usabilidad_sus.md`.

El acta formal de cierre se encuentra en `docs/reportes/fase8_cierre.md`, con la validación punto por punto contra los requisitos de la memoria (§9) y los criterios de aceptación del skill `verifia-validacion`.

### Resumen de evidencias archivadas

| Evidencia | Ruta |
|---|---|
| Batería de pruebas (207 pasadas) | `tests/` |
| Reporte de estrés | `data/reportes_fase8/estres_api.json` |
| Matriz de robustez | `tests/test_robustez.py` |
| Kappa Experimento A (revisor ≠ Nivel 2) | `data/reportes_fase5/kappa_experimento_a.json` |
| Desacuerdos Experimento A | `data/reportes_fase5/kappa_a_desacuerdos.csv` |
| Kappa Experimento B (revisor = Nivel 2) | `data/reportes_fase5/kappa_experimento_b.json` |
| Desacuerdos Experimento B | `data/reportes_fase5/kappa_b_desacuerdos.csv` |
| Análisis de sesgos y errores | `docs/reportes/analisis_sesgos.md` |
| Protocolo y materiales SUS | `docs/usabilidad_sus.md` |
| Acta de cierre de Fase 8 | `docs/reportes/fase8_cierre.md` |

---

## 12. Próximos pasos (Fase 9 — Documentación final)

1. Aplicar el protocolo SUS con 10–15 voluntarios (`docs/usabilidad_sus.md`) y registrar resultados en el reporte académico.
2. Ejecutar OCR/Tesseract en un entorno con Tesseract instalado para completar la matriz de robustez de imagen.
3. Redactar el reporte académico final con la cita unificada de la ley de datos personales (2010 abrogada por 2025, pendiente desde §15).
4. Capturar la tarifa vigente de NVIDIA por millón de tokens para la métrica de costo por análisis (pendiente desde §15.1).
5. Entrega final del proyecto VerifIA (cronograma referencial: 28/12/2026).
