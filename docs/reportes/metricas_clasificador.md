# Métricas del clasificador de riesgo (Fase 5)

> Generado a partir de `models/nivel1_meta.json`, `data/reportes_fase5/eleccion_llm.json`,
> `data/reportes_fase5/ajuste_umbral.json`, `data/reportes_fase5/evaluacion_test.json` y
> `data/reportes_fase5/kappa_experimento_b.json` / `kappa_b_desacuerdos.csv`.
> Fecha de cierre: 18/11/2026.

## 1. Resumen

La Fase 5 compara tres formas de resolver el mismo problema sobre el conjunto de
prueba reservado:

1. **Solo Nivel 1** — TF-IDF (palabras y caracteres) + Naive Bayes calibrado.
2. **Solo Nivel 2** — MiniMax-M3.1-Flash con salida JSON validada por Pydantic.
3. **Híbrido** — cascada: el Nivel 1 resuelve la alta confianza y el LLM solo la
   zona gris (`P(máxima) < 0.75`).

El Nivel 1 se eligió por F1 macro en validación (Naive Bayes, 0.8668) y se calibró
para entregar probabilidades. El umbral se ajustó **una sola vez** con validación:
0.75 conserva un recall seguro de fraude de 98.3 % y escala 24 % de los mensajes,
frente al 26.7 % que escalaría el valor inicial 0.80 sin mejorar el recall.

En la comparación de muestreo del Nivel 2 se impuso `temperature=0` (98.7 % de JSON
válido, 91.9 % de acuerdo humano, p50 109 s) sobre `temperature=1.0/top_p=0.95`
(94.7 % de JSON válido, 95.8 % de acuerdo, p50 176 s). El criterio de la memoria
prioriza la tasa de JSON válido; la latencia y los cuatro fallos de la celda
estocástica refuerzan la decisión.

En el conjunto de prueba, el **híbrido** alcanza exactitud 0.9333 y F1 macro
**0.9352** escalando solo 14.7 % de los mensajes. Iguala al Nivel 2 solo
(0.9346) con 11 llamadas en lugar de 75 y es la única configuración que no deja
ningún fraude etiquetado como `legitimo` (60/60, recall binario 100 %). Frente al
Nivel 1 gana 2.78 puntos de F1 macro. El detalle está en §6.

El **Experimento B** (revisor = MiniMax-M3.1-Flash, el mismo del Nivel 2) obtuvo
un kappa humano–LLM de **0.875** (IC95 0.798–0.949) y 90 % de coincidencia sobre
100 mensajes. En los mensajes manuales y de plantilla el acuerdo sube a 0.972;
en los sintéticos baja a 0.779. El revisor es fiable, pero su punto débil es la
oferta laboral (recall 0.75) y la frontera extorsión/paquetería. El detalle y la
adjudicación de los 10 desacuerdos están en §7.

## 2. Datos y protocolo

| Elemento | Valor |
|---|---|
| Corpus | 500 mensajes, 100 por clase (`data/annotated/corpus.jsonl`) |
| Partición | 350 train / 75 validación / 75 prueba, estratificada por tipología |
| Orígenes | `manual` 175, `plantilla_legitima` 85, `sintetico_llm` 240 |
| Sintéticos | Solo en `train` (regla 9) |
| Entrada de ambos niveles | Texto **ya sanitizado** por la Fase 3 (regla 1) |
| Conjunto de prueba | Reservado hasta esta evaluación (regla 10) |
| Semilla | 42 |
| Pruebas automatizadas | 145 pruebas en verde; `ruff` sin errores |

La validación se usó para elegir el modelo del Nivel 1, calibrarlo y ajustar el
umbral. El conjunto de prueba no participó en ninguna de esas decisiones.

## 3. Nivel 1 — filtro rápido

### 3.1 Características y entrenamiento

