---
name: verifia-validacion
description: "Planifica y ejecuta la validación de VerifIA (Fase 8): pruebas unitarias, integración del flujo completo, estrés con solicitudes concurrentes, robustez ante mensajes ofuscados o imágenes de baja calidad, acuerdo humano–LLM con kappa de Cohen y prueba de usabilidad SUS con 10–15 voluntarios. Úsala al escribir la batería de pruebas, preparar el protocolo con usuarios, analizar sesgos por tipología o redactar el reporte de validación."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, pytest, httpx, scikit-learn, statsmodels, pandas. Opcional: playwright vía la skill webapp-testing."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-16"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §8.7, §9 Fase 8, §10 A8, §11, reglas 9, 10, 11, 13"
---

# Validación e integración — VerifIA (Fase 8)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. Si hay conflicto, gana la memoria.

## Regla que gobierna toda la fase

**Esta fase valida, no ajusta.** El conjunto de prueba sigue reservado y solo se evalúa para el reporte
final (regla 10). Si un resultado obliga a cambiar umbral, prompt, preprocesamiento o modelo, el cambio se
decide con **validación**, se documenta, y la métrica de prueba se recalcula **una vez** al final. Ajustar
mirando el test invalida el reporte.

## 1. Pirámide de pruebas

| Nivel | Qué cubre | Herramienta | Objetivo |
|---|---|---|---|
| Unitarias | sanitizador, Nivel 1, cascada, explicabilidad, OCR | `pytest` | Rápidas, sin red, deterministas |
| Integración | flujo texto e imagen de extremo a extremo | `pytest` + `TestClient` | Contrato entre módulos |
| Estrés | concurrencia y tiempos | `httpx`/`locust`/script propio | Estabilidad y latencia |
| Robustez | entradas adversas | tabla de casos | Nunca un 500 silencioso |
| E2E UI | flujo de 4 pasos, teclado, contraste | Playwright (`webapp-testing`) | Accesibilidad real |
| Usabilidad | personas | protocolo §7 | SUS + decisiones |

## 2. Unitarias — mínimo exigible

- **Sanitización**: ninguna entidad original sobrevive; los 9 marcadores; montos y folios intactos;
  idempotencia (ver `verifia-sanitizacion`).
- **Nivel 1**: pipeline reproducible con semilla; probabilidades suman 1; `puntuacion = round(100*(1−P(legitimo)))`
  dentro de [0, 100]; el modelo cargado produce las mismas predicciones que el entrenado (test de artefacto).
- **Cascada**: alta confianza no llama al LLM (mock que **falla si se invoca**); zona gris válida aplica `max`;
  JSON inválido, timeout, 429 y falta de clave caen en `nivel_1_fallback`.
- **Explicabilidad**: 15 snapshots (5 tipologías × 3 estados), aviso siempre presente, catálogo sin URLs ni
  teléfonos, máximo 5 señales.
- **OCR**: extractor de límites (5 MB / 4000 px / 12 MP), imagen corrupta → 422, imagen en blanco → mensaje claro.

Ninguna prueba unitaria debe depender de la red ni de `NVIDIA_API_KEY`.

## 3. Integración

Flujo texto:

```
POST /api/analizar/texto → sanitizar → Nivel 1 → (¿zona gris?) → Nivel 2 → explicar → ResultadoAnalisis
```

Flujo imagen:

```
POST /api/analizar/imagen → validar → OCR → texto editable → (usuario corrige)
→ sanitizar → clasificar → explicar → ResultadoAnalisis
```

Comprueba en cada uno:

- El esquema de respuesta cumple `ResultadoAnalisis` completo (§8.6).
- `fuente_diccionario`, `escalado_a_llm`, `discrepancia_niveles` son coherentes entre sí.
- El texto original **no** aparece en logs ni en la respuesta.
- El aviso orientativo está presente.

## 4. Estrés

- Escenarios: 20 y 50 solicitudes concurrentes de texto; mezcla con imágenes de ~1 MB.
- Mide **p50, p95, p99** y **tasa de errores**; separa las rutas que llaman al LLM de las que no.
- Verifica: el limitador de frecuencia responde 429 sin bloquear al resto; la memoria no crece entre rondas
  (no hay caché ni acumulación de estado); el proceso no se cae.
