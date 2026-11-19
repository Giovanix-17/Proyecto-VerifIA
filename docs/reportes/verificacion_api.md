# Verificación de la API de NVIDIA — 16–17/11/2026

## Alcance

Prueba de humo de los modelos configurados en `.env` y sondeo de candidatos a
revisor, contra `https://integrate.api.nvidia.com/v1` (API compatible con
OpenAI). Se hizo **una llamada por modelo**, sin prueba de carga ni de *pacing*.
El objetivo era confirmar autenticación, disponibilidad y que la respuesta se
pudiera interpretar (texto para el corpus, JSON para el Nivel 2 y el revisor).

## Resultados

| Rol | Modelo | Resultado | Latencia | Tokens (entrada/salida) | Detalle |
|---|---|---|---:|---:|---|
| Corpus (Fase 2) | `nvidia/nemotron-3.5-bolt-e4b` | ✅ | 14.34 s | 609 / 936 | Generó un mensaje válido con el prompt real de `corpus_generate.py` |
| Nivel 2 | `minimaxai/minimax-m3.1-flash` | ✅ | 0.61–5.22 s | 270 / 13 | JSON válido: `{"tipologia": "suplantacion_bancaria"}` |
| Nivel 2 anterior | `deepseek-ai/deepseek-v4.1-flash` | ❌ HTTP 410 | — | — | No está disponible; no aparece en `/v1/models` |

## Hallazgos

1. **DeepSeek-V4.1-Flash ya no responde.** La API devuelve `410 Gone` y el
   catálogo `/v1/models` (32 modelos) no contiene ningún modelo `deepseek-ai/*`.
2. **MiniMax-M3.1-Flash funciona** y devuelve JSON interpretable con
   `reasoning_effort=low`. Es el **Nivel 2 operativo** desde el 17/11/2026.
3. **Nemotron-3.5-Bolt-E4B funciona.** Con `max_tokens=800` la respuesta se
   truncó (`finish_reason=length`, 795 tokens de razonamiento); con
   `max_tokens=2000` terminó correctamente. El generador usa ahora 2600 (ver
   actualización del 17/11/2026).

## Modelo revisor elegido (§8.7)

El revisor debe ser **distinto** del Nivel 2 para evitar circularidad. Se
probaron candidatos del catálogo con el mismo prompt de clasificación y salida
JSON:

| Candidato | Resultado | Latencia | Perfil | Valoración |
|---|---|---:|---|---|
| **`mistralai/mistral-large-4-1t-a52b`** | ✅ JSON válido | 8.24 s | MoE grande (~1T / 52B activos), instrucciones generales | **Elegido:** el más cercano en capacidad y perfil a DeepSeek-V4.1-Flash |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | ✅ JSON válido | 3.87 s | MoE 30B / 3B activos, razonamiento, Apache 2.0 | Alternativa más rápida y barata; requiere `max_tokens≥1500` porque el razonamiento consume salida |
| `google/gemma-4-31b-it` | ✅ JSON válido | 15.18 s | Denso 31B, instrucciones generales | Válido, pero más lento y sin ventaja clara frente a los anteriores |
| `z-ai/glm-5.3-flash` | ❌ timeout (2 intentos) | >150 s | MoE *flash* | Descartado por latencia inaceptable en la prueba |
| `openai/gpt-oss-20b` | ❌ timeout | >90 s | Denso 20B, razonamiento | Descartado por latencia en la prueba |

**Decisión:** `mistralai/mistral-large-4-1t-a52b` queda como revisor en
`LLM_REVIEWER_MODEL` (`.env` y `.env.example`). Se eligió por su capacidad y su
parecido con el perfil de DeepSeek; `nvidia/nemotron-3.5-lightning-30b-a3b`
queda documentado como alternativa si se prioriza latencia y costo.

> **Revisado el 17/11/2026:** con el prompt real de §8.4, Mistral tarda
> 89.9–175.3 s y excedía `LLM_TIMEOUT_S=60` (valor vigente entonces; desde el
> 18/11/2026 es 180 s). El revisor definitivo pasó a
> `meta/muse-glimmer-30b` (35.6–36.2 s). Ver «Actualización del 17/11/2026».

## Implicaciones

- **Nivel 2:** `LLM_MODEL` es `minimaxai/minimax-m3.1-flash` en `.env` y
  `.env.example`, y se actualizaron la memoria (§6.1, §6.2, §9, §11) y la tabla
  de decisiones.
- **Errores transitorios observados:** en una repetición, MiniMax devolvió un
  `503` (*content safety screening temporarily unavailable*) y luego un `429`.
  Los reintentos inmediatos funcionaron; la Fase 5 debe implementar reintentos
  con espera y el fallback al Nivel 1 (regla 8), no asumir disponibilidad total.
