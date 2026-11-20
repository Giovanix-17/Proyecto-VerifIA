# Acta de cierre y validación de completitud — Fase 8 (VerifIA)

> Proyecto: VerifIA — detección de fraudes y extorsiones digitales.
> Fecha: 20/11/2026.
> Autor: Giovani Hernández Arias.
> Fuente de verdad: `VerifIA_memoria_proyecto.md` §9 Fase 8 y skill `verifia-validacion`.

---

## 1. Veredicto de completitud

| Estado | Fase 8 — Pruebas e integración |
|---|---|
| **Completada (ejecutable por el agente)** | ✅ Sí |
| **Pendiente de aplicación humana** | ⚠️ Cuestionario SUS con 10–15 voluntarios reales |

La Fase 8 está **completa en todo lo que es ejecutable por el agente**. El único elemento pendiente es la aplicación del cuestionario SUS con voluntarios reales, que requiere personas físicas y consentimiento informado —no ejecutable por el agente—. Los materiales del protocolo SUS están listos (`docs/usabilidad_sus.md`).

---

## 2. Validación contra los requisitos de la memoria (§9 Fase 8)

| Requisito (memoria) | Estado | Evidencia |
|---|---|---|
| Pruebas unitarias: sanitización, clasificación, explicabilidad | ✅ | `tests/test_sanitizer.py`, `test_nivel1.py`, `test_nivel2.py`, `test_cascade.py`, `test_explain.py` |
| Pruebas de integración del flujo completo | ✅ | `tests/test_api.py` (flujo texto de extremo a extremo, contrato `ResultadoAnalisis`) |
| Estrés con solicitudes concurrentes (tiempos y tasa de errores) | ✅ | `scripts/estres_fase8.py`, `data/reportes_fase8/estres_api.json` (60 req, 50 hilos, 0 % 5xx, p95 26.2 s) |
| Robustez: mensajes ofuscados, muy largos, vacíos, otro idioma | ✅ | `tests/test_robustez.py` (10/10 casos de texto pasan) |
| Robustez: imágenes de baja calidad | ⚠️ Omitido | Sin Tesseract en el host local; validado en Fase 4 (`docs/reportes/ocr_cer_wer.md`) |
| Usuarios: 10–15 voluntarios, consentimiento, SUS, antes/después | ⚠️ Pendiente | Materiales listos en `docs/usabilidad_sus.md`; aplicación requiere humanos reales |
| Fiabilidad de la anotación: kappa sobre 20 % estratificado | ✅ | Exp. A: kappa 0.925 (`kappa_experimento_a.json`); Exp. B: kappa 0.875 (Fase 5) |
| Adjudicación manual de desacuerdos | ✅ | 16 desacuerdos adjudicados en total (6 Exp. A + 10 Exp. B) |
| Kappa reportado como acuerdo humano–LLM (no inter-humano) | ✅ | Declarado explícitamente en `reporte_validacion.md` §5 y §8 |
| Sesgos y errores por tipología, registro, longitud, canal | ✅ | `docs/reportes/analisis_sesgos.md` |
| Falsos positivos en notificaciones legítimas de bancos/comercios | ✅ | Documentado en `analisis_sesgos.md` §4 (1 caso legítimo → suplantación) |
| Falsos negativos en modalidades poco representadas | ✅ | Documentado (oferta laboral, extorsión/paquetería) |
| Entregable: reporte de validación con observaciones y ajustes | ✅ | `docs/reportes/reporte_validacion.md` |

---

## 3. Validación contra los criterios de aceptación (skill `verifia-validacion`)

| Criterio de aceptación | Estado | Evidencia |
|---|---|---|
| Batería unitaria y de integración en verde, sin red | ✅ | 207 pruebas pasadas (`pytest tests/ -q`) |
| Estrés documentado con tiempos y tasa de errores | ✅ | `data/reportes_fase8/estres_api.json` |
| Matriz de robustez completa | ✅ | `tests/test_robustez.py` (11 casos; 2 omitidos sin Tesseract) |
| Kappa calculado y adjudicado manualmente, reportado como humano–LLM | ✅ | Exp. A (0.925) y Exp. B (0.875); desacuerdos en CSV |
| SUS aplicado a 10–15 personas con consentimiento | ⚠️ Pendiente | Protocolo y materiales listos (`docs/usabilidad_sus.md`) |
| Análisis de sesgos y reporte final entregado | ✅ | `docs/reportes/analisis_sesgos.md` + `reporte_validacion.md` |

---

## 4. Resultado de pruebas

```
207 passed in 47.97s   (tests/ completo)
```

Desglose:
- Unitarias + integración: 196 pruebas (sin red, LLM mockeado)
- Robustez: 11 pruebas (10 ejecutables + 1 de logs; 2 casos de imagen omitidos por falta de Tesseract en el host)

---

## 5. Elemento pendiente y próxima acción

**Pendiente:** Aplicar el protocolo SUS con 10–15 voluntarios reales (`docs/usabilidad_sus.md`).

**Próxima acción (Fase 9 — Documentación final):**
1. Aplicar SUS con voluntarios y registrar resultados en el reporte académico.
2. Completar el reporte académico final con la cita unificada de la ley de datos personales (2010 abrogada por 2025).
3. Capturar la tarifa vigente de NVIDIA por millón de tokens (métrica de costo por análisis).
4. Entrega final del proyecto VerifIA (cronograma referencial: 28/12/2026).

---

## 6. Aprobación de cierre de fase

| Concepto | Responsable | Fecha |
|---|---|---|
| Ejecución y validación de Fase 8 | Giovani Hernández Arias (agente opencode) | 20/11/2026 |
| Revisión académica (pendiente) | Alfredo de Jesús Gutiérrez Gómez | — |

> Nota: el estado "Fases 1–8 completadas" se registra en `docs/plan_trabajo.md` con la salvedad de que el cuestionario SUS queda listo para aplicación humana en la Fase 9.
