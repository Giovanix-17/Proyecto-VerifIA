---
name: verifia-sanitizacion
description: "Sanitiza datos personales en mensajes en español mexicano antes de cualquier clasificación en VerifIA. Úsala al implementar o revisar el módulo de la Fase 3: Microsoft Presidio con spaCy es_core_news_md, reconocedores de teléfono, correo, nombre, tarjeta (Luhn), CLABE, CURP y RFC, la regla de [CODIGO] y la reducción de enlaces a [ENLACE:dominio.tld]. También al escribir sus pruebas o al depurar falsos positivos/negativos de enmascarado."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, presidio-analyzer, presidio-anonymizer, spacy + es_core_news_md. No requiere red en ejecución: el modelo spaCy se descarga en build."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-15"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §7, §7.1, §9 Fase 3, §15.1 (#1,#2,#13)"
---

# Sanitización de datos personales — VerifIA (Fase 3 / OE1)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. **Si algo aquí contradice la memoria, gana la memoria.**
Si falta una definición (por ejemplo, un formato nuevo de PII), **pregunta al desarrollador**; no lo inventes.

## Invariantes (no negociables)

1. **Sanitizar antes de clasificar.** Ningún clasificador, Nivel 1 ni Nivel 2, recibe el texto original.
2. **No almacenar.** Sin tabla de equivalencias, sin caché, sin logs con el texto original. Solo se registran longitudes, contadores y tiempos.
3. **Marcadores tipificados, no borrado.** El marcador conserva la señal ("aquí había un teléfono") sin revelar el dato.
4. **Enlaces: solo dominio.** `[ENLACE:bit.ly]`, no la ruta ni parámetros.
5. **Exhaustividad sobre precisión.** Es mejor enmascarar de más que dejar pasar un dato; los casos residuales se documentan.
6. **Este módulo nunca decide riesgo.** Solo enmascara y produce rasgos; la decisión es del clasificador.

## Catálogo cerrado de marcadores (9)

| Marcador | Entidad | Regla |
|---|---|---|
| `[TELEFONO]` | Teléfono MX | 10 dígitos, lada, `+52` opcional, separadores `espacio . - ( )` |
| `[CORREO]` | Correo | RFC 5322 simplificado |
| `[NOMBRE]` | Persona | NER `PER` de spaCy `es_core_news_md` |
| `[CUENTA]` | Cuenta bancaria | CLABE 18 dígitos con dígito de control |
| `[TARJETA]` | Tarjeta | 13–19 dígitos que **pasan Luhn** |
| `[CODIGO]` | OTP/NIP/CVV | 4–8 dígitos **con contexto de solicitud** (§7.1) |
| `[CURP]` | CURP | 18 caracteres, estructura + estado válido |
| `[RFC]` | RFC | Persona física 13 / moral 12 |
| `[ENLACE:dominio.tld]` | Enlace | Solo host registrable |

No agregues marcadores nuevos sin autorización explícita.

## Orden de aplicación (crítico)

El solapamiento es la principal fuente de errores. Procesa **de lo específico a lo genérico**:

```
TARJETA → CLABE → CURP → RFC → CORREO → TELEFONO → CODIGO → ENLACE → NOMBRE
```

- `TARJETA` antes que `TELEFONO`: 16 dígitos también casan con patrones de teléfono.
- `CLABE` antes que `TELEFONO` y que `CODIGO`: 18 dígitos contienen secuencias de 4–8.
- `CODIGO` al final de los numéricos: su regla de contexto es más laxa y no debe robar dígitos ya reclamados.
- `NOMBRE` al final: el NER es el más propenso a falsos positivos y no debe competir por spans ya usados.

Implementación determinista sugerida: recolecta **todos** los spans candidatos, ordénalos por `(score desc, longitud desc)` y aplica **no-solapamiento** (gana el primero). Después sustituye de derecha a izquierda para no desplazar índices.

## Reconocedores de Presidio (patrón + validación)

Las reglas de formato se implementan como `PatternRecognizer` personalizados con `validate_result`
para los dígitos de control. No uses regex sueltos fuera de Presidio: se pierde la lógica de validación.

- **Luhn (tarjetas):** duplica dígitos alternos desde la derecha, resta 9 a >9, suma ≡ 0 (mod 10). Rechaza si no pasa.
- **CLABE:** 18 dígitos; a los primeros 17 se les aplica el ciclo de pesos `3,7,1`, se suma, y el dígito 18 debe ser `(10 − suma % 10) % 10`.
- **CURP:** 4 letras + `YYMMDD` + `[HM]` + clave de entidad válida + 3 consonantes + `[A-Z0-9]` + dígito. Validar la entidad contra la lista oficial evita falsos positivos.
- **RFC:** `[A-ZÑ&]{3,4}` + `YYMMDD` + homoclave de 3. No valides el dígito de control: el SAT no lo publica de forma estable.
- **Teléfono:** acepta `+52`, ladas de 2–3 dígitos y 10 dígitos nacionales; **exige** separadores o `+52` cuando el número no esté en un contexto claro, para no capturar montos ni folios.

### Configuración del motor

```python
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

provider = NlpEngineProvider(nlp_configuration={
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "es", "model_name": "es_core_news_md"}],
})
engine = AnalyzerEngine(
    nlp_engine=provider.create_engine(),
    supported_languages=["es"],
)
```

- **Elimina los recognizers por defecto en inglés** del registry antes de añadir los tuyos; si no, producirán entidades espurias y marcas inconsistentes.
- Registra cada `PatternRecognizer` con `supported_language="es"` y `supported_entity` igual al marcador destino.
- Ajusta `score_threshold` por entidad; documenta el valor elegido.

## Regla de `[CODIGO]` (§7.1)

Enmascara **solo** si se cumplen las dos condiciones:

1. Son **4–8 dígitos** (con separadores opcionales tipo `4-5-3-1`).
2. Aparecen a **≤ 30 caracteres** de una palabra clave de solicitud:
   `código, clave, token, OTP, pin, nip, cvv, contraseña, verificar, confirma, número de seguridad`.

**Nunca** enmascares: montos con `$` o "pesos", porcentajes, fechas, horas, folios, números de orden, ni números dentro de un marcador ya aplicado.

Casos residuales que deben quedar **documentados** (no resueltos): números escritos con palabras ("tres mil"), ofuscación deliberada (`O`↔`0`, `l`↔`I`), y datos sin contexto reconocible.

## Enlaces

1. Extrae la URL completa del texto.
2. Extrae el **host** con `urllib.parse.urlsplit`; descarta esquema, ruta, query, fragmento, credenciales y puerto.
3. Reduce a host registrable si puedes (quita `www.`; no intentes PSL completa sin dependencia extra).
4. Sustituye por `[ENLACE:host]`.
5. Calcula **rasgos estructurales** (no texto) para el Nivel 1:
   `es_acortador`, `ip_literal`, `num_subdominios`, `tld_sospechoso`, `guiones_en_host`, `longitud_host`, `tiene_puerto`.

Estos rasgos van en `rasgos_enlace`, **nunca** se concatenan al texto sanitizado como si fueran palabras.

## Contrato de salida

```python
class TextoSanitizado(BaseModel):
    texto: str                          # solo marcadores, sin PII
    marcadores: dict[str, int]          # {"[TELEFONO]": 2, ...}
    rasgos_enlace: list[dict[str, Any]] # uno por enlace
    entidades: int                      # total enmascarado
```

- Sin `id → valor original`. Sin mapa reversible.
- Idempotente: sanitizar dos veces produce el mismo texto.

## Pruebas (pytest)

1. **Test de supervivencia de PII**: sobre un lote de ≥100 mensajes anotados, ninguna entidad original debe aparecer en el texto de salida. Compara contra los valores literales del fixture.
2. **Cobertura y precisión por tipo de entidad** → tabla en `docs/reportes/`.
3. **Casos límite obligatorios**:
   - tarjeta de 16 dígitos que falla Luhn → **no** se enmascara como `[TARJETA]`.
   - CLABE con dígito de control incorrecto → no se enmascara como `[CUENTA]`.
   - `transfiera $5,000 hoy` → el monto **sobrevive**.
   - `su código es 4821` → `[CODIGO]`.
   - `pedido 4821` → **no** se enmascara.
   - `https://bit.ly/x7?d=5512345678` → `[ENLACE:bit.ly]`, el teléfono de la query desaparece.
   - texto vacío, solo emojis, 10 000 caracteres.
4. **Idempotencia** y **estabilidad** (mismo input → mismo output).

## Criterios de aceptación (Fase 3)

- Presidio es la base, con reconocedores personalizados y NER `es_core_news_md`.
- Los 9 marcadores existen y están cubiertos por pruebas.
- Regla de `[CODIGO]` verificada con casos positivos y negativos.
- Reporte de cobertura/precisión por entidad sobre ≥100 mensajes.
- Casos residuales documentados.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| Se enmascaran montos | `CODIGO` aplicado sin ventana de contexto | Exige palabra clave a ≤30 caracteres y excluye `$`/`pesos`/`%` |
| El teléfono queda dentro de la CLABE | Orden incorrecto | CLABE antes que TELEFONO y resolución por solapamiento |
| Se borran enlaces completos | Se usó el operador `replace` por defecto | Sustitución manual por span con `[ENLACE:host]` |
| Entidades duplicadas | Varios recognizers reclaman el mismo span | Ordena por score y longitud, aplica no-solapamiento |
| Nombres falsos positivos en mayúsculas | NER sobre texto sin contexto | Revisa umbral y documenta; prioriza exhaustividad |
| El modelo spaCy no carga en Docker | Se descargó en runtime | Descárgalo en build: `python -m spacy download es_core_news_md` |
