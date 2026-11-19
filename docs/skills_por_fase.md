# Skills por fase — VerifIA

Mapa de trabajo entre las fases de `VerifIA_memoria_proyecto.md` §9 y las skills
instaladas en `.agents/skills/`. Es la versión operativa de la §17 de la memoria: la
memoria define **qué** hay que hacer; las skills dicen **cómo** hacerlo.

Regla de precedencia: si una skill contradice una decisión de la memoria (§15), se
corrige la skill, no la memoria.

---

## Cómo se cargan

1. **Una skill principal por fase.** Se carga al inicio, antes de escribir código.
2. **Las de apoyo, solo cuando hacen falta.** No es necesario cargarlas todas si la
   tarea no las toca; se cargan al llegar al punto concreto (por ejemplo, `webapp-testing`
   recién en el momento de generar capturas o probar la interfaz).
3. **Registrar la evidencia.** Cada fase cierra con su artefacto y su criterio de salida;
   el reporte de la Fase 9 cita ambos.

---

## Mapa por fase

| Fase (§9) | Skill principal | Skills de apoyo | Artefacto | Criterio para avanzar |
|---|---|---|---|---|
| **1** — Planeación y alcance | *(ninguna)* | `markdown-mermaid-writing` | `docs/plan_trabajo.md`, `docs/instalacion.md`, contenedor | Plan aprobado y `docker compose up` en estado `healthy` |
| **2** — Corpus | `verifia-corpus` | `huggingface-datasets`, `exploratory-data-analysis`, `citation-management` | `data/annotated/`, `data/splits/`, `docs/guia_anotacion.md` | 500 mensajes (100 por clase), deduplicados, sin PII, partición 70/15/15 |
| **3** — Sanitización | `verifia-sanitizacion` | — | `src/verifia/sanitizer/` + pruebas | ≥ 100 mensajes anotados; cobertura y precisión por entidad; ningún dato personal sobrevive |
| **4** — OCR | `verifia-ocr` | `webapp-testing`, `scientific-visualization` + `matplotlib` | `src/verifia/ocr/` + reporte CER/WER | ≥ 50 capturas; **CER ≤ 15 %**; se avisa si la imagen es insuficiente |
| **5** — Clasificador | `scikit-learn` | `verifia-nivel2-llm`, `statistical-analysis`, `scientific-visualization` + `matplotlib`, `shap` (opcional) | `classifier/` + `docs/reportes/metricas_clasificador.md` | F1 macro por clase; **recall ≥ 90 %** en fraude; 3 configuraciones comparadas |
| **6** — Explicabilidad | `verifia-explicabilidad` | `shap` (opcional) | `src/verifia/explain/` | Semáforo, señales resaltadas, catálogo de recomendaciones y aviso orientativo |
| **7** — Interfaz web | `verifia-api-docker` | `frontend-design`, `web-design-guidelines`, `webapp-testing` | `api/`, `web/`, Docker | `docker compose up` sirve el flujo de 4 pasos; límites y WCAG verificados |
| **8** — Validación | `verifia-validacion` | `statistical-analysis`, `webapp-testing`, `scientific-visualization` + `matplotlib` | `docs/reportes/` | Pruebas técnicas, SUS, kappa humano–LLM y análisis de sesgos |
| **9** — Documentación | `markdown-mermaid-writing` | `citation-management`, `scientific-visualization` | Documento final y manual de uso | Reporte académico con arquitectura, métricas, limitaciones y ley unificada |

### Por qué cada skill principal

| Fase | Justificación en una línea |
|---|---|
| 1 | No hay skill de planeación; el valor está en la documentación y el contenedor, ya cubiertos. |
| 2 | `verifia-corpus` define lotes, pacing, deduplicado por TF-IDF de char 4-gramas y la partición estratificada. |
| 3 | `verifia-sanitizacion` trae Presidio, los reconocedores mexicanos y la regla de `[CODIGO]`. |
| 4 | `verifia-ocr` cubre OpenCV + Tesseract `spa` y el protocolo de medición CER/WER. |
| 5 | `scikit-learn` guía pipelines, validación cruzada y métricas; `verifia-nivel2-llm` aporta el Nivel 2, el JSON validado y la cascada. |
| 6 | `verifia-explicabilidad` especifica el semáforo, el resaltado de señales y el catálogo por tipología. |
| 7 | `verifia-api-docker` contiene endpoints, límites, accesibilidad y el Dockerfile probado. |
| 8 | `verifia-validacion` define la batería de pruebas, el protocolo SUS y el kappa. |
| 9 | `markdown-mermaid-writing` da el formato de documentación y los diagramas editables. |

---

## Checklist por fase