- TF-IDF de **palabras** (unigramas y bigramas, `min_df=2`, `sublinear_tf`).
- TF-IDF de **caracteres** (n-gramas de 3 a 5, tolera escritura ofuscada).
- **Rasgos estructurales**: longitud, proporción de mayúsculas y dígitos,
  exclamaciones/interrogaciones, conteo de cada marcador de sanitización y
  señales del enlace (acortador, IP literal, TLD sospechoso, subdominios,
  guiones). Los enlaces no se concatenan al texto: solo aportan rasgos (regla 4).
- Búsqueda en cuadrícula con **validación cruzada estratificada de 5 pliegues**
  sobre `train`, optimizando F1 macro.
- El ganador se calibra con `CalibratedClassifierCV(method="sigmoid", cv=5)`,
  requisito del §8.6 para calcular `100 × (1 − P(legítimo))`.

### 3.2 Comparación de candidatos

| Modelo | Mejores parámetros | F1 macro CV (train) | F1 macro validación |
|---|---|---:|---:|
| Regresión logística | `C=10` | 0.9309 | 0.7698 |
| SVM lineal | `C=3` | 0.9432 | 0.8116 |
| **Naive Bayes** | **`alpha=0.1`** | **0.8945** | **0.8668** |

Naive Bayes gana en validación aunque pierda en la cruzada de entrenamiento: es
el modelo que **generaliza mejor al cambio de origen** (los sintéticos de `train`
no aparecen en validación). Esa brecha CV→validación es la primera señal de que
el corpus sintético es más fácil que los mensajes manuales y las plantillas.

### 3.3 Métricas del modelo calibrado en validación

| Clase | Precisión | Recall | F1 | Soporte |
|---|---:|---:|---:|---:|
| `legitimo` | 0.7059 | 0.8000 | 0.7500 | 15 |
| `suplantacion_bancaria` | 1.0000 | 0.7333 | 0.8462 | 15 |
| `paqueteria_retenida` | 0.8667 | 0.8667 | 0.8667 | 15 |
| `oferta_laboral_fraudulenta` | 0.8750 | 0.9333 | 0.9032 | 15 |
| `extorsion` | 0.9375 | 1.0000 | 0.9677 | 15 |
| **Macro** | **0.8770** | **0.8667** | **0.8668** | **75** |

Exactitud: **0.8667**. La precisión de `legitimo` (0.71) refleja cinco
mensajes de fraude que el Nivel 1 dejó pasar como legítimos: 3 de suplantación
bancaria y 2 de paquetería. Esos falsos negativos son justamente los que la zona
gris debe recuperar; la suplantación bancaria, con recall 0.73, es la clase que
más se beneficia del Nivel 2.

## 4. Umbral de la cascada

El valor inicial de la memoria es 0.80. Se ajustó una sola vez con validación,
con este criterio: recall seguro de fraude ≥ 90 % y, entre los umbrales que lo
cumplen, el menor escalado posible (regla 11: la exhaustividad pesa más, sin
disparar llamadas al LLM).

| Umbral | Escalado al LLM | Fraude mal resuelto en N1 | Recall seguro de fraude | Precisión en resueltos |
|---:|---:|---:|---:|---:|
| 0.50 | 5.3 % | 5/60 | 91.7 % | 90.1 % |
| 0.60 | 8.0 % | 4/60 | 93.3 % | 91.3 % |
| 0.65 | 12.0 % | 2/60 | 96.7 % | 93.9 % |
| 0.70 | 18.7 % | 2/60 | 96.7 % | 93.4 % |
| **0.75** | **24.0 %** | **1/60** | **98.3 %** | **94.7 %** |
| 0.80 (inicial) | 26.7 % | 1/60 | 98.3 % | 94.5 % |
| 0.85 | 60.0 % | 1/60 | 98.3 % | 93.3 % |
| 0.90 | 100 % | 0/60 | 100 % | — |

**Decisión: 0.75.** Iguala el recall seguro de 0.80 con 2.7 puntos menos de
escalado. Bajarlo más reduce llamadas pero deja errores de fraude que la cascada
ya no puede corregir. El barrido completo está en
`docs/reportes/figuras/barrido_umbral.png` y en `data/reportes_fase5/ajuste_umbral.json`.

