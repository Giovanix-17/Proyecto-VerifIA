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
[verificación de API](docs/reportes/verificacion_api.md).

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

## Estado del proyecto

| Fase | Estado |
|---|---|
| 1 — Planeación, repositorio y contenedor | Completada y aprobada (16/11/2026) |
| 2 — Corpus etiquetado | Completada: 500 mensajes, 500 etiquetas confirmadas por el autor, 22 pruebas (17/11/2026) |
| 3 — Sanitización | Pendiente |
| 4 — OCR | Pendiente |
| 5 — Clasificador en cascada | Pendiente |
| 6 — Explicabilidad | Pendiente |
| 7 — Interfaz web | Pendiente |
| 8 — Validación | Pendiente |
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