- **Revisor:** `LLM_REVIEWER_MODEL` es
  `meta/muse-glimmer-30b`, distinto del Nivel 2; ya no hay duplicidad ni
  advertencia de circularidad (sustituyó a Mistral por latencia).
- La comparación prevista DeepSeek vs. MiniMax queda con un solo candidato
  operativo. Si NVIDIA repone DeepSeek, conviene repetirla.
- Repetir esta prueba cuando NVIDIA actualice el catálogo.

## Actualización del 17/11/2026: tokens, latencia y reintentos

Se repitieron las llamadas con el prompt real de cada tarea para medir la
holgura de `max_tokens` y la latencia. El límite anterior del corpus (2,000
tokens) llegó a consumir 1,839 (92 %) en un lote de 5 mensajes; por eso el
generador usa ahora **2,600**. Para el Nivel 2 y el revisor se fijó
`LLM_MAX_TOKENS=1300`.

### Holgura de tokens

| Tarea | Modelo | Límite | Máximo observado | Holgura | Veredicto |
|---|---|---:|---:|---:|---|
| Corpus, lote de 5 | `nvidia/nemotron-3.5-bolt-e4b` | 2,600 | 1,839 (incl. 1,328 de razonamiento) | 761 (29 %) | Correcto; antes quedaba al 92 % con 2,000 |
| Nivel 2 | `minimaxai/minimax-m3.1-flash` | 1,300 | 284 (incl. 85 de razonamiento) | 1,016 (78 %) | Sobrado |
| Revisor | `meta/muse-glimmer-30b` | 1,300 | 302 | 998 (77 %) | Sobrado |

En cinco lotes de corpus el consumo fue 1,119–1,839 tokens, siempre con
`finish_reason=stop` y 5/5 mensajes. Los prompts midieron 385–700 tokens, muy
por debajo del contexto de los tres modelos (65,536 en Nemotron; 262k–1M en
MiniMax).

### Latencia del revisor

| Modelo | Llamadas | Latencia | JSON válido | Decisión |
|---|---|---:|---|---|
| `mistralai/mistral-large-4-1t-a52b` | 4 exitosas + 3 con timeout | 89.9–175.3 s | Sí | **Descartado:** excedía el timeout de entonces (60 s) |
| **`meta/muse-glimmer-30b`** | 4 | **35.6–36.2 s** | Sí | **Elegido** |
| `google/gemma-4-31b-it` | 1 | 65.8 s | Sí | Descartado por latencia |
| `stepfun-ai/step-5-preview` | 1 | 75.2 s | Sí | Descartado por latencia |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 2 | 7.1 s | No (JSON inválido) | Descartado por salida |

**Decisión:** `LLM_REVIEWER_MODEL=meta/muse-glimmer-30b` en `.env` y
`.env.example`. Es distinto del Nivel 2 (no hay circularidad), cumple el timeout
previsto y devuelve JSON válido con 291–302 tokens de salida.

### Reintentos

`src/verifia/classifier/retry.py` añade `con_reintentos`, con estas reglas:

- se reintentan los estados **400, 408, 409, 429, 500, 502, 503 y 504**, además
  de timeouts y errores de conexión;
- `LLM_MAX_REINTENTOS=3` (intentos totales) y espera exponencial de 2, 4 y 8 s
  (`LLM_RETRY_BASE_S=2`) con jitter y tope de 20 s;
- 401, 404, errores de validación y JSON inválido se propagan sin reintento.

Se usa en `scripts/corpus_generate.py` y `scripts/verificar_api.py`, y queda
disponible para `level2_llm.py` en la Fase 5. La evidencia que motivó el cambio:
MiniMax devolvió `503 content safety screening is temporarily unavailable` y un
`400 Invalid request` esporádico; al repetir con espera respondió JSON válido en
13–16 s.

### `GET /v1/models` 404 en los logs

El par `GET /health` → `GET /v1/models` cada 30 s desde `172.18.0.1` no lo genera
VerifIA: `src/verifia/api/main.py` solo expone `/health`. Es un sondeo de Docker
Desktop (Gordon / Docker AI) que trata el puerto 8000 como un servidor
compatible con OpenAI. **Es benigno**: la aplicación no usa ese endpoint y el
contenedor sigue saludable. Se puede ignorar o desactivar Docker AI/Gordon en
Docker Desktop; no se añade un endpoint falso.

## Reproducción

```powershell
docker run --rm --env-file .env -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/verificar_api.py
```

> `scripts/verificar_api.py` se deja como comprobación reutilizable de la Fase 5.
> No forma parte del corpus ni modifica datos. Devuelve código 1 si algún modelo
> falla o si el Nivel 2 y el revisor coinciden.