## 5. Nivel 2 — LLM con salida estructurada

### 5.1 Configuración

| Elemento | Valor |
|---|---|
| Modelo operativo | `minimaxai/minimax-m3.1-flash` |
| Alternativa prevista | `deepseek-ai/deepseek-v4.1-flash` — **HTTP 410**, no disponible |
| Prompt | Rol, 5 definiciones, tácticas, catálogo de marcadores y 2 ejemplos por clase (10, solo de `train`) |
| Entrada | Texto sanitizado entre `<mensaje>` y `</mensaje>` |
| Salida | JSON con tipología, riesgo, puntuación, señales y justificación |
| Validación | Pydantic + coherencia riesgo↔puntuación + cada señal debe existir literalmente en el texto |
| Reintentos | Hasta 3 intentos ante 400/408/409/429/5xx, timeout y conexión |
| Caché | Ninguna (regla 2) |

El prompt real mide ~1 714 tokens de entrada y ~150 de salida. La llamada incluye
`reasoning_effort=low`; aun así la API gratuita mostró una latencia muy variable
(ver §5.2 y la limitación de §8). Las latencias de la tabla se midieron con
**4 hilos concurrentes** y varios `429`: incluyen la espera por límite de tasa y
sobreestiman la latencia de una solicitud individual.

### 5.2 Comparación de muestreo (validación, 75 mensajes)

| Celda | JSON válido | Acuerdo humano | Latencia p50 | Latencia p95 | Tokens entrada/salida | Fallos |
|---|---:|---:|---:|---:|---:|---|
| **`temp0_determinista`** (`T=0`, `top_p=1.0`) | **98.7 %** (74/75) | 91.9 % | **109.2 s** | **132.3 s** | 1714 / 150 | 1 `senal_no_verificada` |
| `temp1_recomendado` (`T=1.0`, `top_p=0.95`) | 94.7 % (71/75) | **95.8 %** | 176.1 s | 206.7 s | 1714 / 149 | 1 `api_429`, 2 `esquema_invalido`, 1 `salida_truncada` |

**Celda elegida: `temp0_determinista`.** El criterio de la memoria es mayor tasa
de JSON válido y, en empate, mayor acuerdo. `temp1` logra más acuerdo, pero
pierde 4 puntos de validez, duplica la latencia y falla en 4 de 75 mensajes. Para
un sistema que debe degradar con elegancia, la validez del contrato JSON manda.

La comparación **DeepSeek vs. MiniMax no pudo ejecutarse** porque DeepSeek
devuelve HTTP 410 desde el 16/11/2026. Por tanto, esta tabla compara **dos
configuraciones de muestreo del único modelo operativo**, no dos modelos. Es una
limitación que se declara en §8 y en `docs/reportes/verificacion_api.md`.

### 5.3 Cascada en validación

Con el umbral 0.75 y la celda `temp0`:

- Mensajes escalados: **18/75 (24.0 %)**.
- Mensajes resueltos por el Nivel 1: 57/75 (76.0 %).
- Fallback en zona gris: **1/18** (`leg-022`, dictamen rechazado por
  `senal_no_verificada`); el resto de la zona gris obtuvo JSON válido.
- Discrepancias de puntuación (`puntuacion_LLM < puntuacion_N1`): 12 de los 17
  dictámenes válidos de la zona gris; la regla `max()` conserva el riesgo mayor y
  solo marca la diferencia.
- Exactitud: **0.9200** · F1 macro: **0.9191** (frente a 0.8668 del Nivel 1 solo).

| Clase | Precisión | Recall | F1 |
|---|---:|---:|---:|
| `legitimo` | 0.8571 | 0.8000 | 0.8276 |
| `suplantacion_bancaria` | 0.9375 | 1.0000 | 0.9677 |
| `paqueteria_retenida` | 0.8667 | 0.8667 | 0.8667 |
| `oferta_laboral_fraudulenta` | 1.0000 | 0.9333 | 0.9655 |
| `extorsion` | 0.9375 | 1.0000 | 0.9677 |

