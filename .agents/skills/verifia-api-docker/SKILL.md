---
name: verifia-api-docker
description: "Construye la interfaz y el servicio de VerifIA (Fase 7 / OE4): API FastAPI para texto e imagen, frontend estático HTML/CSS/JS sin build, límites de entrada y de frecuencia, accesibilidad WCAG 2.1 y contenedor Docker reproducible en http://localhost:8000. Úsala al crear endpoints, modelos Pydantic de petición/respuesta, la pantalla de 4 pasos, el aviso de privacidad, el Dockerfile/docker-compose, o al depurar errores de arranque, límites y pruebas de integración."
license: "Uso interno del proyecto VerifIA"
allowed-tools: "Read Write Edit Bash Glob Grep"
compatibility: "Python 3.11+, fastapi, uvicorn, pydantic v2, python-multipart. Docker Desktop con WSL2. Sin npm, sin build de frontend, sin base de datos."
metadata:
  version: "1.0"
  last-reviewed: "2026-11-15"
  skill-author: "VerifIA (Giovani Hernández)"
  fuente: "VerifIA_memoria_proyecto.md §5, §9 Fase 7, §13, §15.1 (#5,#8,#10,#18)"
---

# API + interfaz + Docker local — VerifIA (Fase 7 / OE4)

Fuente de verdad: `VerifIA_memoria_proyecto.md`. Si hay conflicto, gana la memoria.

## Invariantes

1. **Local.** `docker compose up` → `http://localhost:8000`. HTTPS, dominio público y nube están fuera de alcance.
2. **Sin persistencia.** No se guardan mensajes, imágenes ni dictámenes. Sin base de datos, sin Redis, sin caché.
3. **Sin logs de contenido.** Nada del texto del usuario ni de la imagen en stdout/archivos.
4. **Sin framework de frontend ni npm.** HTML, CSS y JS estáticos servidos por FastAPI.
5. **El aviso de que la herramienta es orientativa es obligatorio** en cada resultado (regla 13).

## 1. Endpoints

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| `POST` | `/api/analizar/texto` | JSON `{"texto": str}` | `ResultadoAnalisis` |
| `POST` | `/api/analizar/imagen` | `multipart/form-data` (PNG/JPEG) | `ResultadoAnalisis` + texto OCR extraído |
| `GET` | `/health` | — | `{"status":"ok","version":...}` |
| `GET` | `/` | — | `index.html` estático |

Flujo de imagen: valida límites → OCR → **devuelve el texto extraído** para que el usuario lo corrija →
segunda llamada con el texto corregido → sanitización → clasificación.

```python
class SolicitudTexto(BaseModel):
    texto: str = Field(min_length=1, max_length=10_000)

class ResultadoAnalisis(BaseModel):
    tipologia: str
    nivel_riesgo: Literal["bajo", "medio", "alto"]
    puntuacion: int = Field(ge=0, le=100)
    senales_alerta: list[Senal]
    justificacion: str
    resumen_legible: str
    recomendaciones: list[str]
    advertencias: list[str]
    fuente_diccionario: Literal["nivel_1", "nivel_2", "nivel_1_fallback"]
    escalado_a_llm: bool
    discrepancia_niveles: bool
    aviso: str = "Resultado orientativo. No sustituye su criterio ni una denuncia formal."
```

- Las **recomendaciones salen de un catálogo predefinido por tipología**, nunca del LLM (regla 6).
- `fuente_diccionario` y `escalado_a_llm` son obligatorios para trazabilidad.
- No devuelvas el texto sanitizado completo salvo que la UI lo necesite para resaltar señales; si lo haces,
  indica que ya está enmascarado.

## 2. Límites y errores

| Límite | Valor | Respuesta |
|---|---|---|
| Texto | 10 000 caracteres | 422 con mensaje claro |
| Imagen | 5 MB / 4000 px / 12 MP | 413 o 422 según el caso |
| Frecuencia | por IP, en memoria | 429 + `Retry-After` |
| Timeout del LLM | 180 s, 1 reintento | fallback, no 5xx |

- Rate limit **en memoria** (token bucket o ventana deslizante por IP): sin Redis. Documenta el valor y
  límpialo periódicamente para no crecer sin control.
