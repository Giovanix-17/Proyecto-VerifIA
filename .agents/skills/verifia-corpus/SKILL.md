---
name: verifia-corpus
description: "Construye y cura el corpus etiquetado de VerifIA (Fase 2): 500 mensajes en español mexicano, 100 por clase, con origen publico/plantilla_legitima/manual/sintetico_llm, generación sintética con nvidia/nemotron-3.5-bolt-e4b por lotes, deduplicado por TF-IDF de char 4-gramas, verificación de PII y partición estratificada 70/15/15 con test reservado. Úsala al recolectar o generar mensajes, anotar tipologías, limpiar duplicados, dividir los datos o documentar la guía de anotación."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, pandas, scikit-learn, openai SDK (NVIDIA), python-dotenv. Requiere NVIDIA_API_KEY solo para el modelo pequeño de generación."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-16"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §8.1-§8.3, §9 Fase 2, §10 A2, §15.1 (#11,#12,#16)"
---

# Corpus anotado — VerifIA (Fase 2)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. Si hay conflicto, gana la memoria.

## Objetivo y forma del dato

**500 mensajes** (100 por clase), mínimo aceptable **400**. Balanceado entre las 5 clases de §8.1:

| Etiqueta interna | Clase |
|---|---|
| `legitimo` | Mensaje legítimo |
| `suplantacion_bancaria` | Suplantación bancaria |
| `paqueteria_retenida` | Paquetería retenida |
| `oferta_laboral_fraudulenta` | Oferta laboral fraudulenta |
| `extorsion` | Extorsión |

Usa **una sola etiqueta por mensaje** (la tipología). El nivel de riesgo es opcional y solo sirve para
analizar errores; el sistema siempre lo deriva de la puntuación.

## Esquema de anotación (§8.2)

```python
{
  "id": "str",                     # único y estable
  "texto": "str",                  # español, sin PII real
  "tipologia": "legitimo|suplantacion_bancaria|paqueteria_retenida|oferta_laboral_fraudulenta|extorsion",
  "senales_alerta": ["urgencia", "amenaza", "suplantacion", "solicitud_datos", "enlace_sospechoso"],
  "nivel_riesgo": "bajo|medio|alto",   # opcional, referencia
  "origen": "publico|plantilla_legitima|manual|sintetico_llm",
  "revision_llm": "legitimo|..."       # solo si se aplicó el revisor
}
```

Validaciones obligatorias del CSV/JSONL:

- `id` no vacío y sin duplicados.
- `tipologia` dentro del conjunto cerrado.
- `origen` dentro del conjunto cerrado.
- `texto` no vacío y ≤ 10 000 caracteres.
- `senales_alerta` solo con valores del catálogo.

## Orígenes y su regla de uso

| Origen | Fuente | Puede ir a val/test |
|---|---|---|
| `publico` | Repositorios públicos, boletines de Condusef/SSPC, medios | Sí, si no es traducción automática |
| `plantilla_legitima` | Notificaciones cotidianas de plantillas públicas (bancos, paqueterías, comercios) | Sí |
| `manual` | Redactado por el autor, **independiente**, no derivado de ejemplos de entrenamiento | Sí |
| `sintetico_llm` | Generado con `nvidia/nemotron-3.5-bolt-e4b` | **No. Exclusivo de train** (regla 9) |

### Advertencias de procedencia

- **Traducciones automáticas** (p. ej. datasets del Hub traducidos con un LLM) son **derivadas**: trátalas
  como `sintetico_llm` y mantenlas fuera de val/test. Verifica la licencia antes de citarlas.
- Un dataset en español peninsular no equivale a español mexicano: revisa modismos, montos (`$` y "pesos"),
  nombres de bancos y paqueterías, y el canal (SMS vs WhatsApp).
- No existe corpus público de smishing mexicano; cualquier fuente externa es un punto de partida, no el corpus.

## Generación sintética

- Modelo: `nvidia/nemotron-3.5-bolt-e4b` (pequeño, barato, español en su post-training).
- **Lotes con control de ritmo (pacing)** para respetar los límites de la API; registra llamadas y errores.
- Salida por mensaje: `mensaje`, `tipologia`, `senales_alerta`.
- **La tipología que propone el LLM es un borrador.** La etiqueta definitiva la asigna el autor siguiendo
  `docs/guia_anotacion.md`.
- Registra el acuerdo borrador↔humano como evidencia adicional de calidad; **no** sustituye al protocolo §8.7.
- Presupuesto: ~250–400 llamadas. Si el saldo se agota, recorta sintético, **nunca** la evaluación.

Directrices del prompt de generación (para que los textos sirvan):

- Español mexicano, longitud variada (1–4 frases), canal SMS/WhatsApp.
- Que las 5 clases sean **distinguibles por señales lingüísticas**, no por nombres propios inventados.
- Incluir variantes: sin enlaces, con enlace, con monto, con plazo, con amenaza velada.
- Prohibido generar datos personales reales o verosímiles completos (teléfonos válidos, CLABE válidas).

## Depuración (en este orden)

1. **Normalización**: UTF-8, saltos `\n`, espacios múltiples, comillas tipográficas, NFC.
2. **Deduplicado exacto** por `texto` normalizado.
3. **Casi duplicados**: TF-IDF de **char 4-gramas** + similitud coseno **≥ 0.90** → conserva uno.
4. **Verificación de PII real**: pasa el corpus por el sanitizador; si aparecen entidades que parecen reales
   (teléfono válido con lada, correo con dominio real, CLABE con dígito de control correcto), elimina o
   sustituye el mensaje.
5. **Revisión de balance** por clase y por origen.

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(4, 4), lowercase=True)
X = vec.fit_transform(textos)
S = cosine_similarity(X)
# marca pares (i, j) con i < j y S[i, j] >= 0.90 y elimina el duplicado
```

- El deduplicado se hace **antes** de particionar. Si deduplicas después, quedan casi duplicados cruzando
  train/val/test y las métricas se inflan (fuga por casi duplicado).
- Aplica el umbral de forma **global** (matriz completa), no por subconjunto.

## Partición estratificada

- **70 / 15 / 15** por clase: `train`, `val`, `test`.
- Estratifica por `tipologia`; verifica conteos por clase en cada split.
- El **test se reserva hasta la evaluación final** (regla 10). No lo mires, no lo uses para elegir umbral ni
  prompt, no lo incluyas en análisis exploratorios.
- `sintetico_llm` **solo** en `train`. Si tras el split aparece sintético en val/test, el script debe fallar.
- Guarda `data/splits/{train,val,test}.jsonl` **y** un `split_manifest.json` con: semilla, fecha, hashes de
  los archivos, conteos por clase y versión del script.

```python
from sklearn.model_selection import train_test_split