La cascada recupera por completo el recall de suplantación bancaria (0.73 → 1.00)
sin perder precisión global: es la evidencia directa de que la zona gris aporta.

## 6. Evaluación en el conjunto de prueba

El test se usó **una sola vez**, después de fijar modelo, calibración, umbral,
prompt y muestreo con validación. Tiene 75 mensajes (15 por clase), así que cada
error mueve 6.7 puntos el recall de su clase.

### 6.1 Comparación global

| Configuración | Exactitud | F1 macro | Precisión macro | Recall macro | Escalado | Latencia p50 | Latencia p95 | Tokens entrada/salida |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Solo Nivel 1 | 0.9067 | 0.9074 | 0.9163 | 0.9067 | 0 % | 12.1 ms | — | 0 / 0 |
| Solo Nivel 2 | 0.9333 | 0.9346 | 0.9446 | 0.9333 | 100 % | 72.1 s | 81.0 s | 125 171 / 10 323 |
| **Híbrido (0.75)** | **0.9333** | **0.9352** | **0.9413** | **0.9333** | **14.7 %** (11/75) | **0.01 s** | **75.1 s** | **18 845 / 1 397** |

El híbrido **iguala al Nivel 2 solo** (F1 0.9352 frente a 0.9346; la diferencia
cabe en un mensaje) con **11 llamadas en lugar de 75**: 85.3 % menos llamadas y
85.1 % menos tokens. Frente al Nivel 1, gana **2.78 puntos de F1 macro**
(0.9074 → 0.9352) sin cambiar el resto de la matriz: la única diferencia con el
Nivel 1 son dos mensajes de oferta laboral que el filtro mandaba a `legitimo` y
que la zona gris recuperó.

La latencia del Nivel 2 se midió con **4 hilos concurrentes** e incluye esperas
por `429`; la del híbrido es una **estimación secuencial** (12 ms del Nivel 1 más
la latencia registrada de cada llamada escalada), no una medición de concurrencia.
Por eso su media es 12.1 s y su p50 es 0.01 s: 64 de 75 mensajes no tocan la red.

### 6.2 Comportamiento binario fraude ↔ legítimo

Para el semáforo de la Fase 6, lo decisivo es no dejar pasar fraude como
legítimo; confundir dos tipologías de fraude conserva la alerta. Visto en
binario:

| Configuración | Recall fraude | Precisión fraude | Fraude → legítimo | Legítimo → fraude |
|---|---:|---:|---:|---:|
| Solo Nivel 1 | 96.7 % (58/60) | 98.3 % (58/59) | 2 | 1 |
| Solo Nivel 2 | 93.3 % (56/60) | 100 % (56/56) | 4 | 0 |
| **Híbrido** | **100 % (60/60)** | **98.4 % (60/61)** | **0** | **1** |

El híbrido es la **única configuración sin falsos negativos binarios**: ningún
mensaje de fraude del test quedó etiquetado como `legitimo`. Sus cuatro errores
de fraude son confusiones entre tipologías (2 paquetería → suplantación,
1 suplantación → paquetería, 1 oferta laboral → suplantación) y provienen del
Nivel 1: no estaban en la zona gris, así que el LLM no podía corregirlos. El
precio es un falso positivo (un legítimo marcado como suplantación bancaria).

### 6.3 Métricas por clase del híbrido

| Clase | Precisión | Recall | F1 | Soporte |
|---|---:|---:|---:|---:|
| `legitimo` | 1.0000 | 0.9333 | 0.9655 | 15 |
| `suplantacion_bancaria` | 0.7778 | 0.9333 | 0.8485 | 15 |
| `paqueteria_retenida` | 0.9286 | 0.8667 | 0.8966 | 15 |
| `oferta_laboral_fraudulenta` | 1.0000 | 0.9333 | 0.9655 | 15 |
| `extorsion` | 1.0000 | 1.0000 | 1.0000 | 15 |
| **Macro** | **0.9413** | **0.9333** | **0.9352** | **75** |

