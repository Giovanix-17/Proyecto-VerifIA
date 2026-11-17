# VerifIA — Memoria de proyecto

> Sistema inteligente para la detección de fraudes y extorsiones digitales.
> Documento de referencia para desarrollar el prototipo con **opencode**. Se le entrega a opencode como la fuente del proyecto.
> Fuente: *Propuesta_proyecto_IA.docx* (Octubre 2026).
> **Revisión 2 (octubre 2026):** incorporates las decisiones de implementación acordadas entre el desarrollador y el agente (ver §15.1).

---

## 0. Cómo debe usar este archivo el agente

- Léelo completo antes de escribir código. Es la fuente de verdad del proyecto.
- Trabaja **fase por fase** (sección 9), en orden, y no avances a la siguiente sin cumplir los criterios de aceptación de la actual.
- Respeta las **reglas de diseño no negociables** (sección 7).
- Si algo no está definido aquí (ver sección 15), **pregunta al desarrollador** en lugar de inventarlo.
- Mantén el proyecto **simple**: implementa solo lo descrito en este archivo, sin funcionalidades extra ni complejidad adicional.
- El desarrollador es estudiante: explica brevemente las decisiones técnicas y los términos nuevos mientras trabajas.
- Las secciones marcadas como *sugerencia* no vienen de la propuesta original; son ayudas para organizar el trabajo.
- **Al iniciar cada fase, carga la skill que indica la §17** (y las de apoyo que correspondan). Las skills están instaladas en `.agents/skills/` y contienen los detalles operativos de cada módulo; esta memoria sigue siendo la fuente de verdad si hay conflicto.

---

## 1. Resumen ejecutivo

| Campo | Valor |
|---|---|
| Nombre | **VerifIA** |
| Tipo | Desarrollo tecnológico aplicado, experimental; prototipo de software con componentes de IA |
| Qué hace | Analiza mensajes de texto y capturas de pantalla en español, y devuelve nivel de riesgo, tipo de fraude probable, frases de alerta y acciones seguras recomendadas |
| Usuario objetivo | Ciudadanos sin conocimientos técnicos que reciben mensajes sospechosos |
| Enfoque técnico | Clasificación **híbrida en cascada**: filtro clásico rápido (TF-IDF + ML clásico) + LLM con salida estructurada para casos ambiguos |
| Entradas | Texto pegado o imagen (PNG/JPEG) de una conversación |
| Salida | Semáforo de riesgo (verde/amarillo/rojo) + tipología + señales de alerta resaltadas + recomendaciones |
| Duración | Referencial: 29/09/2026 → 28/12/2026 (12 semanas). Es solo una guía; no hay que seguir estas fechas al pie de la letra |
| Despliegue | **Prototipo local** en contenedor Docker (Docker Desktop / WSL2), servido en `http://localhost:8000`. HTTPS queda documentado como requisito de un futuro despliegue público |
| Costo operativo | ~$0. Todo el stack es open source; el único servicio de terceros es la API gratuita de NVIDIA (créditos de prueba) |

### Contexto académico

- Universidad Tecnológica de Tabasco — División Académica de Tecnologías de la Información y Comunicación
- Ingeniería en TI e Innovación Digital (1-A, Redes)
- Asignatura: Fundamentos de Inteligencia Artificial
- Docente: Alfredo de Jesús Gutiérrez Gómez
- Autor: Giovani Hernández Arias
- Parrilla, Centro, Tabasco, octubre 2026

---

## 2. Problema y justificación

**Problema.** El fraude y la extorsión por medios digitais (SMS, mensajería instantánea, correo) crecen de forma sostenida en México, según Condusef (2024). Las modalidades más comunes son suplantación bancaria, paquetería retenida, ofertas laborales falsas y extorsión; inducen a la víctima a dar códigos, hacer transferencias o entregar datos bajo presión emocional. Afecta más a personas con menor alfabetización digital.

**Justificación.**
- Hace falta una herramienta accesible que permita validar un mensaje sospechoso *antes* de actuar.
- Impacto tecnológico: pipeline de IA aplicado a un problema local.
- Impacto social: cultura de prevención del fraude digital.
- Impacto ético: sanitización de datos personales antes de cualquier clasificación.
- No existe una herramienta sencilla para la ciudadanía que reúna estas técnicas con los tipos de fraude que circulan en México; las colecciones públicas (p. ej. SMS Spam Collection) están en inglés.

---

## 3. Objetivos

**Objetivo general.** Desarrollar un sistema inteligente de clasificación de mensajes y capturas de pantalla sospechosas, usando PLN y OCR, para alertar sobre posibles fraudes o extorsiones y sugerir acciones seguras.

**Objetivos específicos.**
1. **OE1 — Sanitización:** módulo que enmascare teléfonos, correos, nombres y datos bancarios antes del procesamiento.
2. **OE2 — OCR:** módulo que extraiga texto de capturas de pantalla.
3. **OE3 — Clasificador:** modelo híbrido que identifique la tipología del fraude y asigne un nivel de riesgo cuantificable.
4. **OE4 — Interfaz:** interfaz web accesible para ingresar mensajes o capturas y recibir recomendaciones.

---

## 4. Alcances y límites

**Alcances (sí incluye).**
- Prototipo funcional que analiza texto y capturas **en español**.
- Sanitización previa a cualquier análisis.
- Clasificador híbrido: nivel de riesgo, tipología y recomendaciones.
- Interfaz web funcional.
- OCR orientado a capturas de apps de mensajería comunes en México.
- Recursos de cómputo accesibles, ejecutable en una sola computadora.
- Contenedor Docker reproducible (Docker Desktop / WSL2) que levanta todo el sistema en `localhost`.

**Límites (NO incluye).**
- Integración directa con plataformas de mensajería o sistemas bancarios (el usuario ingresa texto o imagen manualmente).
- Aplicación móvil nativa (solo web).
- Denuncias automáticas ante autoridades (solo alertas informativas y recomendaciones).
- OCR no garantiza resultados en imágenes de baja resolución o con interferencias significativas.
- **HTTPS, dominio público y despliegue en la nube quedan fuera del alcance actual**: el prototipo corre en `localhost`. Se documenta la ruta de publicación futura (§9 Fase 7) sin implementarla.
- Sin autenticación ni multiusuario (prototipo de un solo operador).
- Sin base de datos, sin Redis, sin cola de trabajos, sin RAG, sin embeddings, sin fine-tuning, sin orquestadores externos.
- Sin caché de resultados: no se almacenan mensajes ni respuestas (regla 2).

---

## 5. Arquitectura

Pipeline de módulos desacoplados:

```
Mensaje de texto ─────────────────────────┐
                                          ▼
Captura de pantalla → Módulo OCR ──► Sanitización de datos personales
                 (Tesseract + OpenCV)     (Presidio + regex/NER)
                                          │
                                          ▼
                              Nivel 1: filtro rápido
                              (TF-IDF + clasificador clásico)
                                          │
                                          ▼
                              Decisión por umbral de confianza
                               │                          │
                        confianza alta                 zona gris
                               │                          ▼
                               │              Nivel 2: LLM con salida
                               │              estructurada (JSON)
                               ▼                          │
                  Generador de explicabilidad y recomendaciones
                  (semáforo + señales de alerta + acciones seguras)
                                          │
                                          ▼
                              Resultado mostrado al usuario
```

Principio clave: **ningún clasificador recibe datos personales**; todo texto pasa por sanitización primero.

**El LLM (Nivel 2) recibe exclusivamente texto ya sanitizado.** Aunque los modelos disponibles en la API de NVIDIA acepten imágenes, el prototipo **no** envía la captura al LLM: hacerlo expondría los datos personales que la sanitización elimina. La imagen se procesa siempre de forma local (OCR con Tesseract) y solo el texto resultante viaja al modelo. Esta decisión se documenta como parte del diseño de protección de datos.

---

## 6. Stack tecnológico previsto

