# Análisis de sesgos y errores — VerifIA (Fase 8, §8 del skill)

> Fuente: `data/reportes_fase5/evaluacion_test.json`, `data/reportes_fase5/metricas_clasificador.md`, `kappa_experimento_a.json`, `kappa_experimento_b.json`. Conjunto de prueba reservado: 75 mensajes (15 por clase).

---

## 1. Desagregación por tipología (conjunto de prueba, híbrido)

| Clase | Precisión | Recall | F1 | Soporte | Errores principales |
|---|---:|---:|---:|---:|---|
| `legitimo` | 1.0000 | 0.9333 | 0.9655 | 15 | 1 falso positivo (marcado como suplantación bancaria) |
| `suplantacion_bancaria` | 0.7778 | 0.9333 | 0.8485 | 15 | 1 legítimo → suplantación; 2 paquetería → suplantación; 1 oferta → suplantación |
| `paqueteria_retenida` | 0.9286 | 0.8667 | 0.8966 | 15 | 2 falsos negativos (confusión con suplantación) |
| `oferta_laboral_fraudulenta` | 1.0000 | 0.9333 | 0.9655 | 15 | 1 falso negativo (oferta → legítimo en Nivel 1, recuperado en zona gris) |
| `extorsion` | 1.0000 | 1.0000 | 1.0000 | 15 | Sin errores |
| **Macro** | **0.9413** | **0.9333** | **0.9352** | **75** | |

**Lectura:** la clase con menor recall es `paqueteria_retenida` (0.8667), seguida de `suplantacion_bancaria` y `oferta_laboral_fraudulenta` (0.9333). `extorsion` es perfecta. El patrón dominante de error es la **confusión entre tipologías de fraude** (paquetería ↔ suplantación), que conserva la alerta binaria (fraude vs. legítimo) pero no el tipo exacto.

---

## 2. Comportamiento binario fraude ↔ legítimo

| Configuración | Recall fraude | Precisión fraude | Fraude → legítimo (FN) | Legítimo → fraude (FP) |
|---|---:|---:|---:|---:|
| Solo Nivel 1 | 96.7 % (58/60) | 98.3 % (58/59) | 2 | 1 |
| Solo Nivel 2 | 93.3 % (56/60) | 100 % (56/56) | 4 | 0 |
| **Híbrido** | **100 % (60/60)** | **98.4 % (60/61)** | **0** | **1** |

El híbrido es la **única configuración sin falsos negativos binarios**: ningún mensaje de fraude del test quedó etiquetado como `legítimo`. El precio es un falso positivo (un legítimo marcado como suplantación bancaria). Esto es consistente con la regla 11 (la exhaustividad/recall pesa más en clases de fraude).

**Recall binario con IC95 Wilson:** 60/60 = 100 %, IC95 [94.0 %, 100 %]. Con 60 mensajes de fraude, el intervalo es ancho: un solo error movería el recall binario 1.7 puntos.

---

## 3. Desagregación por origen del mensaje

| Origen | n en test | Kappa (Experimento A) | Coincidencia (Experimento A) | Observación |
|---|---:|---:|---:|---|
| `manual` | 61 | — | — | Mensajes escritos de forma independiente; pueden ir en validación y prueba (regla 9 no aplica) |
| `plantilla_legitima` | 14 | — | — | Todas legítimas; no se calcula kappa (una sola clase) |
| `sintetico_llm` | 0 | 0.779 | 82.7 % | No aparecen en test (regla 9: sintéticos solo en train) |

El Experimento A (kappa 0.925, muestra train+val) muestra que el revisor `meta/muse-glimmer-30b` coincide mejor en mensajes `manual` + `plantilla` (kappa 0.972 en Exp. B) que en `sintetico_llm` (kappa 0.779). Los sintéticos son la parte más ruidosa del corpus, en línea con la brecha CV→validación observada en Fase 5.

---

## 4. Falsos positivos y falsos negativos por enfoque

### Falsos positivos (legítimo marcado como fraude)
- **1 caso:** un mensaje legítimo (notificación de cargo de BBVA) clasificado como `suplantacion_bancaria` por el Nivel 1 con alta confianza. No llegó a la zona gris, así que el Nivel 2 no pudo corregirlo. Es el principal falso positivo del híbrido.
- **Riesgo de sobre-alerta:** notificaciones legítimas de bancos y comercios que usan lenguaje de urgencia ("llame al número al reverso de su tarjeta") pueden activar el filtro. La regla 11 acepta este coste para evitar falsos negativos.

### Falsos negativos (fraude marcado como legítimo)
- **Híbrido:** 0 (ninguno en el test de 60 mensajes de fraude).
- **Nivel 1 solo:** 2 (3 suplantación + 2 paquetería según el reporte de Fase 5; 2 pasaron al binario legítimo). Estos son justamente los que la zona gris recupera.
- **Modalidades poco representadas:** la oferta laboral tiene el recall más bajo entre las clases de fraude en varios experimentos (0.75 en Exp. B revisor; 0.80 en Nivel 1 solo test). Es la clase que más se beneficia de la cascada.

---

## 5. Acuerdo humano–LLM (kappa) — naturaleza de la métrica

| Experimento | Revisor | Kappa | IC95 | Coincidencia | Interpretación (Landis & Koch) |
|---|---|---:|---:|---:|---|
| A (calidad del corpus) | `meta/muse-glimmer-30b` (≠ Nivel 2) | **0.925** | [0.862, 0.975] | 94.0 % | Casi perfecta |
| B (calidad del Nivel 2) | `minimaxai/minimax-m3.1-flash` (= Nivel 2) | 0.875 | [0.798, 0.949] | 90.0 % | Casi perfecta |

**Limitación explícita:** el kappa mide **acuerdo entre anotación humana y revisor automático (LLM)**, no confiabilidad inter-humana. Presentarlo como inter-humano sería un error metodológico. No sustituye la revisión humana; sirve como auditoría automatizada del corpus.

La brecha más relevante está en las clases `oferta_laboral_fraudulenta` y `extorsion`, donde el revisor tiende a leer `legitimo` o `paqueteria_retenida` cuando no hay una petición explícita de dinero o una amenaza directa. Seis desacuerdos en el Experimento A fueron adjudicados manualmente (4 se mantuvieron con la lectura del revisor, 2 con la humana).

---

## 6. Conclusiones del análisis de sesgos

1. **No hay evidencia de sesgo grave por canal** (todos los mensajes del test son de texto pegado; los casos de imagen/OCR se cubren en la matriz de robustez, no en métricas de clasificación).
2. **La clase `paqueteria_retenida` concentra la mayor parte de los errores de tipología** (confusión con suplantación bancaria). No afecta la alerta binaria pero sí el tipo de fraude mostrado.
3. **La clase `oferta_laboral_fraudulenta` es la más difícil para el revisor LLM** (recall 0.75 en Exp. B) y la que más se beneficia de la zona gris en el test.
4. **El recall binario fraude→legítimo es 100 % en el híbrido**, cumpliendo la regla 11 de exhaustividad en clases de fraude.
5. **El costo principal es un falso positivo** (legítimo como suplantación), aceptable dado el enfoque de alta exhaustividad.