F1 por clase en las tres configuraciones, para ver dónde gana cada una:

| Clase | Solo Nivel 1 | Solo Nivel 2 | Híbrido |
|---|---:|---:|---:|
| `legitimo` | 0.9032 | 0.8824 | **0.9655** |
| `suplantacion_bancaria` | 0.8485 | **0.9333** | 0.8485 |
| `paqueteria_retenida` | 0.8966 | **0.9286** | 0.8966 |
| `oferta_laboral_fraudulenta` | 0.8889 | 0.9286 | **0.9655** |
| `extorsion` | **1.0000** | **1.0000** | **1.0000** |

El Nivel 2 solo es mejor en suplantación y paquetería; el híbrido, en legítimo y
oferta laboral. Frente al Nivel 1, la ganancia del híbrido viene de dos ofertas
recuperadas; frente al Nivel 2, empata en F1 con 85 % menos llamadas.

`extorsion` queda perfecta; oferta laboral sube de 0.80 a 0.9333 de recall
gracias a la cascada. La precisión de `suplantacion_bancaria` (0.78) la bajan un
legítimo, dos paqueterías y una oferta laboral que el Nivel 1 clasificó como
suplantación con alta confianza: la zona gris no las vio y el Nivel 2 no pudo
intervenir. Es el mismo patrón de error que ya mostraba la validación y la
principal deuda del filtro.

### 6.4 Recall de fraude con incertidumbre

- **Recall exacto de tipología en fraude:** 56/60 = 93.33 %, IC95 Wilson
  [84.1 %, 97.4 %].
- **Recall binario fraude vs. legítimo:** 60/60 = 100 %, IC95 Wilson
  [94.0 %, 100 %].

Con 60 mensajes de fraude, el intervalo es ancho: un solo error mueve 1.7 puntos
el recall binario y la cota inferior del 94 % recuerda que el resultado no está
garantizado en una muestra nueva.

### 6.5 Fallos, latencia y lectura operativa

- **Dos fallos de API** en la corrida de solo Nivel 2 (`leg-010` y
  `man-paq-026`, ambos `api_429`). La métrica estricta los cuenta como
  `legitimo`; descontándolos, el Nivel 2 válido sube a exactitud 0.9452 y F1
  0.9456 (n=73). Es una **cota superior no alcanzable en operación**: un fallo de
  API no desaparece, se degrada. El híbrido no tuvo fallos en su zona gris
  (0/11) y por eso no necesitó ese ajuste.
- **Ocho discrepancias de puntuación** en la zona gris (`puntuacion_LLM <
  puntuacion_N1`). La regla `max()` conservó el riesgo mayor y solo registró la
  diferencia; no cambió ninguna etiqueta.
- **La zona gris aportó exactamente lo previsto.** De los 11 mensajes
  escalados, el Nivel 1 acertaba 9 y fallaba 2 (oferta laboral); el LLM acertó
  los 11 y corrigió esos dos. Los otros 64 mensajes se resolvieron sin red.
- **La cola de latencia manda.** El p95 del híbrido (75.1 s) superaba el
  `LLM_TIMEOUT_S=60` inicial: en producción esos mensajes habrían caído a
  fallback. Ya se elevó a **180 s** (§9), por encima del p95 de test (75.1 s) y
  del p95 de validación (132.3 s).
- **Costo.** La API se usó en modalidad de prueba: \$0. Los 20 242 tokens del
  híbrido (270 por mensaje analizado; 1 840 por mensaje escalado) son la base
  para extrapolar si se migra a tarifa por token.

La figura `docs/reportes/figuras/matrices_confusion_fase5.png` muestra las tres
matrices con conteos anotados; los datos crudos están en
`data/reportes_fase5/evaluacion_test.json`.

## 7. Experimento B — acuerdo humano ↔ LLM (calidad del Nivel 2)