| Componente | Herramienta | Finalidad |
|---|---|---|
| Lenguaje | Python | Servicio y módulos de IA |
| ML clásico | scikit-learn | TF-IDF, clasificadores, validación cruzada, métricas |
| Sanitización | **Microsoft Presidio** (base obligatoria) + regex/NER en español | Detección y enmascarado de datos personales |
| NER | spaCy `es_core_news_md` | Motor de reconocimiento de entidades en español para Presidio |
| OCR | Tesseract (paquete `spa`) + OpenCV | Extracción de texto y preprocesamiento |
| LLM | API de NVIDIA (modelos gratuitos) con salida estructurada | Segundo nivel de análisis y justificación |
| Validación de respuestas | Pydantic (esquemas JSON) | Verificar el formato de salida del LLM |
| Servicio web | FastAPI + Uvicorn | API para texto e imágenes |
| Interfaz | HTML, CSS, JavaScript (estático, sin build ni npm) | Web accesible y adaptable a móviles |
| Pruebas / versiones | pytest, Git | Pruebas automatizadas y control de código |
| Contenedor | Docker Desktop (WSL2), `docker compose` | Entorno reproducible del prototipo en `localhost` |
| Despliegue público (futuro, fuera de alcance actual) | Caddy + Let's Encrypt | TLS automático ante dominio propio |

Las herramientas pueden ajustarse si los resultados de las pruebas lo requieren.

### 6.1 Configuración del LLM (NVIDIA API)

La clave va en `.env` como `NVIDIA_API_KEY`. **Solo se usa la API de NVIDIA**; no se despliega ningún modelo local. Los modelos concretos, su rol y sus especificaciones están definidos en la tabla siguiente y en §6.2.

| Rol | Modelo | Motivo de la elección |
|---|---|---|
| **Nivel 2 (cascada)** — principal | `minimaxai/minimax-m3.1-flash` | 428B / 23B activos, *Structured Output* explícito; **único candidato operativo** tras el HTTP 410 de DeepSeek (verificado el 17/11/2026). Licencia "research and development only" en NVIDIA, a citar en el reporte |
| **Nivel 2 — alternativa** | `deepseek-ai/deepseek-v4.1-flash` (**no disponible**: HTTP 410 desde el 16/11/2026) | Base MIT, 552B / 8B activos, KV cache en FP4 (890 bytes/token) → menor latencia y costo; se conserva como referencia histórica y se reevaluará si NVIDIA lo repone |
| **Revisor automático** (kappa, §8.7) | `meta/muse-glimmer-30b` | Modelo distinto del Nivel 2 para evitar circularidad. JSON válido en 35.6–36.2 s con el prompt real; Mistral-Large-4 se descartó por latencias de 90–175 s, incompatibles con el timeout de 60 s (verificado el 17/11/2026) |
| **Generación del corpus** (Fase 2) | `nvidia/nemotron-3.5-bolt-e4b` | 8B (4B efectivos), Apache 2.0, español entre los idiomas focales de su post-training, *Structured Output*; barato y rápido para generar cientos de mensajes |

El modelo se elige con variables de entorno, sin tocar código:

```
NVIDIA_API_KEY=...
LLM_MODEL=minimaxai/minimax-m3.1-flash        # Nivel 2 (DeepSeek devuelve 410)
LLM_REVIEWER_MODEL=meta/muse-glimmer-30b      # revisor automático (kappa)
LLM_CORPUS_MODEL=nvidia/nemotron-3.5-bolt-e4b     # generación de corpus sintético
LLM_TIMEOUT_S=60
LLM_MAX_TOKENS=1300
LLM_MAX_REINTENTOS=3
LLM_RETRY_BASE_S=2
LLM_REASONING_EFFORT=low
```

**Parámetros de llamada.** Endpoint `https://integrate.api.nvidia.com/v1/chat/completions`, compatible con la API de OpenAI (`openai` de Python con `base_url` NVIDIA).

- `timeout` 60 s, hasta **3 intentos** con espera exponencial (2, 4, 8 s) ante 400/429/5xx/timeout, `max_tokens` 1300.
- `reasoning_effort` **bajo**: ambos modelos grandes son "razonadores" y emiten un bloque de razonamiento antes de la respuesta; para una tarea de 5 clases el esfuerzo alto solo añade latencia y costo.
- **Muestreo:** los modelos recomiendan `temperature=1.0`, `top_p=0.95`, pero para una clasificación repetible se prueba en la Fase 5 `temperature=0` contra el valor recomendado y **se conserva el que tenga mayor tasa de JSON válido y mayor acuerdo con las etiquetas humanas**. La comparación queda documentada.
- **Extracción del JSON:** la respuesta útil viene dentro de `content`, después del bloque de razonamiento (`reasoning_content`). El parser debe **extraer el primer objeto JSON balanceado** del texto, no asumir que todo `content` es JSON. Si la extracción o la validación Pydantic fallan → fallback (regla 8).
- **Sin caché de respuestas:** cachear texto + dictamen equivaldría a almacenar mensajes (regla 2).

### 6.2 Especificaciones de los modelos (fichas de build.nvidia.com, consulta octubre 2026)

| | DeepSeek-V4.1-Flash | MiniMax-M3.1-Flash | Nemotron-3.5-Bolt-E4B |
|---|---|---|---|
| Publicador / ID API | `deepseek-ai/deepseek-v4.1-flash` | `minimaxai/minimax-m3.1-flash` | `nvidia/nemotron-3.5-bolt-e4b` |
| Arquitectura | MoE (cod. 20 + dec. 20 capas) | MoE | MoE (Gemma-4-E4B) |
| Parámetros | 552B / 8B activos (prefill), 16B (decode) | ~428B / 23B activos | 8B / 4B efectivos |
| Contexto | 1,048,576 tokens | hasta 1,000,000 (la ficha "Specifications" indica 262,144) | 65,536 |
| Entrada / salida | Texto, Imagen → Texto | Texto, Imagen → Texto | Texto → Texto |
| Function calling | Sí | Sí | Sí |
| Structured output | Protocolo con respuestas estructuradas | **Soporte explícito** | **Soporte explícito** |
| Reasoning | `reasoning_effort` 1–100 | `low, medium, high, xhigh, max` | configurable (thinking on/off) |
| Licencia del modelo base | MIT + NVIDIA Open Model Agreement ("commercial or non-commercial") | MINIMAX Community License ("research and development only" en NVIDIA) | Apache 2.0 + OpenMDW |
| Publicación en NVIDIA | 18/09/2026 | 22/10/2026 | 23/10/2026 |

Notas para el reporte:
- **Disponibilidad (17/11/2026):** DeepSeek-V4.1-Flash devuelve HTTP 410 y no aparece en `/v1/models`; el Nivel 2 queda en MiniMax-M3.1-Flash. Los datos de DeepSeek se conservan como referencia de la comparación prevista y por si NVIDIA lo repone.
- Los benchmarks publicados por los proveedores **no están verificados de forma independiente por NVIDIA** y ninguno mide español ni fraude; la comparación empírica entre ambos modelos grandes **no pudo ejecutarse** por el 410. MiniMax se evaluará como único Nivel 2 operativo en la Fase 5.
- Nemotron-3.5-Bolt-E4B está pensado por NVIDIA para *customization y post-training*, no para inferencia en producción: encaja con su uso real en este proyecto (generar el corpus de entrenamiento).
- En NVIDIA la API se rige por el *NVIDIA API Trial Terms of Service* (créditos de prueba y límites de uso). Esto obliga a usar el modelo pequeño para el trabajo masivo (§9 Fase 2) y a que el fallback al Nivel 1 sea real, no teórico (regla 8).

### 6.3 Presupuesto de llamadas estimado

| Uso | Llamadas aprox. |
|---|---|
| Generación de corpus sintético (Fase 2.2) | ~250–400 (modelo pequeño) |
| Ajuste de umbral y evaluación (validación, Fase 5) | ~75 |
| Revisor automático / kappa (2 experimentos) | ~200 |
| Evaluación "solo Nivel 2" sobre el conjunto de prueba | ~75 |
| Pruebas de integración | ~30 |
| **Total** | **~530–780** |

Si el saldo de prueba se agota, la reducción de impacto es: reducir el corpus sintético (nunca la evaluación del conjunto de prueba, que está reservado) y conservar el fallback al Nivel 1.

---

