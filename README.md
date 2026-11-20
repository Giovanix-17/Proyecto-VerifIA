# VerifIA

Prototipo académico que analiza mensajes y capturas de pantalla en español mexicano
para advertir sobre posibles fraudes o extorsiones digitales. Devuelve un semáforo de
riesgo, la tipología probable, las señales de alerta y acciones seguras recomendadas.

- **Institución:** Universidad Tecnológica de Tabasco (DATIC)
- **Asignatura:** Fundamentos de Inteligencia Artificial
- **Autor:** Giovani Hernández Arias
- **Alcance:** prototipo local en `http://localhost:8000`; no es un servicio público

## Cómo funciona

1. El texto se **sanitiza** antes de cualquier análisis: teléfonos, correos, nombres,
   cuentas y códigos se sustituyen por marcadores tipificados.
2. Un **filtro clásico** (TF-IDF + modelo lineal) resuelve los casos de alta confianza.
3. Los casos ambiguos se escalan a un **LLM** con salida JSON validada.
4. El resultado se traduce a un semáforo con explicación y recomendaciones de un
   catálogo fijo (nunca generadas por el LLM).

La imagen nunca se envía al modelo: el OCR se ejecuta en local y solo el texto
resultante viaja a la API.

## Inicio rápido

```powershell
Copy-Item .env.example .env    # y rellena NVIDIA_API_KEY
docker compose up --build -d
Invoke-RestMethod http://localhost:8000/health
```

Detalle completo en [`docs/instalacion.md`](docs/instalacion.md).

Documentación del proyecto: [plan de trabajo](docs/plan_trabajo.md) ·
[instalación](docs/instalacion.md) · [guía de anotación](docs/guia_anotacion.md) ·
[skills por fase](docs/skills_por_fase.md) · [revisión Fase 2](docs/reportes/revision_fase2.md) ·
[cobertura de sanitización](docs/reportes/cobertura_sanitizacion.md) ·
[OCR: CER/WER](docs/reportes/ocr_cer_wer.md) ·
[métricas del clasificador](docs/reportes/metricas_clasificador.md) ·
[explicabilidad](docs/reportes/explicabilidad.md) ·
[interfaz web](docs/reportes/interfaz_web.md) ·
[verificación de API](docs/reportes/verificacion_api.md) ·
[reporte de validación (Fase 8)](docs/reportes/reporte_validacion.md) ·
[análisis de sesgos (Fase 8)](docs/reportes/analisis_sesgos.md) ·
[protocolo de usabilidad SUS (Fase 8)](docs/usabilidad_sus.md) ·
[acta de cierre Fase 8](docs/reportes/fase8_cierre.md).

## Corpus (Fase 2)

500 mensajes en español mexicano, 100 por clase, con partición 70/15/15. Los
sintéticos (`nvidia/nemotron-3.5-bolt-e4b`) van **solo a train**; validación y
prueba usan ejemplos manuales y plantillas legítimas.

```powershell
# 1. Generar sintéticos (reanudable; ~48 llamadas para 60 por clase)
docker run --rm -v "${PWD}:/app" -w /app --env-file .env verifia:0.1.0 `
  python scripts/corpus_generate.py --per-class 60

# 2. Depurar, auditar PII y particionar
docker run --rm -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/corpus_build.py

# 3. Revisar etiquetas (paso humano obligatorio)
docker run --rm -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/corpus_review.py --export
# editar data/annotated/revision.csv y luego:
docker run --rm -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/corpus_review.py --import
docker run --rm -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/corpus_build.py
```

Artefactos: `data/annotated/corpus.jsonl`, `data/splits/{train,val,test}.jsonl`,
`data/splits/split_manifest.json` y
[reporte de cobertura](docs/reportes/cobertura_corpus.md).

## Sanitización (Fase 3)

Antes de cualquier clasificación, todo texto pasa por Presidio + spaCy
`es_core_news_md`. Se sustituyen teléfonos, correos, nombres, CLABE, tarjetas,
códigos, CURP, RFC y enlaces (solo dominio) por los nueve marcadores del
catálogo. No se guarda el texto original ni una tabla reversible.

```python
from verifia.sanitizer import sanitizar