El protocolo completo del §8.7 pertenece a la Fase 8. El **Experimento B** se
adelanta aquí porque es evidencia directa para justificar el Nivel 2: si el LLM
clasifica con una fiabilidad comparable al anotador humano, la zona gris tiene
sentido; si no, la cascada solo añadiría costo.

### 7.1 Protocolo aplicado

| Elemento | Decisión |
|---|---|
| Revisor | `minimaxai/minimax-m3.1-flash` (el mismo modelo del Nivel 2) |
| Muestra | 100 mensajes, 20 por clase; **100 válidos** tras reintentar 11 fallos de tasa |
| Origen de la muestra | `train` + validación; el test queda reservado |
| Exclusión | Los 10 mensajes usados como few-shot en el prompt |
| Insumo | Texto sanitizado + definiciones de la guía + lista cerrada de 5 clases |
| Muestreo | `temperature=0`, `top_p=1.0`, `max_tokens=1200` |
| Salida | JSON con un solo campo `tipologia`, extraído con el parser balanceado |
| Métrica | Kappa de Cohen, coincidencia, matriz humano↔LLM e IC95 por bootstrap |

Se excluyeron los few-shot porque el modelo ya vio su etiqueta en el prompt:
incluirlos habría inflado artificialmente el acuerdo.

### 7.2 Resultado global

| Métrica | Valor |
|---|---:|
| Kappa de Cohen (humano–LLM) | **0.875** |
| IC95 por bootstrap (1000 remuestreos) | **0.798 – 0.949** |
| Coincidencia | **90.0 %** (90/100) |
| Desacuerdos | 10 |

Según Landis & Koch, 0.875 cae en la banda **casi perfecta** (0.81–1.00); incluso
la cota inferior del intervalo (0.798) sigue siendo **sustancial**. El kappa no
mide acuerdo entre anotadores humanos: mide **acuerdo humano–LLM** y se reporta
así, tal como exige el §8.7.

### 7.3 Matriz humano ↔ LLM

Filas: etiqueta humana. Columnas: etiqueta del revisor.

| Humano \ LLM | legítimo | suplant. | paquetería | oferta | extorsión | Total |
|---|---:|---:|---:|---:|---:|---:|
| `legitimo` | **20** | 0 | 0 | 0 | 0 | 20 |
| `suplantacion_bancaria` | 1 | **19** | 0 | 0 | 0 | 20 |
| `paqueteria_retenida` | 0 | 1 | **19** | 0 | 0 | 20 |
| `oferta_laboral_fraudulenta` | 5 | 0 | 0 | **15** | 0 | 20 |
| `extorsion` | 1 | 0 | 2 | 0 | **17** | 20 |
| **Total** | 27 | 20 | 21 | 15 | 17 | 100 |

Recall del revisor tomando la etiqueta humana como referencia:

| Clase humana | Aciertos | Recall |
|---|---:|---:|
| `legitimo` | 20/20 | 1.000 |
| `suplantacion_bancaria` | 19/20 | 0.950 |
| `paqueteria_retenida` | 19/20 | 0.950 |
| `oferta_laboral_fraudulenta` | 15/20 | 0.750 |
| `extorsion` | 17/20 | 0.850 |

### 7.4 Dónde se concentra el desacuerdo

- **Oferta laboral (5 casos, todos sintéticos).** El revisor los llama
  `legitimo` porque no encuentra una petición explícita de dinero o datos. Es la
  misma tensión que reveló la adjudicación: varias ofertas sintéticas son
  plausibles y no cumplen al pie de la letra la definición de la guía.
- **Extorsión (3 casos, todos sintéticos).** Dos usan pretexto de paquetería o
  carga retenida y uno es una cobranza sin amenaza. El revisor se queda con el
  pretexto y no con la posible intimidación; la adjudicación confirmó que no hay
  amenaza directa en esos textos.
- **Confusiones aisladas (2 casos).** Una paquetería se vuelve suplantación
  bancaria y una suplantación se vuelve legítimo; la primera sigue siendo fraude
  y la segunda es un aviso ambiguo.