## 7. Reglas de diseño no negociables

Provienen directamente de la propuesta:

1. **Sanitizar antes de clasificar.** Ni el clasificador clásico ni el LLM ven datos personales.
2. **No almacenar** mensajes ni imágenes originales. Sin tabla de equivalencias de los datos enmascarados. Tampoco se cachean las respuestas del LLM.
3. **Marcadores tipificados**, no borrado. Catálogo definitivo (9):
   `[TELEFONO]`, `[CORREO]`, `[NOMBRE]`, `[CUENTA]`, `[TARJETA]`, `[CODIGO]`, `[CURP]`, `[RFC]`, `[ENLACE:dominio.tld]`.
   Conservan la señal sin revelar el dato.
4. De los **enlaces** se conserva **solo el dominio**: el marcador es `[ENLACE:dominio.tld]` (p. ej. `[ENLACE:bit.ly]`, `[ENLACE:banco-verify.com]`). La ruta, los parámetros y el resto de la URL se descartan. Las **señales estructurales** del enlace (acortador de URL, IP literal, exceso de subdominios, TLD dudoso, guiones acumulados) se calculan como rasgos para el Nivel 1, no como texto.
5. En la sanitización, **priorizar exhaustividad sobre precisión** y documentar casos residuales.
6. **Las recomendaciones salen de un catálogo predefinido por tipología**, NO las genera el LLM (evita que invente teléfonos, enlaces o instrucciones).
7. **Validar la salida del LLM** con esquema (Pydantic); manejar alucinaciones y formato inválido.
8. **Fallback:** si el LLM no está disponible, devuelve el resultado del Nivel 1 con aviso de *análisis parcial*.
9. **Los datos generados con LLM (`sintetico_llm`) solo se usan en entrenamiento**, nunca en validación ni prueba. Se marcan con su origen y se revisan manualmente. (Ver §8: los ejemplos de origen `manual`, redactados de forma independiente por el autor y no derivados de ejemplos de entrenamiento, sí pueden aparecer en validación y prueba; el objetivo de la regla es evitar fuga por casi duplicados generados.)
10. **El conjunto de prueba (15 %) permanece reservado** hasta la evaluación final.
11. En alertas, **pesa más la exhaustividad (recall)** en las clases de fraude, sin ignorar las falsas alarmas.
12. Credenciales del LLM en **variables de entorno**, nunca en el código fuente.
13. Cada resultado indica que la herramienta es **orientativa** y no sustituye el criterio del usuario ni la denuncia formal.

### 7.1 Regla de enmascarado de `[CODIGO]`

La exhaustividad (regla 5) no puede significar "tapar todos los números", porque los **montos son una señal de fraude** (`transfiera $5,000`). Criterio:

- Se enmascara como `[CODIGO]` **solo si** son 4–8 dígitos **y** aparecen a ≤ 30 caracteres de una palabra clave de solicitud: `código, clave, token, OTP, pin, nip, cvv, contraseña, verificar, confirma, número de seguridad`.
- **No** se enmascaran: montos con `$` o "pesos", porcentajes, fechas, horas, folios, números de orden.
- Casos residuales que se documentan (regla 5): números escritos con palabras ("tres mil"), ofuscación deliberada (`4-5-3-1`, `O`↔`0`, `l`↔`I`), datos sin contexto reconocible.

---

## 8. Modelo de datos y clasificación

### 8.1 Clases (tipología)

1. Mensaje legítimo
2. Suplantación bancaria
3. Paquetería retenida
4. Oferta laboral fraudulenta
5. Extorsión

### 8.2 Esquema de anotación por mensaje

| Campo | Obligatorio | Descripción |
|---|---|---|
| `id` | Sí | Identificador único del mensaje |
| `texto` | Sí | Texto en español (ya saneado de PII real) |
| `tipologia` | Sí | Una de las 5 clases de §8.1. **Único campo usado para entrenar** |
| `senales_alerta` | No | Lista de señales detectadas (urgencia, amenaza, suplantación, solicitud de datos o códigos, enlaces sospechosos) |
| `nivel_riesgo` | No | Bajo / medio / alto. **Solo como referencia para análisis de errores**; el nivel que muestra el sistema siempre es derivado de la puntuación |
| `origen` | Sí | `publico` · `sintetico_llm` · `manual` · `plantilla_legitima` |
| `revision_llm` | No | Resultado del revisor automático (kappa), si aplica |

**Guía de anotación** (`docs/guia_anotacion.md`) que define cada clase, con ejemplos. Se reduce la carga de anotación decidiendo **una sola etiqueta por mensaje** (la tipología); el nivel de riesgo se deriva siempre de la puntuación del modelo.

### 8.3 Corpus

- **500 mensajes en español**, balanceados entre las 5 clases (100 por clase). Mínimo aceptable: 400.
- Por origen:
  - `publico`: repositorios públicos y boletines de instituciones de seguridad cibernética / protección al usuario financiero.
  - `plantilla_legitima`: notificaciones cotidianas de plantillas públicas, sin datos personales.
  - `manual`: redactados por el autor de forma independiente, **no derivados de ejemplos de entrenamiento**; pueden estar en validación y prueba.
  - `sintetico_llm`: generados con `nvidia/nemotron-3.5-bolt-e4b`, con modismos y esquemas de fraude comunes en México. **Exclusivos de entrenamiento** (regla 9), revisados manualmente.
- **Depuración:** normalización de codificación, eliminación de duplicados y **casi duplicados** (similitud coseno de TF-IDF de char 4-gramas ≥ 0.90), y verificación de que no haya datos personales reales.
- **Partición estratificada:** 70 % train / 15 % validación / 15 % test. El test permanece reservado hasta la evaluación final (regla 10).

### 8.4 Salida estructurada del LLM (Nivel 2)

Debe devolver un objeto JSON con: tipología, nivel de riesgo, puntuación 0–100, señales de alerta (frase textual + motivo) y justificación breve.

*Ejemplo ilustrativo (sugerencia, no es el esquema final):*

```json
{
  "tipologia": "suplantacion_bancaria",
  "nivel_riesgo": "alto",
  "puntuacion": 92,
  "senales_alerta": [
    {"frase": "su cuenta será bloqueada hoy", "motivo": "urgencia y amenaza"},
    {"frase": "ingrese su código en [ENLACE:banco-verify.com]", "motivo": "solicitud de código"}
  ],
  "justificacion": "Suplanta a un banco y presiona para entregar un código."
}
```

**Esquema Pydantic (`src/verifia/schemas.py`).** Valida: `tipologia` ∈ las 5 clases; `nivel_riesgo` ∈ {bajo, medio, alto}; `0 ≤ puntuacion ≤ 100`; lista de señales con `frase` (debe aparecer en el texto sanitizado) y `motivo`; `justificacion` no vacía. **Coherencia obligatoria:** el `nivel_riesgo` debe coincidir con la banda de la `puntuacion` (§8.6); si no coincide, la salida del LLM se descarta y aplica el fallback.

### 8.5 Semáforo de riesgo

| Color | Puntuación | Significado | Acción |
|---|---|---|---|
| Verde | 0–33 | Riesgo bajo | — |
| Amarillo | 34–66 | Riesgo medio | Se recomienda verificar |
| Rojo | 67–100 | Riesgo alto | No actuar conforme al mensaje |

Rangos iniciales sencillos; se pueden mover un poco al ver los resultados de validación, sin complicarlo más.

### 8.6 De probabilidad a puntuación y regla de decisión

El Nivel 1 entrega probabilidades; el semáforo exige una puntuación 0–100. Definición única:

```
puntuacion_nivel1 = round(100 × (1 − P(mensaje_legitimo)))
```

(se usa el modelo calibrado: `CalibratedClassifierCV` en SVM, o regresión logística).

**Cascada:**

1. Si `P(máxima) ≥ 0.80` → **se resuelve en el Nivel 1**. `puntuacion = puntuacion_nivel1`. El LLM no se llama. El semáforo sale de esa puntuación.
2. Si `P(máxima) < 0.80` → **zona gris**: se llama al Nivel 2.
   - Si el JSON es válido → `puntuacion = max(puntuacion_LLM, puntuacion_nivel1)` (ante discrepancia se conserva el **riesgo mayor**, en línea con la regla 11 de exhaustividad) y se registra `discrepancia_niveles: true`.
   - Si el JSON es inválido, la API falla o no hay `NVIDIA_API_KEY` → `puntuacion = puntuacion_nivel1` + aviso visible de **análisis parcial** (regla 8).
