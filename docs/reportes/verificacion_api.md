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
   `max_tokens=2000` terminó correctamente. El script de generación usa 2000.

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

## Implicaciones

- **Nivel 2:** `LLM_MODEL` es `minimaxai/minimax-m3.1-flash` en `.env` y
  `.env.example`, y se actualizaron la memoria (§6.1, §6.2, §9, §11) y la tabla
  de decisiones.
- **Errores transitorios observados:** en una repetición, MiniMax devolvió un
  `503` (*content safety screening temporarily unavailable*) y luego un `429`.
  Los reintentos inmediatos funcionaron; la Fase 5 debe implementar reintentos
  con espera y el fallback al Nivel 1 (regla 8), no asumir disponibilidad total.
- **Revisor:** `LLM_REVIEWER_MODEL` es
  `mistralai/mistral-large-4-1t-a52b`, distinto del Nivel 2; ya no hay
  duplicidad ni advertencia de circularidad.
- La comparación prevista DeepSeek vs. MiniMax queda con un solo candidato
  operativo. Si NVIDIA repone DeepSeek, conviene repetirla.
- Repetir esta prueba cuando NVIDIA actualice el catálogo.

## Reproducción

```powershell
docker run --rm --env-file .env -v "${PWD}:/app" -w /app verifia:0.1.0 `
  python scripts/verificar_api.py
```

> `scripts/verificar_api.py` se deja como comprobación reutilizable de la Fase 5.
> No forma parte del corpus ni modifica datos. Devuelve código 1 si algún modelo
> falla o si el Nivel 2 y el revisor coinciden.