- Umbrales de aceptación: **defínelos con el desarrollador** (la memoria no fija latencia). Referencia
  sugerida, no normativa: p95 < 3 s sin LLM y < 10 s con LLM; 0 % de errores 5xx con entradas válidas.

## 5. Robustez — tabla obligatoria

| Entrada | Comportamiento esperado |
|---|---|
| Mensaje ofuscado (`4-5-3-1`, `O`↔`0`, `l`↔`I`) | No rompe; el riesgo puede ser menor, se documenta como limitación |
| Texto de 10 000 caracteres | Se procesa; responde en tiempo aceptable |
| Texto vacío o solo espacios | 422 con mensaje claro |
| Solo emojis | 422 o "sin texto analizable", nunca 500 |
| Otro idioma (inglés) | Se procesa con aviso de que el sistema está orientado a español |
| HTML o `<script>` en el mensaje | Se escapa; no se ejecuta ni se refleja como markup |
| Intento de inyección de prompt ("ignora las instrucciones…") | Se trata como datos; el esquema sigue validando |
| Imagen de baja resolución o borrosa | "No se pudo extraer texto" con indicación de repetir la captura |
| Imagen que no es un chat (foto cualquiera) | Se procesa o se rechaza con mensaje claro; nunca un resultado absurdo silencioso |
| Archivo con extensión falsa | Se rechaza por magic bytes |

Cada fila es una prueba con su aserción. Documenta el resultado real, incluso cuando difiere de lo esperado.

## 6. Acuerdo humano–LLM (kappa, §8.7)

Protocolo exacto:

1. **Muestreo**: 20 % estratificado del corpus (con 500 mensajes → 100; 20 por clase).
2. **Insumo**: texto **ya sanitizado** + guía de anotación + lista cerrada de 5 clases.
3. **Modelo revisor**: el que **no** se usa como Nivel 2 (evita circularidad).
4. **Parámetros**: `temperature=0`, salida JSON con un solo campo `tipologia`.
5. **Cálculo**:

```python
from sklearn.metrics import cohen_kappa_score, confusion_matrix

kappa = cohen_kappa_score(y_humano, y_llm, labels=TIPOLOGIAS)
matriz = confusion_matrix(y_humano, y_llm, labels=TIPOLOGIAS)
acuerdo = (y_humano == y_llm).mean()
```

6. **Adjudicación**: en cada desacuerdo, el autor decide la etiqueta correcta y registra el motivo. Esa cola
   de revisión es la misma que ya exige la regla 9 para datos sintéticos: el trabajo no se duplica.
7. **Interpretación (Landis & Koch)**: <0 nula · 0.01–0.20 leve · 0.21–0.40 moderada · 0.41–0.60 *fair* ·
   0.61–0.80 sustancial · 0.81–1 casi perfecta.

Dos experimentos, con propósitos distintos:

- **A (calidad del corpus)**: revisor ≠ Nivel 2 → ¿la guía es clara? ¿el corpus es consistente?
- **B (calidad del Nivel 2)**: revisor = Nivel 2 → evidencia directa para justificar el Nivel 2.

**Debes declarar en el reporte**: el kappa mide **acuerdo humano–LLM**, no confiabilidad inter-humana.
Presentarlo como inter-humano es un error metodológico. Si un docente o compañero hace una segunda
anotación humana sobre ~10 % (50 mensajes), se reporta como evidencia cruzada opcional.

## 7. Usabilidad (SUS)

**Protocolo**

1. 10–15 voluntarios, distintas edades y familiaridad tecnológica.
2. **Consentimiento informado** por escrito; sin recabar datos identificables.
3. Escenarios preparados con mensajes **sintéticos**; nunca mensajes personales reales.
4. Tareas: decidir qué hacer con cada mensaje **antes** y **después** de ver la alerta.
5. Observaciones sobre claridad, sin inducir respuestas.

**SUS** (10 ítems, escala 1–5, alternando positivo/negativo):