3. El **0.80** es un valor inicial: se ajusta **una sola vez** con el conjunto de validación para lograr **recall ≥ 90 %** en las clases de fraude sin escalar demasiados mensajes al LLM.

**Respuesta del sistema** (campos mínimos): `tipologia`, `nivel_riesgo`, `puntuacion`, `senales_alerta`, `justificacion`, `resumen_legible`, `recomendaciones[]`, `advertencias[]` (p. ej. "análisis parcial: el modelo avanzado no estuvo disponible"), `fuente_diccionario` (`nivel_1` · `nivel_2` · `nivel_1_fallback`), `escalado_a_llm` (bool), `discrepancia_niveles` (bool).

### 8.7 Fiabilidad de la anotación: revisor automático con LLM

No se cuenta con un segundo anotador humano. Para no dejar vacía la verificación de la calidad del corpus, **el segundo revisor es un modelo de lenguaje**, que se aplica sobre el **20 % estratificado** del corpus (100 mensajes con 500 → 20 por clase, mínimo estadísticamente razonable).

**Protocolo:**

1. **Muestreo** aleatorio estratificado por clase (20 %).
2. **Insumo:** el texto **ya sanitizado** (nunca el original con PII) + la guía de anotación + la lista cerrada de 5 clases. `temperature=0`, salida JSON con un solo campo `tipologia`.
3. **Modelo del revisor:** `meta/muse-glimmer-30b` (§6.1), distinto del Nivel 2 para evitar circularidad. La justificación y el sondeo están en `docs/reportes/verificacion_api.md`.
4. **Cálculo:** `cohen_kappa_score` (scikit-learn), matriz de confusión humano↔LLM y porcentaje de coincidencia.
5. **Adjudicación manual:** en los desacuerdos, el autor decide la etiqueta correcta y registra el motivo. Estos casos son la **cola de revisión manual** que ya exige la regla 9 para los datos sintéticos: el trabajo no se duplica.
6. **Reporte:** `docs/reportes/kappa_revisor_automatico.md` con el valor de kappa, la tabla de coincidencias, los casos adjudicados y el análisis de errores.

**Dos experimentos, con respuestas distintas:**

- **Experimento A (calidad del corpus):** revisor = modelo distinto al de Nivel 2 → ¿la guía de anotación es clara? ¿el corpus es consistente?
- **Experimento B (calidad del Nivel 2):** revisor = el modelo que se usará como Nivel 2 → ¿el LLM clasifica con la misma fiabilidad que el anotador humano? Es **evidencia directa para justificar el Nivel 2** de la cascada.

**Interpretación (Landis & Koch):** < 0 nula · 0.01–0.20 leve · 0.21–0.40 moderada · 0.41–0.60 *fair* · 0.61–0.80 sustancial · 0.81–1 casi perfecta.

**Lo que hay que declarar en el reporte final (limitación explícita):**

- El kappa obtenido mide **acuerdo entre anotación humana y revisor automático (LLM)**, **no** confiabilidad inter-humana. Presentarlo como inter-humano sería un error metodológico.
- No reemplaza la revisión humana: sirve como **auditoría automatizada del corpus** (detecta clases ambiguas, textos mal etiquetados y guías poco claras).
- Riesgo de circularidad: por eso revisor y Nivel 2 son modelos distintos.
- Si el docente o un compañero acepta realizar una **segunda anotación humana** sobre un subconjunto menor (≈ 10 %, ~50 mensajes), esa revisión valida al propio LLM-revisor y se reporta como evidencia cruzada. Es opcional y depende de la disponibilidad de un segundo anotador.

---

## 9. Fases de desarrollo

Cada fase corresponde a una actividad de la propuesta y a un objetivo específico.

### Fase 1 — Planeación y alcance (Actividad 1)
- Documento de planeación: alcance técnico, recursos, tecnologías, criterios de éxito, roles → `docs/plan_trabajo.md`.
- Estructura del repositorio, entorno de trabajo, `.env.example` y contenedor (`Dockerfile` + `docker-compose.yml`).
- Guía de instalación local → `docs/instalacion.md` (Docker Desktop como camino principal, venv como alternativa).
- Cronograma validado (ya definido en §10).
- **Entregable:** plan de trabajo aprobado.

### Fase 2 — Recopilación y curación del corpus (Actividad 2)
- Recolectar mensajes de fuentes públicas y boletines (`origen: publico`).
- Generar ejemplos sintéticos con `nvidia/nemotron-3.5-bolt-e4b` en **lotes con control de ritmo** (pacing) para respetar los límites de la API; salida JSON con `mensaje`, `tipologia` y `senales_alerta` (`origen: sintetico_llm`, solo train).
  - La `tipologia` que propone el LLM es **solo un borrador**: **la etiqueta definitiva la asigna el autor** siguiendo `docs/guia_anotacion.md`. El nivel de coincidencia entre el borrador del LLM y la etiqueta humana se registra como evidencia adicional de calidad (no sustituye al protocolo de §8.7).
- Redactar manualmente los ejemplos de origen `manual` y las plantillas legítimas.
- Depurar: normalización, duplicados y casi duplicados (TF-IDF char 4-gramas ≥ 0.90), verificación de ausencia de PII real.
- Partición estratificada 70/15/15 y reserva del conjunto de prueba.
- **Entregable:** corpus anotado y balanceado de **500 ejemplos** (100 por clase), con `docs/guia_anotacion.md` y el reporte de cobertura de las 5 clases.

### Fase 3 — Módulo de sanitización (Actividad 3, OE1)
- **Base obligatoria: Microsoft Presidio** (`AnalyzerEngine`) con motor spaCy `es_core_news_md` en español.
- **Entidades a detectar:** teléfonos (con lada y prefijo +52), correos, tarjetas (validar con algoritmo de **Luhn**), cuentas **CLABE** (con dígito de control), **CURP**, **RFC** (persona física y moral) y nombres de personas.
- **Técnicas:** las reglas de formato se implementan como `PatternRecognizer` personalizados de Presidio (regex + contexto + `validate_result` para Luhn y dígito de control de CLABE); los nombres se detectan con el NER en español de spaCy.
- **Marcadores de salida:** los 9 de la regla 3, con el criterio de `[CODIGO]` de §7.1.
- **Validación:** conjunto de **≥100 mensajes** con datos personales anotados a mano; medir cobertura y precisión por tipo de entidad; documentar casos residuales.
- **Entregable:** módulo de sanitización validado e integrado al flujo, con pruebas unitarias (pytest) que verifiquen que ningún dato personal sobrevive al enmascarado.

### Fase 4 — Módulo OCR (Actividad 4, OE2)
- **Entrada:** PNG o JPEG, **≤ 5 MB**, **lado mayor ≤ 4000 px** y **≤ 12 MP** (se aplica el límite que se alcance primero); si se exceden los límites, informar al usuario (no escalar).
- **Preprocesamiento (OpenCV):** escala de grises, ampliación de resolución, reducción de ruido, binarización adaptativa, inversión de colores en modo oscuro. Evaluar segmentar para excluir barras de estado, encabezados y campos de escritura.
- **Extracción:** Tesseract con paquete de español (`spa`) y modos de segmentación ajustados a conversaciones.
- **Posprocesamiento:** unir líneas de un mismo globo, corregir caracteres confundidos, eliminar marcas de hora; **mostrar el texto al usuario para que corrija errores antes del análisis**.
- **Evaluación:** **≥50 capturas** de apps de mensajería de uso común en México y del servicio de mensajes del teléfono, modo claro y oscuro, distintas resoluciones, solo mensajes de prueba. Métricas: **CER** y **WER** contra transcripción manual. Meta de referencia: **CER ≤ 15 %** en capturas de calidad aceptable; si no se alcanza, ajustar el preprocesamiento. Si la imagen es insuficiente, informar al usuario.
- **Entregable:** pipeline funcional imagen → texto.