resultado = sanitizar("Mi teléfono es 55 1234 5678 y mi correo es ana@ejemplo.com")
resultado.texto       # "Mi teléfono es [TELEFONO] y mi correo es [CORREO]"
resultado.marcadores  # {'[TELEFONO]': 1, '[CORREO]': 1}
```

```powershell
# Repetir la medición de cobertura y precisión
python scripts/eval_sanitizer.py --report docs/reportes/cobertura_sanitizacion.md
```

Resultado: 120 mensajes anotados (141 entidades), 100 % de cobertura y
precisión en el conjunto de ajuste, cero PII superviviente, y cero hallazgos
duros al escanear los 500 mensajes del corpus con un detector independiente.
El detalle metodológico y los casos residuales están en el
[reporte](docs/reportes/cobertura_sanitizacion.md).

## OCR (Fase 4)

Las capturas PNG o JPEG se procesan **en local** con OpenCV y Tesseract en
español; la imagen nunca se envía a la API. Se aplican límites de 5 MB,
4000 px de lado mayor y 12 MP, se corrige la orientación EXIF, se amplían las
capturas pequeñas, se invierte el modo oscuro y se normaliza el fondo antes de
binarizar. El resultado es un **borrador editable** que el usuario revisa antes
del análisis.

```python
from verifia.ocr import extraer_texto, extraer_y_sanitizar

borrador = extraer_texto("captura.png")
borrador.texto        # texto reconocido, listo para corregir en la interfaz

borrador, limpio = extraer_y_sanitizar("captura.png")
limpio.texto          # ya con [TELEFONO], [CORREO], etc.
```

```powershell
# Generar 60 capturas sintéticas y medir CER/WER
python scripts/generar_capturas_ocr.py
python scripts/eval_ocr.py --report docs/reportes/ocr_cer_wer.md
```

Resultado: 60 capturas (claro/oscuro, cuatro resoluciones, WhatsApp y SMS),
CER 0.14 % y WER 0.80 %, sin fallas del pipeline. Las capturas son sintéticas,
así que las cifras son una línea base reproducible y no una garantía en campo;
el detalle está en el [reporte](docs/reportes/ocr_cer_wer.md).

## Clasificador en cascada (Fase 5)

El Nivel 1 es un TF-IDF de palabras y caracteres con Naive Bayes calibrado
(`P(máxima) ≥ 0.75` resuelve sin red). La zona gris pasa a MiniMax-M3.1-Flash,
que devuelve un JSON validado con Pydantic y cuyo contrato exige que cada señal
exista literalmente en el texto. El umbral se ajustó **solo con validación**.

En el conjunto de prueba reservado (75 mensajes, 15 por clase):

| Configuración | F1 macro | Escalado | Latencia p50 |
|---|---:|---:|---:|
| Solo Nivel 1 | 0.9074 | 0 % | 12 ms |
| Solo Nivel 2 | 0.9346 | 100 % | 72 s |
| **Híbrido** | **0.9352** | **14.7 %** | **0.01 s** |

El híbrido no dejó ningún fraude etiquetado como legítimo (60/60) y usó 11
llamadas al LLM en lugar de 75. El Experimento B del kappa obtuvo un acuerdo
humano–LLM de **0.875** (IC95 0.798–0.949): 0.972 en mensajes manuales y de
plantilla, 0.779 en sintéticos. Limitaciones: dos `429` en la corrida de solo
Nivel 2, muestra de test pequeña y latencia de la API gratuita con cola de ~80 s.
El detalle, las matrices de confusión y la adjudicación de los 10 desacuerdos
están en el [reporte de métricas](docs/reportes/metricas_clasificador.md).

```powershell
$env:PYTHONPATH = "src"
python scripts/entrenar_nivel1.py
python scripts/ajustar_umbral.py
python scripts/comparar_llm.py --timeout 300
python scripts/evaluar_fase5.py --timeout 300
python scripts/kappa_experimento_b.py --timeout 300
python scripts/figuras_fase5.py
```

## Explicabilidad (Fase 6)

Cada dictamen se traduce a un resultado que un ciudadano puede usar: un **semáforo
de tres estados** derivado siempre de la puntuación final (0–33 verde, 34–66
amarillo, 67–100 rojo), **hasta cinco señales resaltadas** sobre el texto
sanitizado con sus offsets y su origen, un **resumen determinista de tres
frases** en lenguaje sencillo y **recomendaciones de un catálogo cerrado** por
tipología. El resumen no se genera con el LLM y el estado no depende del
`nivel_riesgo` que propuso el modelo. El color nunca es el único canal: cada
estado lleva título, descripción e icono (✔, ⚠, ⛔), conforme a WCAG 2.1. El
aviso orientativo aparece en el 100 % de las respuestas, incluido el fallback.

```python
import joblib
from verifia.classifier.cascade import CascadeVerifIA