Por origen:

| Origen | n | Kappa | Coincidencia |
|---|---:|---:|---:|
| `manual` | 31 | 0.959 | 96.8 % |
| `plantilla_legitima` | 17 | —* | 100 % |
| `sintetico_llm` | 52 | 0.779 | 82.7 % |
| **Manual + plantilla** | **48** | **0.972** | **97.9 %** |

\* El kappa no está definido cuando la submuestra contiene una sola clase
(todas las plantillas son `legitimo`).

La brecha es la conclusión más útil del experimento: **el revisor coincide casi
por completo con los mensajes escritos por humanos** y discrepa sobre todo en
los sintéticos. Eso no significa que el LLM sea infalible, sino que el etiquetado
sintético es la parte más ruidosa del corpus, en línea con la brecha
CV→validación de §3.2.

### 7.5 Adjudicación de los 10 desacuerdos

El autor revisó los diez casos el 18/11/2026. En **4** se mantuvo la etiqueta
humana y en **6** se aceptó la lectura del LLM. La adjudicación **no modifica el
corpus ni recalcula el kappa**: el adjudicador ya conocía la respuesta del
modelo, así que usarla como nueva referencia inflaría el acuerdo de forma
circular.

| id | Humano | LLM | Adjudicación | Lectura |
|---|---|---|---|---|
| `syn-0029` | suplantación | legítimo | **legítimo** | Sin solicitud de datos, códigos, pago ni enlace; smishing ambiguo |
| `man-paq-025` | paquetería | suplantación | **paquetería** | Suplanta a un comercio y pide $500; no es un banco |
| `syn-0168` | oferta | legítimo | **oferta** | Contratación inmediata y trabajo remoto al extranjero con urgencia |
| `syn-0167` | oferta | legítimo | **oferta** | “Comisiones por reclutar” es señal explícita de la guía |
| `syn-0139` | oferta | legítimo | **legítimo** | Oferta plausible, sin pago ni datos |
| `syn-0163` | oferta | legítimo | **legítimo** | Vacante con folio, sin solicitud alguna |
| `syn-0150` | oferta | legítimo | **oferta** | Comisiones por reclutar, ganancias altas y urgencia |
| `syn-0266` | extorsión | legítimo | **legítimo** | Sin amenaza no es extorsión; texto con artefacto de generación |
| `syn-0190` | extorsión | paquetería | **paquetería** | Aduana y paquete retenido con datos y plazo, sin amenaza directa |
| `syn-0189` | extorsión | paquetería | **paquetería** | Carga retenida y pago con enlace, sin amenaza directa |

Los motivos completos están en
`data/reportes_fase5/kappa_b_desacuerdos.csv`. Dos hallazgos de calidad del
corpus que conviene atender en la Fase 8: `syn-0266` conserva el artefacto
“(Formal, sin enlace)” y varias ofertas sintéticas son indistinguibles de una
vacante legítima.

### 7.6 Qué implica para la cascada

- El kappa **0.875** respalda usar el LLM en la zona gris: su clasificación es
  sustancialmente mejor que el azar y coincide con el anotador en 9 de cada 10
  mensajes.
- Su punto débil es la **oferta laboral** (recall 0.75) y la frontera
  extorsión/paquetería. En el test, la zona gris recibió cuatro ofertas y el LLM
  las resolvió todas (corrigió dos); con una muestra distinta podría ocurrir lo
  contrario. La Fase 8 debe vigilar ese caso.
- El experimento es **circular por diseño** (mismo modelo que el Nivel 2): mide
  si el modelo comparte la taxonomía humana, no su calidad independiente. El
  **Experimento A**, con `meta/muse-glimmer-30b` como revisor distinto, queda
  para la Fase 8 y es el que audita el corpus sin esa circularidad.

## 8. Limitaciones

1. **Tamaño del test.** 75 mensajes (15 por clase). Un solo error mueve el recall
   de una clase 6.7 puntos; las diferencias de 1–2 puntos entre configuraciones
   no deben leerse como superioridad estable.