### Fase 5 — Clasificador de riesgo (Actividad 5, OE3)

**Nivel 1 — filtro rápido (modelos clásicos)**
- Entrada: texto sanitizado.
- Características: TF-IDF de palabras (unigramas + bigramas), TF-IDF de caracteres (n-gramas 3–5, tolera escritura ofuscada), y rasgos estructurales (tipo de enlace, acortadores de URL, proporción de mayúsculas, longitud, marcadores de datos sanitizados).
- Modelos a comparar: regresión logística, SVM lineal, Naive Bayes (sin XGBoost). Se queda el de mejor F1 en validación.
- Validación cruzada estratificada de 5 pliegues + búsqueda en cuadrícula; ponderación de clases por desbalance.

**Nivel 2 — LLM con salida estructurada**
- Prompt con: rol, definiciones de cada tipología, tácticas de ingeniería social y casos resueltos (few-shot).
- Modelo: `minimaxai/minimax-m3.1-flash` (§6.1), con `reasoning_effort` bajo. DeepSeek-V4.1-Flash queda descartado por HTTP 410.
- Salida JSON validada con Pydantic (§8.4), extracción robusta del bloque JSON desde `content`.
- Si el JSON es inválido o la API falla, usar el fallback del Nivel 1 (regla 8).

**Regla de decisión**
- Si la probabilidad máxima del Nivel 1 es **≥ 0.80** → se resuelve ahí.
- Si es **menor a 0.80** → se escala al Nivel 2 (zona gris).
- El 0.80 es un valor inicial; se ajusta una sola vez con el conjunto de validación para lograr un **recall ≥ 90 %** en las clases de fraude sin escalar demasiados mensajes al LLM.
- Usar un modelo que entregue probabilidades (regresión logística, o SVM con `CalibratedClassifierCV`).
- Cálculo de la puntuación y regla de `max()` según §8.6.

**Comparación de modelos LLM (parte de la Fase 5)**
- Probar `minimaxai/minimax-m3.1-flash` como Nivel 2 sobre el conjunto de validación. La comparación prevista con DeepSeek-V4.1-Flash **no pudo ejecutarse** (HTTP 410); si NVIDIA lo repone, repetirla con el mismo prompt. Como contraste opcional puede usarse `meta/muse-glimmer-30b`.
- Criterio objetivo de elección: **% de JSON válido**, **acuerdo con las etiquetas humanas**, **latencia** y **costo por análisis** (tokens de entrada/salida reportados por la API).
- Probar `temperature=0` contra el muestreo recomendado por el modelo (`1.0`/`top_p=0.95`) y quedarse con el mejor.
- Se deja documentado el modelo elegido y la comparación completa.

**Evaluación (conjunto de prueba)**
- Precisión, exhaustividad y F1 **por clase y macro**, matriz de confusión, proporción de mensajes escalados, tiempo de respuesta, costo por análisis.
- Comparar **tres configuraciones**: solo Nivel 1, solo Nivel 2 e híbrido.
- **Entregable:** modelo con métricas documentadas (`docs/reportes/metricas_clasificador.md`).

### Fase 6 — Explicabilidad y recomendaciones (Actividad 6, complementa OE3)
- Traducir el dictamen a semáforo de 3 estados.
- Resaltar señales de alerta sobre el texto sanitizado (en Nivel 1, vía términos con mayor contribución en el modelo lineal).
- Explicación breve en lenguaje sencillo: señal más relevante, peligro y consecuencias de actuar.
- Catálogo de recomendaciones por tipología (no generado por el LLM). Acciones contempladas: no compartir códigos ni contraseñas, verificar por canales oficiales, no hacer pagos anticipados por ofertas laborales, conservar evidencia, denunciar.
- El mensaje final incluye siempre el **aviso de que la herramienta es orientativa** (regla 13).
- **Entregable:** módulo de explicabilidad integrado.