- Errores siempre en JSON consistente: `{"detail": "...", "codigo": "texto_muy_largo"}`.
- No expongas trazas internas ni rutas del sistema en los mensajes de error.

## 3. Frontend estático (sin build)

- `web/` con `index.html`, `estilos.css`, `app.js`. `app.setup` con `StaticFiles` en `/static` y `/` sirviendo el index.
- **Flujo de 4 pasos visibles**: (1) ingresar mensaje o captura → (2) revisar texto extraído → (3) analizar →
  (4) resultado.
- **Mobile-first**: una columna, tipografía ≥16 px, botones ≥44 px, sin scroll horizontal.
- El JS usa `fetch` a los endpoints; muestra estados de carga y desactiva el botón mientras espera.
- Aviso de privacidad visible: *"Los mensajes se enmascaran y no se almacenan."*
- El veredicto y la acción principal van primero; el detalle después.

### Accesibilidad (WCAG 2.1)

- Contraste ≥ 4.5:1 en texto normal y ≥ 3:1 en elementos gráficos.
- El riesgo se comunica con **texto + icono**, nunca solo con color (verde/amarillo/rojo).
- Navegación completa por teclado, `:focus-visible` evidente, sin trampas de foco.
- `<label>` asociado a cada campo; `aria-live="polite"` en la zona de resultado.
- `alt` en imágenes decorativas vacío; errores anunciados, no solo pintados.
- Lenguaje claro, sin tecnicismos; no uses "TF-IDF", "cascada" ni "Pydantic" en la UI.

## 4. Docker

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download es_core_news_md

COPY . .
RUN useradd -m verifia && chown -R verifia:verifia /app
USER verifia

EXPOSE 8000
CMD ["uvicorn", "verifia.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
services:
  verifia:
    build: .
    env_file: .env
    ports: ["8000:8000"]
    read_only: true
    tmpfs: ["/tmp"]
    security_opt: ["no-new-privileges:true"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- Descarga el modelo spaCy **en build**, no en runtime (sin red al arrancar).
- Usuario no root; `read_only` + `tmpfs` refuerzan que no se guarde nada.
- `.dockerignore` con `data/`, `notebooks/`, `.env`, `tests/`, `__pycache__`.
- **Sin volúmenes** que monten `data/` en producción: no hay nada que persistir.
- `--host 0.0.0.0` es necesario dentro del contenedor; el puerto se publica solo en `localhost`.

## 5. Pruebas

- `pytest` + `fastapi.testclient.TestClient`:
  - texto válido, texto vacío, texto de 10 001 caracteres;
  - imagen válida, imagen > 5 MB, formato no soportado;
  - 429 al superar el límite de frecuencia;
  - respuesta con `fuente_diccionario="nivel_1_fallback"` cuando el LLM falla (mock).
- **Ningún log contiene el texto de entrada**: test que captura `caplog` y busca el literal.
- E2E con Playwright (skill `webapp-testing`): flujo de 4 pasos, teclado, y que el veredicto no dependa del color.

## Criterios de aceptación (Fase 7)

- `docker compose up` levanta el sistema y responde en `http://localhost:8000`.
- Flujo de 4 pasos completo, texto e imagen.
- Límites de texto, imagen y frecuencia aplicados y probados.
- Aviso de privacidad y aviso de resultado orientativo visibles.
- Contraste, teclado y comunicación no cromática verificados.

## Errores frecuentes

| Síntoma | Causa | Corrección |
|---|---|---|
| `Connection refused` desde el host | Uvicorn escucha en `127.0.0.1` | `--host 0.0.0.0` dentro del contenedor |
| La imagen pesa >1 GB | Se copió `data/` o `.venv` | `.dockerignore` y `COPY` selectivo |
| Tesseract falla solo en Docker | Falta `tesseract-ocr-spa` | Instálalo en la imagen |
| spaCy descarga en cada arranque | Modelo no horneado | `python -m spacy download` en build |
| 500 al subir imagen | Falta `python-multipart` | Añádelo a `requirements.txt` |
| El resultado depende solo del color | Semáforo sin texto/icono | Añade etiqueta y `aria-label` |
| CORS bloquea el fetch | Se sirvió el front desde otro origen | Sirve el estático desde el mismo FastAPI |