2. **Un solo modelo de Nivel 2.** DeepSeek-V4.1-Flash devuelve 410; la
   comparación prevista entre modelos no se pudo ejecutar. Lo reportado es
   comparación de muestreo.
3. **Latencia de la API gratuita.** p50 de 109 s y p95 de 132 s con el prompt
   real, medidos con 4 hilos concurrentes (incluyen esperas por 429). El
   `LLM_TIMEOUT_S=60` inicial no se validó en régimen individual y, con esta
   carga, era insuficiente: en producción habría hecho fallback casi siempre en
   la zona gris. Se elevó a **180 s** el 18/11/2026, pero la latencia sigue siendo
   una limitación y debe medirse una solicitud aislada en la Fase 7.
4. **Origen del corpus.** No hay mensajes `origen: publico`; el corpus combina
   manuales, plantillas y sintéticos. La brecha CV→validación muestra que los
   sintéticos son más fáciles; las métricas de test son optimistas frente a
   mensajes reales de usuarios.
5. **Una sola ejecución del test.** El Nivel 1 es determinista y `temp0` también;
   aun así, la API puede cambiar de versión o de latencia. No se repitió la
   evaluación para no gastar el presupuesto de llamadas ni tocar la reserva.
6. **Costo.** La API se usó en modalidad de prueba gratuita: el costo monetario
   del prototipo es \$0. Se reportan tokens para poder extrapolar si se migra a
   tarifa por token; no se inventa un precio que la consola no publica.

## 9. Decisiones pendientes y recomendaciones

- **Timeout operativo (aplicado).** Se elevó `LLM_TIMEOUT_S` de 60 a **180 s**
  en `.env`, `.env.example` y la memoria §6.1/§15.1, porque el p95 medido es
  132 s. Con 60 s, la Fase 7 habría mostrado “análisis parcial” en casi toda la
  zona gris.
- **Repetir la comparación de modelos** si NVIDIA repone DeepSeek-V4.1-Flash,
  con el mismo prompt y las mismas filas.
- **Capturar la tarifa vigente** en la consola de NVIDIA al momento del reporte
  final para convertir los tokens en costo por análisis.
- **Adjudicación del Experimento B (completada).** Los diez desacuerdos quedaron
  revisados y con motivo en `data/reportes_fase5/kappa_b_desacuerdos.csv`:
  4 etiquetas humanas mantenidas y 6 lecturas del LLM aceptadas. No se
  recalcula el kappa (§7.5). En la Fase 8 conviene corregir `syn-0266` y revisar
  las ofertas sintéticas ambiguas.

## 10. Reproducción

```powershell
$env:PYTHONPATH = "src"

# 1. Entrenar el Nivel 1 y ajustar el umbral (solo train + validación)
python scripts/entrenar_nivel1.py
python scripts/ajustar_umbral.py

# 2. Comparar muestreo del Nivel 2 (validación; ~150 llamadas)
python scripts/comparar_llm.py --timeout 300

# 3. Evaluar las tres configuraciones (test reservado; ~75 llamadas)
python scripts/evaluar_fase5.py --timeout 300

# 4. Experimento B del kappa (train + validación; 100 llamadas)
python scripts/kappa_experimento_b.py --timeout 300

# Si se corta por límite de tasa, repetir solo los fallos:
python scripts/kappa_experimento_b.py --timeout 300 --max-hilos 2 --reusar

# 5. Figuras
python scripts/figuras_fase5.py
```

Los JSONL de cada llamada (sin texto de los mensajes, solo id, etiqueta, latencia
y tokens) quedan en `data/reportes_fase5/`. No se guarda el texto de ningún
mensaje ni la respuesta completa del LLM (regla 2). La única excepción es
`kappa_b_desacuerdos.csv`, que conserva el texto **sanitizado** de los 10
desacuerdos para que el autor pueda adjudicarlos; son mensajes del corpus, no de
usuarios, y no contienen datos personales.
