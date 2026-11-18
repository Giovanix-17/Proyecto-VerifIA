# Cobertura y precisión de la sanitización (Fase 3)

> Generado por `scripts/eval_sanitizer.py` sobre `tests/fixtures/pii_eval.jsonl` (120 mensajes anotados a mano).

## Configuración del motor

| Componente | Versión / valor |
|---|---|
| Presidio Analyzer | 2.2.366 |
| spaCy | 3.8.18 |
| Modelo NER | `es_core_news_md` 3.8.0 |
| Registro de reconocedores | solo los de VerifIA + NER español; sin los de inglés |
| Umbral mínimo por entidad | 0.5 (los patrones validados obtienen 1.0) |

Se construye un `RecognizerRegistry` vacío y se añaden los reconocedores propios. No se cargan los reconocedores por defecto en inglés porque producen entidades espurias y marcas inconsistentes.

## Orden de resolución y reglas

Los candidatos se ordenan de lo específico a lo genérico y se aplica no-solapamiento; después se sustituye de derecha a izquierda para no desplazar índices:

`TARJETA → CUENTA (CLABE) → CURP → RFC → CORREO → TELEFONO → CODIGO → ENLACE → NOMBRE`

- **Tarjeta:** 13–19 dígitos con Luhn; rechaza una CLABE válida de 18 dígitos y los teléfonos con `+52` que pasan Luhn por azar.
- **CLABE:** 18 dígitos con dígito de control (pesos 3, 7, 1).
- **CURP:** estructura, entidad federativa válida y fecha real; no se valida el dígito de control.
- **RFC:** 12 o 13 caracteres con fecha válida.
- **Correo:** simplificación de RFC 5322.
- **Teléfono:** 10 dígitos, con `+52` y `+52 1`; se descartan folios, montos y porcentajes por contexto.
- **Código:** 4–8 dígitos con palabra de solicitud a ≤ 30 caracteres (medida desde el final de la palabra) y sin contexto de monto, porcentaje, fecha, folio o código postal.
- **Enlace:** se conserva solo el dominio registrable; los rasgos estructurales van aparte, nunca al texto.
- **Nombre:** NER español, recorte de la oración, respaldo para tratamientos (`Lic.`, `Sra.`, `Dr.`) y filtro de categoría gramatical para no confundir verbos imperativos.

## Resultado global

| Métrica | Valor |
|---|---:|
| Entidades esperadas | 141 |
| Entidades encontradas | 141 |
| **Cobertura (recall)** | **100.0 %** |
| Marcadores producidos | 141 |
| Marcadores correctos | 141 |
| **Precisión** | **100.0 %** |

> **Lectura correcta:** este conjunto de 120 mensajes se usó durante el desarrollo para ajustar los reconocedores y la regla de `[CODIGO]`; por eso las cifras son optimistas y no equivalen a una validación con mensajes reales. La comprobación independiente sobre el corpus y las pruebas pytest de casos límite complementan la evidencia.

## Por tipo de entidad

| Entidad | Esperadas | Encontradas | Cobertura | Producidas | Correctas | Precisión | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| CODIGO | 15 | 15 | 100.0 % | 15 | 15 | 100.0 % | 100.0 % |
| CORREO | 15 | 15 | 100.0 % | 15 | 15 | 100.0 % | 100.0 % |
| CUENTA | 12 | 12 | 100.0 % | 12 | 12 | 100.0 % | 100.0 % |
| CURP | 11 | 11 | 100.0 % | 11 | 11 | 100.0 % | 100.0 % |
| ENLACE | 18 | 18 | 100.0 % | 18 | 18 | 100.0 % | 100.0 % |
| NOMBRE | 28 | 28 | 100.0 % | 28 | 28 | 100.0 % | 100.0 % |
| RFC | 9 | 9 | 100.0 % | 9 | 9 | 100.0 % | 100.0 % |
| TARJETA | 11 | 11 | 100.0 % | 11 | 11 | 100.0 % | 100.0 % |
| TELEFONO | 22 | 22 | 100.0 % | 22 | 22 | 100.0 % | 100.0 % |

## Supervivencia de datos personales

Comprobación sobre el texto final: ningún valor anotado debe aparecer en la salida. Para enlaces también se revisan los dígitos de la ruta y la query (el dominio sí se conserva, por diseño).

- Valores que sobreviven: **0**

## Comprobación independiente sobre el corpus

Se sanitizaron los 500 mensajes de `data/annotated/corpus.jsonl` y se escaneó la salida con el detector simple de la Fase 2 (regex + Luhn + dígito de control de CLABE), que no comparte código con Presidio.

- Mensajes procesados: **500**
- Mensajes con al menos un cambio: **175**
- Marcadores aplicados: **193**
- Hallazgos de PII dura tras sanitizar: **0**

El escaneo independiente no detecta correos, CURP, RFC, CLABE, tarjetas ni teléfonos en la salida. Los códigos contextuales y los enlaces se validan en el conjunto anotado.

## Casos residuales conocidos

Se documentan como pendientes; la regla 5 de la memoria prioriza exhaustividad sobre precisión.

- Números escritos con palabras (`tres mil`), ofuscación deliberada (`4-5-3-1`, `O`↔`0`, `l`↔`I`) y datos sin contexto reconocible.
- Folios de exactamente 10 dígitos sin palabra de contexto pueden parecer teléfonos; se descartan cuando aparecen `folio`, `pedido`, `orden`, `guía`, `referencia`, `factura` o `recibo` cerca.
- Nombres de una sola palabra muy comunes pueden escaparse del NER; los nombres en mayúsculas institucionales se revisan contra una lista de falsos positivos.
- La CURP se valida por estructura y entidad federativa; no se valida su dígito de control.
- El detector simple de la Fase 2 marca como código contextual el folio `XYZ12345` de `syn-0058` porque la palabra «código» aparece en la misma oración; la regla §7.1 lo excluye correctamente y no es una fuga.