### Fase 7 — Interfaz web (Actividad 7, OE4)
- **Backend:** FastAPI con endpoints para texto e imágenes.
- **Flujo en 4 pasos:** (1) ingresar mensaje o cargar captura → (2) revisar texto extraído → (3) ejecutar análisis → (4) resultado con semáforo, tipo de fraude probable, señales resaltadas y acciones recomendadas.
- Bocetos de baja fidelidad antes de implementar.
- **Frontend:** HTML, CSS y JavaScript estáticos servidos por FastAPI, **sin framework y sin paso de build (sin npm)**. Mobile-first.
- **Accesibilidad (WCAG 2.1):** contraste suficiente, navegación por teclado, etiquetas en campos, riesgo comunicado con **texto e iconos, no solo color**. Lenguaje claro sin tecnicismos; veredicto y acción principal primero, detalle después.
- **Aviso de privacidad visible:** los mensajes se sanitizan y no se almacenan.
- **Contenedor:** `Dockerfile` + `docker-compose.yml`; ejecución principal con **Docker Desktop (WSL2)** en `http://localhost:8000`. Alternativa documentada con venv en `docs/instalacion.md`.
- **Límites:** tamaño máximo de imagen (Fase 4), máximo de texto (10 000 caracteres) y **límite de frecuencia de solicitudes** en memoria (por IP), sin Redis.
- **HTTPS:** fuera del alcance actual. Se documenta en `docs/instalacion.md` la ruta de publicación futura (Caddy + Let's Encrypt ante dominio propio) como siguiente etapa, sin implementarla.
- **Entregable:** interfaz funcional conectada al backend, ejecutable con `docker compose up`.

### Fase 8 — Pruebas e integración (Actividad 8)
- **Técnicas:** pruebas unitarias (sanitización, clasificación, explicabilidad), integración del flujo completo, estrés con solicitudes concurrentes (tiempos y tasa de errores), robustez con mensajes ofuscados, muy largos, vacíos, en otro idioma y imágenes de baja calidad.
- **Usuarios:** 10–15 voluntarios de distintas edades y familiaridad con tecnología; escenarios preparados (sin mensajes personales reales); consentimiento informado; sin recabar datos identificables. Medir usabilidad con **SUS**, comparar decisiones antes/después de ver la alerta, recoger observaciones sobre claridad.
- **Fiabilidad de la anotación:** aplicar el protocolo de revisor automático con LLM (§8.7) sobre el 20 % estratificado; adjudicar manualmente los desacuerdos; reportar kappa como *acuerdo humano–LLM*.
- **Sesgos y errores:** analizar por tipología, registro del mensaje, longitud y canal (texto/imagen); atención a falsos positivos en notificaciones legítimas de bancos y comercios, y falsos negativos en modalidades poco representadas.
- **Entregable:** reporte de validación con observaciones y ajustes.

### Fase 9 — Documentación final (Actividad 9)
- Documentación técnica: arquitectura, esquemas de datos, entrenamiento y métricas.
- Manual breve de uso; instrucciones de instalación y despliegue; registro de decisiones, limitaciones y lecciones aprendidas.
- Reporte técnico conforme a lineamientos institucionales, con la cita de la ley de datos personales **unificada** (ver §15).
- **Entregable:** documento final del proyecto VerifIA.

---

## 10. Cronograma (referencial: 29/09/2026 – 28/12/2026)

> Las fechas son solo una guía. Lo que importa es el orden y las dependencias entre tareas, no cumplir los días exactos.

Responsable de todas las tareas: Giovani Hernández. ◆ = hito.

| ID | Actividad / subactividad | Inicio | Fin | Días | Dep. | Entregable |
|---|---|---|---|---|---|---|
| **Fase I — Planeación y análisis** | | | | | | |
| **A1** | **Planeación y definición del alcance** | 29/09 | 05/10 | 7 | | |
| 1.1 | Definición de alcance, recursos y tecnologías | 29/09 | 02/10 | 4 | — | `docs/plan_trabajo.md` |
| 1.2 | Elaboración y validación del cronograma | 03/10 | 05/10 | 3 | 1.1 | Cronograma validado |
| 1.3 | Estructura del repositorio, entorno y `.env.example` | 05/10 | 05/10 | 1 | 1.1 | Repo inicial + contenedor |
| ◆ | **Plan de trabajo aprobado** | 05/10 | 05/10 | 0 | | |
| **Fase II — Desarrollo del pipeline de IA** | | | | | | |
| **A2** | **Recopilación y curación del corpus** | 06/10 | 19/10 | 14 | | |
| 2.1 | Recolección de mensajes de fuentes públicas y boletines | 06/10 | 10/10 | 5 | 1.2 | Dataset crudo recopilado |
| 2.2 | Generación de ejemplos sintéticos con LLM (modelo pequeño, por lotes) | 11/10 | 14/10 | 4 | 2.1 | Ejemplos sintéticos generados |
| 2.3 | Anotación, balanceo y depuración (500 ej.) | 15/10 | 19/10 | 5 | 2.2 | Corpus anotado y balanceado |
| ◆ | **Corpus de entrenamiento listo** | 19/10 | 19/10 | 0 | | |
| **A3** | **Módulo de sanitización de datos personales** | 20/10 | 26/10 | 7 | | |
| 3.1 | Diseño de reglas y expresiones regulares de PII | 20/10 | 22/10 | 3 | 2.3 | Reglas de sanitización definidas |
| 3.2 | Implementación con Presidio (reconocedores personalizados + NER es) | 23/10 | 24/10 | 2 | 3.1 | Módulo de sanitización codificado |
| 3.3 | Pruebas de cobertura sobre mensajes reales | 25/10 | 26/10 | 2 | 3.2 | Reporte de cobertura de sanitización |
| **A4** | **Módulo de reconocimiento óptico de caracteres** | 27/10 | 09/11 | 14 | | |
| 4.1 | Integración de motor OCR para capturas en español | 27/10 | 01/11 | 6 | 3.3 | Motor OCR integrado |
| 4.2 | Ajuste de parámetros y pruebas de precisión | 02/11 | 05/11 | 4 | 4.1 | Métricas de precisión de OCR |
| 4.3 | Conexión del pipeline imagen→texto con sanitización | 06/11 | 09/11 | 4 | 4.2 | Pipeline OCR–sanitización enlazado |
| ◆ | **Pipeline de ingesta de datos operativo** | 09/11 | 09/11 | 0 | | |
| **A5** | **Entrenamiento del clasificador de riesgo** | 10/11 | 23/11 | 14 | | |
| 5.1 | Entrenamiento del filtro clásico (TF-IDF + LR/SVM/NB) | 10/11 | 14/11 | 5 | 2.2 | Clasificador base entrenado |
| 5.2 | Configuración del LLM con salida estructurada (NVIDIA API) | 15/11 | 19/11 | 5 | 5.1 | Segundo nivel de clasificación configurado |
| 5.3 | Evaluación con métricas F1, precisión y recall + comparación de modelos | 20/11 | 23/11 | 4 | 5.2 | Reporte de métricas de desempeño |
| ◆ | **Modelo clasificador validado** | 23/11 | 23/11 | 0 | | |
| **A6** | **Generador de explicabilidad y recomendaciones** | 24/11 | 30/11 | 7 | | |
| 6.1 | Diseño del semáforo de riesgo (0–100) | 24/11 | 26/11 | 3 | 5.3 | Escala de riesgo definida |
| 6.2 | Implementación de banderas rojas y recomendaciones | 27/11 | 30/11 | 4 | 6.1 | Módulo de explicabilidad funcional |
| **A7** | **Interfaz web de usuario** | 01/12 | 14/12 | 14 | | |
| 7.1 | Diseño de la interfaz (wireframes y UI) | 01/12 | 04/12 | 4 | 6.2 | Prototipo de interfaz aprobado |
| 7.2 | Desarrollo del frontend (carga de texto/imagen) | 05/12 | 09/12 | 5 | 7.1 | Frontend funcional |
| 7.3 | Integración con el backend + contenedor Docker local | 10/12 | 14/12 | 5 | 7.2 | Sistema integrado extremo a extremo |
| ◆ | **Prototipo funcional integrado (ejecutable en `localhost`)** | 14/12 | 14/12 | 0 | | |
| **Fase III — Validación y cierre** | | | | | | | |
| **A8** | **Pruebas de integración y validación** | 15/12 | 21/12 | 7 | | |
| 8.1 | Pruebas de estrés e integración del sistema | 15/12 | 17/12 | 3 | 7.3 | Reporte de pruebas técnicas |
| 8.2 | Validación con usuarios reales, kappa con revisor automático y ajustes finales | 18/12 | 21/12 | 4 | 8.1 | Reporte de validación con usuarios |
| ◆ | **Sistema validado por usuarios** | 21/12 | 21/12 | 0 | | |
| **A9** | **Documentación final y reporte académico** | 22/12 | 28/12 | 7 | | |
| 9.1 | Integración de documentación técnica y arquitectura | 22/12 | 24/12 | 3 | 8.2 | Documentación técnica integrada |
| 9.2 | Redacción y revisión del reporte académico final | 26/12 | 28/12 | 3 | 9.1 | Documento final del proyecto VerifIA |
| ◆ | **Entrega final del proyecto VerifIA** | 28/12 | 28/12 | 0 | | |

---

## 11. Métricas de evaluación (resumen)

| Módulo | Métricas |
|---|---|
| Anotación | Kappa de Cohen entre anotación humana y **revisor automático (LLM)** sobre el 20 % estratificado (§8.7) |
| Sanitización | Cobertura y precisión por tipo de entidad (≥100 mensajes anotados) |
| OCR | CER y WER (≥50 capturas) |
| Clasificador | Precisión, exhaustividad, F1 por clase y macro; matriz de confusión; % de mensajes escalados; tiempo de respuesta; costo por análisis |
| LLM | % de JSON válido; latencia por llamada; tokens de entrada/salida por análisis |
| Sistema | Pruebas unitarias, integración, estrés (concurrencia) y robustez |
| Usabilidad | SUS; comparación de decisiones antes y después de la alerta (10–15 voluntarios) |

---

## 12. Decisiones de diseño y su base teórica (resumen)

- **Ingeniería social (smishing/phishing):** los ataques se apoyan en confianza y emociones; suelen suplantar entidades, crear urgencia o amenaza, pedir acciones inmediatas e incluir enlaces o contactos del atacante (Munoz & Islam, 2025; Desolda et al., 2024).
- **Modelos clásicos (TF-IDF + LR/SVM/NB):** rápidos, baratos e interpretables, pero dependen del vocabulario visto; generalizan mal ante datos de otro origen (Koide et al., 2024: 54.53 %–60.00 % de exactitud en sistemas de referencia con correos de otro origen).
- **LLM:** capta contexto y tácticas de ingeniería social, pero tiene costo, latencia y alucinaciones. Ejemplo reportado: GPT-4 12.53 s y ~20× el costo de GPT-3.5 (2.50 s).
- **Cascada:** nivel 1 barato para casos de alta confianza; nivel 2 caro para ambiguos (Koide et al., 2024). Mostrar zona gris con advertencia (Desolda et al., 2024).
- **Sanitización:** reduce riesgo pero no garantiza detección total (Microsoft Presidio, s. f.); por eso además no se conservan los datos. Los enlaces/correos/teléfonos ayudan a detectar smishing, por eso se sustituyen por marcadores y no se eliminan.
- **Presidio como base:** los formatos mexicanos (CLABE, CURP, RFC, tarjeta con Luhn) se implementan como reconocedores de patrón personalizados sobre Presidio, lo que permite conservar la lógica de validación (Luhn, dígito de control) en lugar de regex sueltos.
- **Marcadores tipificados vs. borrado:** un marcador conserva la señal de "aquí había un teléfono" sin revelar el dato; además, la presencia del marcador es en sí misma un rasgo útil para el clasificador.
- **OCR:** Tesseract (Smith, 2007), soporta español; las capturas de mensajería requieren preprocesamiento (fondos de color, globos, emojis, modo oscuro).
- **Explicabilidad:** las advertencias genéricas son poco eficaces; las específicas (característica sospechosa, peligro, consecuencias) mejoran comprensión y confianza (Desolda et al., 2024). El color no debe ser el único canal (WCAG 2.1).
- **Privacidad en la inferencia:** enviar la captura directamente al LLM multimodal ahorraría el OCR, pero expondría los datos personales que la sanitización elimina. Se elige el flujo local OCR → sanitización → LLM(texto), y se documenta como decisión de diseño.
- **Modelos de la API de NVIDIA:** los benchmarks publicados son de los propios proveedores y no están verificados de forma independiente; ninguno mide español ni fraude. La comparación empírica prevista entre DeepSeek-V4.1-Flash y MiniMax-M3.1-Flash **no pudo ejecutarse** porque DeepSeek devuelve HTTP 410 (17/11/2026); MiniMax es el Nivel 2 operativo y se evaluará en la Fase 5.
- **Marco normativo:** la Ley Federal de Protección de Datos Personales en Posesión de los Particulares fue **abrogada por una nueva ley publicada el 20/03/2025** (vigente desde el día siguiente); supervisión pasa a la Secretaría Anticorrupción y Buen Gobierno. Principios que guían el diseño: tratar datos solo para finalidades informadas y lo estrictamente necesario → sanitizar antes de procesar, no conservar, informar al usuario.

### Proyectos relacionados

| Proyecto | Resumen |
|---|---|
| SMS Spam Collection (Almeida et al., 2011) | 5,574 SMS en inglés (4,827 legítimos / 747 spam); solo referencia metodológica |
| Verma et al. (2023) | Phishing en mensajería instantánea móvil con PLN y ML |
| ChatSpamDetector (Koide et al., 2024) | LLM + prompt detallado, dictamen estructurado; GPT-4 con 99.70 % de exactitud sobre 1,010 phishing + 1,000 legítimos |
| APOLLO (Desolda et al., 2024) | GPT-4o; clasifica y explica; 97.4 % de exactitud (99 % con reputación de URL); sustituye URL/teléfonos/correos por metaetiquetas; dos prompts encadenados (clasificar → explicar) |

---

## 13. Estructura de repositorio

```
Proyecto-IA/
├── VerifIA_memoria_proyecto.md  # este archivo (fuente del proyecto)
├── README.md
├── pyproject.toml / requirements.txt
├── Dockerfile                   # imagen única: FastAPI + Tesseract(spa) + modelos spaCy
├── docker-compose.yml           # opción principal de ejecución (Docker Desktop / WSL2)
├── .env.example                 # credenciales del LLM y parámetros, nunca en el código
├── .gitignore
├── data/
│   ├── raw/                     # mensajes de fuentes públicas
│   ├── synthetic/               # generados con LLM (solo train)
│   ├── annotated/               # corpus anotado (tipologia, origen, ...)
│   ├── splits/                  # train / val / test estratificados
│   └── ocr_test/                # >=50 capturas + transcripciones
├── docs/
│   ├── plan_trabajo.md          # Fase 1: alcance, recursos, tecnologías, criterios, roles
│   ├── instalacion.md           # Docker Desktop (principal) y venv (alternativa); ruta HTTPS futura
│   ├── guia_anotacion.md        # definición de las 5 clases + ejemplos
│   └── reportes/                # métricas, cobertura de sanitización, CER/WER, kappa, sesgos
├── notebooks/                   # exploración y entrenamiento
├── scripts/                     # generación de corpus, depuración, partición, evaluación
├── src/verifia/
│   ├── sanitizer/               # Presidio + recognizers (Luhn, CLABE, CURP, RFC) + NER es
│   ├── ocr/                     # preprocesamiento OpenCV + Tesseract
│   ├── classifier/
│   │   ├── level1.py            # TF-IDF + modelo clásico
│   │   ├── level2_llm.py        # NVIDIA API + Pydantic
│   │   └── cascade.py           # umbrales, puntuación y fallback
│   ├── explain/                 # semáforo, señales, catálogo de recomendaciones
│   ├── api/                     # FastAPI
│   └── schemas.py               # esquemas Pydantic (salida del LLM, respuestas de la API)
├── web/                         # HTML, CSS, JS (estático, sin build)
└── tests/                       # pytest
```

---

## 14. Orden de trabajo con opencode

1. **Fase 1** — Inicializar repo, entorno, estructura de carpetas, `.env.example`, `docker-compose.yml` y `docs/plan_trabajo.md`.
2. **Fase 2** — Scripts de recolección, generación sintética por lotes, limpieza, deduplicado por similitud, partición estratificada y verificación de PII.
3. **Fase 3** — `sanitizer` con Presidio, reconocedores personalizados y pruebas unitarias antes de cualquier otro módulo.
4. **Fase 4** — `ocr` con evaluación CER/WER.
5. **Fase 5** — Nivel 1 → Nivel 2 → cascada → comparación de modelos LLM → evaluación de las 3 configuraciones.
6. **Fase 6** — Semáforo + catálogo de recomendaciones.
7. **Fase 7** — API FastAPI + frontend estático + contenedor Docker local.
8. **Fases 8–9** — Pruebas, validación con usuarios, kappa con revisor automático y documentación.

En cada fase, usa la skill principal y las de apoyo que lista la **§17**.

---

## 15. Decisiones tomadas y puntos pendientes

### Decisiones tomadas

1. **Clasificador clásico:** solo regresión logística, SVM lineal y Naive Bayes, como en la metodología. No se usa XGBoost.
2. **LLM:** API de NVIDIA con modelos gratuitos; clave en `.env` (`NVIDIA_API_KEY`). **No se despliega ningún modelo local.**
3. **Metas simples de referencia** (valores iniciales, sin agregar trabajo):
   - OCR: CER ≤ 15 %.
   - Cascada: umbral de confianza 0.80.
   - Recall ≥ 90 % en las clases de fraude.
   - Semáforo: 0–33 verde, 34–66 amarillo, 67–100 rojo.
4. **Cronograma:** referencial, no es un plazo fijo.
5. **Prompt del Anexo:** descartado; no forma parte del proyecto.
6. **Despliegue:** prototipo **local** en contenedor Docker (Docker Desktop/WSL2), en `http://localhost:8000`. HTTPS, dominio y nube quedan fuera de alcance actual, documentados como etapa futura.

### 15.1 Decisiones de implementación acordadas (octubre 2026)

| # | Decisión | Valor |
|---|---|---|
| 1 | Catálogo de marcadores | 9 marcadores: `[TELEFONO] [CORREO] [NOMBRE] [CUENTA] [TARJETA] [CODIGO] [CURP] [RFC] [ENLACE:dominio.tld]` |
| 2 | Enmascarado de `[CODIGO]` | 4–8 dígitos **con contexto de solicitud** (≤30 caracteres); no enmascara montos, %, fechas ni folios |
| 3 | Puntuación 0–100 | `100 × (1 − P(legitimo))`; en zona gris `max(LLM, Nivel 1)`; fallback = Nivel 1 + "análisis parcial" |
| 4 | Nivel de riesgo | **Derivado** de la puntuación; en el corpus es opcional y solo referencia |
| 5 | Límites del sistema | Imagen ≤ 5 MB, ≤ 4000 px, ≤ 12 MP (PNG/JPEG); texto ≤ 10 000 caracteres; LLM timeout 60 s, hasta 3 intentos, `max_tokens` 1300, `reasoning_effort` bajo; corpus sintético con `max_tokens` 2600 por lote |
| 6 | Fiabilidad de la anotación | **Revisor automático con LLM** sobre el 20 % estratificado; se reporta como *acuerdo humano–LLM* (no inter-humano); desacuerdos adjudicados a mano |
| 7 | Plan de trabajo | La Fase 1 entra como **primer paso del §14**, con entregable `docs/plan_trabajo.md` |
| 8 | Entorno de ejecución | **Docker Desktop (WSL2)** como opción principal; venv documentado como alternativa |
| 9 | Proveedor de LLM | **Solo API de NVIDIA** |
| 10 | HTTPS | Fuera de alcance actual; documentado para un futuro despliegue público |
| 11 | Tamaño del corpus | **500 mensajes** (100 por clase); mínimo aceptable 400 |
| 12 | Orígenes de los datos | `publico`, `sintetico_llm`, `manual`, `plantilla_legitima`. La regla 9 aplica **solo a `sintetico_llm`** (exclusivo de train) |
| 13 | Presidio | **Requisito de la Fase 3** (base obligatoria), con reconocedores personalizados para formatos mexicanos y NER `es_core_news_md` |
| 14 | Modelo de Nivel 2 | `minimaxai/minimax-m3.1-flash` (default operativo); `deepseek-ai/deepseek-v4.1-flash` no disponible por HTTP 410 (17/11/2026) |
| 15 | Modelo del revisor (kappa) | `meta/muse-glimmer-30b`, distinto del Nivel 2 (evita circularidad); Mistral-Large-4 descartado por latencia |
| 16 | Modelo de generación de corpus | `nvidia/nemotron-3.5-bolt-e4b` (pequeño, barato, español en su post-training, *Structured Output*) |
| 17 | Entrada al LLM | **Solo texto sanitizado**; la imagen nunca se envía al modelo |
| 18 | Caché de respuestas | No se implementa (regla 2) |

### Pendiente

- Unificar la cita de la ley de datos personales en el reporte final (el Capítulo I cita la de 2010 y el apartado 2.10 aclara que fue abrogada por la de 2025).
- Confirmar en la Fase 5 el muestreo del Nivel 2 (`temperature=0` vs. `1.0`). El modelo ya está definido: MiniMax-M3.1-Flash, porque DeepSeek-V4.1-Flash devuelve 410. El revisor del §8.7 también está definido: Mistral-Large-4-1T-A52B.
- Capturar los precios por millón de tokens vigentes en la consola de NVIDIA al momento del reporte, para la métrica de costo por análisis.

---

## 16. Referencias

- Almeida, T. A., Gómez Hidalgo, J. M., & Yamakami, A. (2011). Contributions to the study of SMS spam filtering: New collection and results. *Proceedings of the 11th ACM Symposium on Document Engineering (DocEng '11)*, 259–262. https://doi.org/10.1145/2034691.2034742
- Chapman, P., et al. (2000). *CRISP-DM 1.0: Step-by-step data mining guide*. SPSS Inc.
- Comisión Nacional para la Protección y Defensa de los Usuarios de Servicios Financieros. (2024). *Reporte de fraudes cibernéticos en el sistema financiero mexicano*. Condusef.
- Desolda, G., Greco, F., & Viganò, L. (2024). APOLLO: A GPT-based tool to detect phishing emails and generate explanations that warn users. arXiv. https://arxiv.org/abs/2410.07997
- Jurafsky, D., & Martin, J. H. (2023). *Speech and language processing* (3rd ed.). Stanford University.
- Koide, T., Fukushi, N., Nakano, H., & Chiba, D. (2024). ChatSpamDetector: Leveraging large language models for effective phishing email detection. *SecureComm 2024*. https://arxiv.org/abs/2402.18093
- Ley Federal de Protección de Datos Personales en Posesión de los Particulares. (2010). *Diario Oficial de la Federación*, México.
- Ley Federal de Protección de Datos Personales en Posesión de los Particulares. (2025). *Diario Oficial de la Federación*, 20 de marzo de 2025. México.
- Microsoft. (s. f.). *Presidio: Data protection and de-identification SDK*. https://microsoft.github.io/presidio/
- Mishra, S., & Soni, D. (2023). DSmishSMS: A system to detect smishing SMS. *Neural Computing and Applications, 35*, 4975–4992. https://doi.org/10.1007/s00521-021-06305-y
- Munoz, M. L., & Islam, M. F. (2025). Deep learning approaches for multi-class classification of phishing text messages. *Journal of Cybersecurity and Privacy, 5*(4), 102. https://doi.org/10.3390/jcp5040102
- NVIDIA. (2026). *DeepSeek-V4.1-Flash — model card*. https://build.nvidia.com/deepseek-ai/deepseek-v4.1-flash
- NVIDIA. (2026). *MiniMax-M3.1-Flash — model card*. https://build.nvidia.com/minimaxai/minimax-m3.1-flash
- NVIDIA. (2026). *Nemotron-3.5-Bolt-E4B — model card*. https://build.nvidia.com/nvidia/nemotron-3.5-bolt-e4b
- Pedregosa, F., et al. (2011). Scikit-learn: Machine learning in Python. *JMLR, 12*, 2825–2830.
- Smith, R. (2007). An overview of the Tesseract OCR engine. *ICDAR 2007*, 629–633. IEEE.

---

## 17. Skills por fase (asignación de trabajo)

Las skills instaladas en `.agents/skills/` concentran los detalles operativos de cada
módulo (comandos, plantillas, criterios de aceptación y errores frecuentes). Esta tabla
define **qué skill cargar al iniciar cada fase** de la §9. La memoria sigue mandando si
hay conflicto; si una skill contradice una decisión de la §15, se corrige la skill.

| Fase | Skill principal | Skills de apoyo | Cuándo usarlas |
|---|---|---|---|
| **1** — Planeación y alcance | *(ninguna)* | `markdown-mermaid-writing` | Plan de trabajo, diagrama de arquitectura y cronograma en Markdown/Mermaid. |
| **2** — Corpus | `verifia-corpus` | `huggingface-datasets` (si se consultan colecciones públicas), `exploratory-data-analysis` (perfil del corpus, desequilibrio, fuga train/test), `citation-management` (procedencia de las fuentes) | Recolección, generación sintética por lotes, deduplicado y partición 70/15/15. |
| **3** — Sanitización | `verifia-sanitizacion` | — | Presidio, reconocedores mexicanos (Luhn, CLABE, CURP, RFC), regla de `[CODIGO]` y pruebas de cobertura. |
| **4** — OCR | `verifia-ocr` | `webapp-testing` (generar las ≥50 capturas sintéticas con Playwright), `scientific-visualization` (gráfica de CER/WER) | Preprocesamiento, Tesseract `spa`, medición de CER/WER. |
| **5** — Clasificador | `scikit-learn` | `verifia-nivel2-llm` (Nivel 2, esquema Pydantic y cascada), `statistical-analysis` (comparación de modelos), `scientific-visualization` (matriz de confusión y curvas), `shap` (solo si se explora la contribución de rasgos) | Nivel 1, Nivel 2, umbral, comparación de LLM y evaluación de las tres configuraciones. |
| **6** — Explicabilidad | `verifia-explicabilidad` | `shap` (opcional: mapear pesos del modelo lineal a señales) | Semáforo, resaltado de señales y catálogo de recomendaciones. |
| **7** — Interfaz web | `verifia-api-docker` | `frontend-design` (dirección visual), `web-design-guidelines` (auditoría WCAG), `webapp-testing` (E2E con Playwright) | API, pantalla de 4 pasos, Docker y pruebas de interfaz. |
| **8** — Validación | `verifia-validacion` | `statistical-analysis` (SUS, kappa, intervalos), `webapp-testing`, `scientific-visualization` | Pruebas unitarias, integración, estrés, robustez, usuarios y kappa. |
| **9** — Documentación | `markdown-mermaid-writing` | `citation-management` (referencias y cita unificada de la ley 2025), `scientific-visualization` (figuras finales) | Documento técnico, manual de uso y reporte académico. |

**Nota de orden.** El protocolo de kappa de la §8.7 pertenece a la Fase 8, pero el
**Experimento B** (revisor = mismo modelo que el Nivel 2) conviene ejecutarlo dentro de
la Fase 5, porque es evidencia directa para justificar el Nivel 2 de la cascada.

**Pruebas de interfaz.** No requieren un MCP de navegador: la skill `webapp-testing`
usa Python + Playwright en modo headless, lo que hace las pruebas repetibles y deja
capturas como evidencia para el reporte. Requiere `pip install playwright` y
`python -m playwright install chromium` una sola vez.

**Detalle operativo.** La versión de trabajo, con el artefacto y el criterio de salida de
cada fase, está en `docs/skills_por_fase.md`. Esta sección y ese documento se mantienen
sincronizados.

**Gráficas.** En las fases 4, 5, 8 y 9, `scientific-visualization` define el estándar de
figura (legibilidad, color accesible, exportación) y `matplotlib` es la herramienta que
lo implementa.