```python
def sus(r: dict[str, int]) -> float:
    total = sum((r[f"q{i}"] - 1) if i % 2 == 1 else (5 - r[f"q{i}"]) for i in range(1, 11))
    return total * 2.5      # rango 0–100
```

Ítems: (1) me gustaría usarlo con frecuencia · (2) lo encontré innecesariamente complejo · (3) me pareció
fácil de usar · (4) creo que necesitaría apoyo técnico · (5) las funciones están bien integradas ·
(6) hubo demasiada inconsistencia · (7) la mayoría aprendería a usarlo rápido · (8) lo encontré muy
engorroso · (9) me sentí seguro al usarlo · (10) necesité aprender mucho antes de empezar.

- Reporta **media, desviación estándar y rango**, no solo la media. Referencia descriptiva: 68 es el promedio
  histórico (Bangor et al., 2008); con 10–15 personas es **descriptivo, no confirmatorio**.
- Cada ítem 2, 4, 6, 8 y 10 es negativo (se invierte en la fórmula).

**Antes/después de la alerta** (decisión binaria acertada/no acertada, medidas repetidas):

```python
from statsmodels.stats.contingency_tables import mcnemar

tabla = [[acierto_antes_y_despues, acierto_antes_fallo_despues],
         [fallo_antes_acierto_despues, fallo_antes_y_despues]]
resultado = mcnemar(tabla, exact=True)   # exacto por n pequeño
```

Interpreta con cautela: con n ≈ 12 solo se detectan efectos grandes. Reporta proporciones e intervalos,
y evita concluir "no hay efecto" cuando el estudio simplemente no tiene potencia.

## 8. Sesgos y errores

Analiza las métricas **desagregadas**, no solo el macro:

- por **tipología** (¿qué clase concentra los errores?),
- por **longitud** del mensaje (corto/medio/largo),
- por **canal** (texto pegado vs. OCR),
- por **registro** (formal/informal, con o sin emojis).

Focos específicos exigidos por la memoria:

- **Falsos positivos** en notificaciones **legítimas de bancos y comercios** (el riesgo de sobre-alertar).
- **Falsos negativos** en modalidades **poco representadas** en el corpus.
- Recuerda la regla 11: en clases de fraude pesa más el **recall**, sin ignorar las falsas alarmas.

Para proporciones con n pequeño, reporta intervalo de confianza de Wilson en lugar de un porcentaje seco.

## 9. Reporte (`docs/reportes/reporte_validacion.md`)

1. Alcance y qué **no** se validó.
2. Resultados de unitarias/integración/estrés (tabla con p50/p95 y tasa de errores).
3. Matriz de robustez con el resultado real por caso.
4. Kappa: valor, matriz de confusión, desacuerdos adjudicados y su motivo.
5. Usabilidad: n, SUS (media ± DE), McNemar, observaciones cualitativas.
6. Análisis de sesgos por tipología, longitud y canal.
7. Limitaciones explícitas (incluida la naturaleza humano–LLM del kappa).
8. Ajustes propuestos y **si tocaron el test o no**.

## Criterios de aceptación (Fase 8)

- Batería unitaria y de integración en verde, sin red.
- Estrés documentado con tiempos y tasa de errores.
- Matriz de robustez completa.
- Kappa calculado y adjudicado manualmente, reportado como humano–LLM.
- SUS aplicado a 10–15 personas con consentimiento.
- Análisis de sesgos y reporte final entregado.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| Métricas de test mejoran tras cada ajuste | Se está tuneando con test | Vuelve a validación; test se mide una vez al final |
| Kappa altísimo y poco creíble | Revisor = Nivel 2 en el experimento A | Usa modelos distintos para A y B |
| Kappa presentado como inter-humano | Error metodológico | Declara "acuerdo humano–LLM" |
| Pruebas lentas o inestables | Llamadas reales a la API en unitarias | Mockea el cliente y falla si se invoca |
| Fuga en integración | Se loguea o devuelve el texto original | Aserción sobre logs y payload |
| SUS sin sentido | No se invirtieron los ítems negativos | Aplica la fórmula con inversión |
| "No hubo mejora" | n insuficiente | Reporta IC y limita la conclusión |