- [x] **Fase 1** — `markdown-mermaid-writing` → plan, instalación, contenedor. Plan aprobado y contenedor `healthy` (16/11/2026).
- [x] **Fase 2** — `verifia-corpus` + `huggingface-datasets` / `exploratory-data-analysis` / `citation-management` → corpus de 500 construido, etiquetas confirmadas por el autor y pruebas en verde (16/11/2026).
- [x] **Fase 3** — `verifia-sanitizacion` → Presidio + `es_core_news_md`, 9 marcadores, reconocedores Luhn/CLABE/CURP/RFC y regla de `[CODIGO]`; 120 mensajes anotados (141 entidades), cero supervivencias y cero hallazgos duros en los 500 mensajes del corpus (17/11/2026).
- [x] **Fase 4** — `verifia-ocr` + `webapp-testing` (capturas sintéticas) + `scientific-visualization` → validación PNG/JPEG, preprocesamiento OpenCV, Tesseract `spa`, posprocesamiento y 60 capturas sintéticas (claro/oscuro, 4 resoluciones, WhatsApp/SMS) con CER 0.14 % y WER 0.80 % (17/11/2026).
- [x] **Fase 5** — `scikit-learn` + `verifia-nivel2-llm` + `statistical-analysis` → tres configuraciones comparadas en test (híbrido F1 macro 0.9352, recall binario de fraude 100 %, 14.7 % escalado), figuras y Experimento B del kappa (0.875; IC95 0.798–0.949) con 10 desacuerdos adjudicados (18/11/2026).
- [ ] **Fase 6** — `verifia-explicabilidad` → semáforo y recomendaciones.
- [ ] **Fase 7** — `verifia-api-docker` + `frontend-design` + `web-design-guidelines` + `webapp-testing` → sistema integrado.
- [ ] **Fase 8** — `verifia-validacion` + `statistical-analysis` + `webapp-testing` → reporte de validación.
- [ ] **Fase 9** — `markdown-mermaid-writing` + `citation-management` → documento final.

---

## Mapa inverso: skill → fase

| Skill | Tipo | Fase |
|---|---|---|
| `verifia-corpus` | Del proyecto | 2 |
| `verifia-sanitizacion` | Del proyecto | 3 |
| `verifia-ocr` | Del proyecto | 4 |
| `verifia-nivel2-llm` | Del proyecto | 5 (y Experimento B en 8) |
| `verifia-explicabilidad` | Del proyecto | 6 |
| `verifia-api-docker` | Del proyecto | 7 |
| `verifia-validacion` | Del proyecto | 8 |
| `scikit-learn` | Genérica | 5 |
| `exploratory-data-analysis` | Genérica | 2 |
| `huggingface-datasets` | Genérica | 2 (opcional) |
| `citation-management` | Genérica | 2 y 9 |
| `webapp-testing` | Genérica | 4, 7 y 8 |
| `frontend-design` | Genérica | 7 |
| `web-design-guidelines` | Genérica | 7 |
| `statistical-analysis` | Genérica | 5 y 8 |
| `scientific-visualization` | Genérica | 4, 5, 8 y 9 |
| `matplotlib` | Genérica | Implementación de las gráficas de 4, 5, 8 y 9 |
| `markdown-mermaid-writing` | Genérica | 1 y 9 |
| `shap` | Genérica | 5 y 6 (opcional) |
| `huggingface-papers` | Genérica | Sin fase fija: solo si se cita un paper de Hugging Face |
| `statsmodels` | Genérica | Sin fase fija: el proyecto no hace inferencia sobre coeficientes |
| `opencode` / `report` | Del entorno | Solo si surge una duda de OpenCode o hay que reportar un fallo de la herramienta |

---

## Notas de uso

**Experimento B del kappa.** Pertenece al protocolo de la §8.7 (Fase 8), pero conviene
ejecutarlo dentro de la Fase 5: es evidencia directa para justificar el Nivel 2. Se
reporta en `docs/reportes/metricas_clasificador.md` §7; la Fase 8 lo amplía en
`docs/reportes/kappa_revisor_automatico.md` con el Experimento A.

**Pruebas de interfaz.** No requieren MCP de navegador. `webapp-testing` usa Playwright
en modo headless: reproducible y deja capturas como evidencia. Instalación única:
`pip install playwright` y `python -m playwright install chromium`.

**Skills del proyecto frente a genéricas.** Las siete `verifia-*` son específicas y
tienen prioridad operativa; las genéricas aportan método (ML, estadística, gráficas,
documentación) y no conocen las reglas de la memoria, así que nunca se aplican a ciegas.

**Trazabilidad para el reporte.** En la Fase 9, este documento sirve para explicar cómo
se organizó el trabajo y por qué cada actividad usó un método concreto.