modelo = joblib.load("models/nivel1.joblib")
resultado = CascadeVerifIA(modelo, llamar_llm=False).analizar(
    "Su cuenta será bloqueada hoy. Ingrese su código"
)
resultado.estado            # 'rojo'
resultado.puntuacion        # 93
resultado.senales_alerta    # [SenalResaltada(...), ...] con frase, categoria, inicio, fin
resultado.recomendaciones   # catálogo fijo, nunca texto del LLM
resultado.aviso             # herramienta orientativa (regla 13)
```

El módulo no reclasifica ni recalcula la puntuación: solo explica lo que ya
decidió la cascada. Detalle, contrato de salida y limitaciones en el
[reporte de explicabilidad](docs/reportes/explicabilidad.md).

## Interfaz web (Fase 7)

La interfaz estática se sirve desde el mismo FastAPI, sin framework ni paso de
build, en `http://localhost:8000`. El flujo visible tiene cuatro pasos:

1. Pegar el mensaje o subir una captura PNG/JPEG.
2. Revisar y corregir el texto extraído por OCR.
3. Analizar (estado de espera con el botón deshabilitado).
4. Ver el semáforo, las señales resaltadas y las recomendaciones.

| Endpoint | Uso |
|---|---|
| `GET /health` | Comprobación de vida (`{"status":"ok","version":"0.1.0"}`) |
| `POST /api/analizar/texto` | Analiza un texto de hasta 10 000 caracteres |
| `POST /api/analizar/imagen` | Extrae el texto de una captura (≤ 5 MB, ≤ 4000 px, ≤ 12 MP) |
| `GET /` | Interfaz de 4 pasos |

Límites: texto de 10 000 caracteres, imagen de 5 MB / 4000 px / 12 MP y
10 solicitudes por IP cada 60 s (configurable con `RATE_LIMIT_MAX` y
`RATE_LIMIT_VENTANA_S`). Los errores siempre son JSON con `detail` y `codigo`.
La imagen nunca se envía al LLM; solo el texto ya sanitizado puede consultarse
al servicio externo. No hay base de datos, caché ni logs de contenido, y el
contenedor corre en modo de solo lectura.

```powershell
# Con el contenedor levantado:
.\.venv\Scripts\python.exe scripts\e2e_interfaz.py
```

El E2E de Playwright recorre texto e imagen, comprueba el foco, los errores
anunciados, el veredicto no cromático y la ausencia de scroll horizontal en
móvil. Detalle, tablas de contraste y limitaciones en el
[reporte de interfaz](docs/reportes/interfaz_web.md).

## Estado del proyecto

| Fase | Estado |
|---|---|
| 1 — Planeación, repositorio y contenedor | Completada y aprobada (16/11/2026) |
| 2 — Corpus etiquetado | Completada: 500 mensajes, 500 etiquetas confirmadas por el autor, 22 pruebas (17/11/2026) |
| 3 — Sanitización | Completada: Presidio + spaCy `es_core_news_md`, 9 marcadores, 120 mensajes anotados, cero PII superviviente (17/11/2026) |
| 4 — OCR | Completada: pipeline PNG/JPEG con Tesseract `spa`, límites, preprocesamiento y 60 capturas sintéticas con CER 0.14 % (17/11/2026) |
| 5 — Clasificador en cascada | Completada: F1 macro 0.9352, recall binario de fraude 100 %, 14.7 % escalado, kappa humano–LLM 0.875 (18/11/2026) |
| 6 — Explicabilidad | Completada: semáforo 0–100, hasta 5 señales con offsets, resumen de 3 frases, catálogo cerrado por tipología y aviso orientativo en todos los caminos; 171 pruebas (18/11/2026) |
| 7 — Interfaz web | Completada: API FastAPI, flujo de 4 pasos, límites, WCAG verificada y contenedor `healthy`; 193 pruebas y E2E 20/20 (19/11/2026) |
| 8 — Validación | Completada (20/11/2026): 207 pruebas pasadas, estrés, matriz de robustez, kappa Exp. A 0.925 y Exp. B 0.875, análisis de sesgos. Pendiente: aplicación del cuestionario SUS con 10–15 voluntarios reales (materiales listos en `docs/usabilidad_sus.md`). |
| 9 — Documentación final | Pendiente |

## Estructura

```
├── VerifIA_memoria_proyecto.md   # fuente de verdad del proyecto
├── Dockerfile / docker-compose.yml
├── .env.example                 # plantilla; el .env real no se versiona
├── data/                        # corpus y capturas de prueba
├── docs/                        # plan, instalación, skills por fase, guía de anotación, reportes
├── notebooks/                   # exploración y entrenamiento
├── scripts/                     # generación, depuración, partición, evaluación
├── src/verifia/                 # sanitizer, ocr, classifier, explain, api
├── tests/                       # pytest
└── web/                         # HTML, CSS y JS estáticos (sin build)
```

## Privacidad

Los mensajes se enmascaran y **no se almacenan**: no hay base de datos ni caché de
resultados, y el contenedor corre en modo de solo lectura. El resultado es
**orientativo** y no sustituye el criterio del usuario ni una denuncia formal.