train, temp = train_test_split(df, test_size=0.30, stratify=df["tipologia"], random_state=42)
val, test = train_test_split(temp, test_size=0.50, stratify=temp["tipologia"], random_state=42)
```

Verificación posterior obligatoria (falla el pipeline si no se cumple):

```python
assert set(train["origen"]) - {"sintetico_llm"} or True   # train admite todo
assert "sintetico_llm" not in set(val["origen"]) | set(test["origen"])
```

## Guía de anotación (`docs/guia_anotacion.md`)

Debe contener, por cada clase:

1. Definición en una frase.
2. Señales típicas (urgencia, amenaza, suplantación, solicitud de datos/códigos, enlace).
3. Qué **no** es esa clase (fronteras con las vecinas).
4. 3–5 ejemplos anotados.
5. Casos ambiguos y su resolución.

Fronteras que más se confunden y hay que fijar explícitamente:

- **Suplantación bancaria vs. extorsión**: la primera suplanta a una institución y pide credenciales/códigos;
  la segunda amenaza a la persona y exige dinero.
- **Paquetería retenida vs. oferta laboral**: ambas usan enlaces y urgencia; manda el pretexto del mensaje.
- **Legítimo vs. suplantación**: una notificación real de banco puede pedir "verificar"; la diferencia es que
  **no** solicita códigos ni enlaces a dominios ajenos.

## Criterios de aceptación (Fase 2)

- 500 mensajes (mínimo 400), 100 por clase, balanceados.
- Todos con `tipologia` definitiva asignada por el autor.
- Sin duplicados ni casi duplicados (coseno < 0.90 en todos los pares).
- Sin PII real verificada.
- Split 70/15/15 estratificado, sin `sintetico_llm` en val/test, con manifiesto reproducible.
- `docs/guia_anotacion.md` y reporte de cobertura de las 5 clases.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| Métricas demasiado altas | Casi duplicados entre splits | Deduplicar globalmente antes de particionar |
| Clase con 60 ejemplos | Generación desbalanceada | Genera por cuota y verifica conteos antes de anotar |
| Sintético en test | Split hecho antes de filtrar origen | Filtra por origen y añade el `assert` |
| Etiquetas inconsistentes | Se aceptó la tipología del LLM | Revisión humana obligatoria + guía |
| Teléfonos reales en el corpus | Plantillas o sintético sin control | Pasa todo por el sanitizador y descarta coincidencias |
| Split irreproducible | Sin semilla ni manifiesto | Fija `random_state` y guarda hashes |
