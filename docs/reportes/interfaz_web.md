# Interfaz web, API y contenedor (Fase 7)

> Backend `src/verifia/api/`, frontend estático `web/` y ejecución local con
> `Dockerfile` + `docker-compose.yml`.
> Fecha de cierre: 19/11/2026.

## 1. Resumen

La Fase 7 entrega el prototipo integrado de VerifIA en `http://localhost:8000`:

- **API FastAPI** para analizar texto y extraer el texto de una captura.
- **Flujo de 4 pasos** en HTML, CSS y JavaScript estáticos, sin framework ni
  paso de build.
- **Límites** de texto, imagen y frecuencia aplicados en el servidor.
- **Docker** como camino principal de ejecución, con usuario sin privilegios,
  sistema de archivos de solo lectura y sin volúmenes de datos.
- **Aviso de privacidad** y **aviso orientativo** visibles en la interfaz.

El criterio de salida se cumple: `docker compose up` levanta el sistema, el
contenedor queda `healthy`, el flujo de 4 pasos funciona con texto e imagen y
los límites y criterios de accesibilidad están verificados con pruebas
automatizadas y E2E.

## 2. Artefactos

| Artefacto | Ruta |
|---|---|
| Aplicación FastAPI | `src/verifia/api/main.py` |
| Estado y operaciones del servicio | `src/verifia/api/servicio.py` |
| Errores HTTP consistentes | `src/verifia/api/errores.py` |
| Límite de frecuencia en memoria | `src/verifia/api/limites.py` |
| Contratos HTTP y de resultado | `src/verifia/schemas.py` |
| Interfaz estática | `web/index.html`, `web/estilos.css`, `web/app.js` |
| Bocetos de baja fidelidad | `docs/wireframes_interfaz.md` |
| Imagen y orquestación | `Dockerfile`, `docker-compose.yml`, `.dockerignore` |
| Pruebas de API | `tests/test_api.py` |
| Pruebas estáticas de accesibilidad | `tests/test_interfaz.py` |
| E2E con Playwright | `scripts/e2e_interfaz.py` |

## 3. Endpoints

| Método | Ruta | Entrada | Salida |
|---|---|---|---|
| `GET` | `/health` | — | `{"status":"ok","version":"0.1.0"}` |
| `GET` | `/` | — | `index.html` |
| `GET` | `/static/*` | — | CSS y JS estáticos |
| `POST` | `/api/analizar/texto` | JSON `{"texto": str}` | `RespuestaAnalisis` |
| `POST` | `/api/analizar/imagen` | `multipart/form-data` (PNG/JPEG) | `RespuestaOCR` |

El flujo de imagen usa **dos llamadas**: la primera extrae el texto con OCR local
y lo devuelve para que la persona lo corrija; la segunda analiza el texto
corregido. La imagen nunca se envía a la API del LLM.

Ejemplo real contra el contenedor:

```text
POST /api/analizar/texto
{"texto":"BANCOMEX: su cuenta sera bloqueada HOY. Confirme su codigo en http://banco-verify.com/acceso o llame al 55 1234 5678"}

200 OK
{
  "tipologia": "suplantacion_bancaria",
  "nivel_riesgo": "alto",
  "puntuacion": 93,
  "estado": "rojo",
  "fuente_diccionario": "nivel_1",
  "escalado_a_llm": false,
  "texto_analizado": "BANCOMEX: su cuenta sera bloqueada HOY. Confirme su codigo en [ENLACE:banco-verify.com] o llame al [TELEFONO]"
}
```

`texto_analizado` es el texto **ya sanitizado**; la interfaz lo usa para
resaltar las señales y lo etiqueta como enmascarado. La respuesta conserva el
contrato de la Fase 6: `estado`, `nivel_riesgo`, `puntuacion`, `senales_alerta`,
`recomendaciones`, `advertencias`, `fuente_diccionario`, `escalado_a_llm`,
`discrepancia_niveles` y `aviso`.

## 4. Límites y errores

| Límite | Valor | Respuesta |
|---|---|---|
| Texto | 10 000 caracteres | `422` con código `texto_muy_largo` |
| Texto vacío o solo espacios | — | `422` con código `texto_vacio` |
| Imagen | 5 MB / 4000 px / 12 MP (PNG o JPEG) | `413` si excede el peso; `422` si el formato o la imagen no son válidos |
| Frecuencia | 10 solicitudes por IP cada 60 s (configurable) | `429` + `Retry-After` |
| LLM no disponible | — | No es `5xx`: fallback al Nivel 1 con aviso de análisis parcial |

Los errores usan el mismo cuerpo:

```json
{"detail": "Mensaje claro para la persona", "codigo": "codigo_estable"}
```

El límite de frecuencia usa una ventana deslizante **en memoria**, con poda de
claves inactivas. No hay Redis, base de datos ni caché de resultados. Al
ejecutarse un solo proceso de Uvicorn, el límite es efectivo para el prototipo;
si en el futuro se usaran varios workers, cada proceso tendría su propio
contador (limitación documentada).

## 5. Privacidad y no persistencia

| Invariante | Cómo se cumple |
|---|---|
| Sanitizar antes de clasificar | `analizar_texto` llama a `sanitizar()` antes de la cascada |
| No almacenar mensajes ni imágenes | Sin base de datos, sin caché y sin tabla de equivalencias |
| No guardar la imagen | El OCR es local; la imagen no se envía al LLM |
| No registrar contenido | El servicio fija `presidio_analyzer` en `WARNING`; la prueba con `caplog` busca el teléfono y el dominio del mensaje y no los encuentra |
| Aviso orientativo | `aviso` es obligatorio en el esquema y la interfaz lo muestra en cada resultado |
| Contenedor sin escritura | `read_only: true`, `tmpfs: [/tmp]` y usuario `verifia` sin privilegios |

La interfaz declara la privacidad en el paso 1: los datos se enmascaran, el
mensaje y la imagen no se guardan, y si el caso es ambiguo solo el **texto ya
enmascarado** se consulta a un servicio externo. La captura nunca sale del
equipo.

## 6. Docker

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Resultado verificado el 19/11/2026:

| Comprobación | Resultado |
|---|---|
| `docker compose config -q` | Sin errores |
| Contenedor `verifia` | `Up (healthy)` |
| `GET /health` | `{"status":"ok","version":"0.1.0"}` |
| Puerto | `127.0.0.1:8000 -> 8000/tcp`, no expuesto a la red local |
| Tamaño de la imagen | ≈ 1.98 GB (Tesseract, spaCy, Presidio, OpenCV) |
| Usuario | `verifia`, sin privilegios |
| Sistema de archivos | Solo lectura, con `/tmp` en `tmpfs` |
| Datos en la imagen | `data/`, `notebooks/`, `docs/`, `tests/` y `.env` excluidos por `.dockerignore` |

La imagen instala Tesseract con el paquete `spa`, las dependencias de
`requirements.txt` y el modelo `es_core_news_md` **durante el build**; no
descarga modelos al arrancar. El healthcheck consulta `/health` cada 30 s.

## 7. Interfaz y flujo de 4 pasos

| Paso | Qué ve la persona | Implementación |
|---|---|---|
| 1. Entrada | Pegar texto o subir captura, con aviso de privacidad y contador | `#paso-1`, radio de modo, `textarea`, `input[type=file]` |
| 2. Revisión | Texto editable; si vino de una captura, se corrige antes de analizar | `#paso-2`, `#texto-revision`, avisos del OCR |
| 3. Análisis | Estado de espera con `aria-live`, botón deshabilitado | `#paso-3`, `aria-busy`, foco en el panel |
| 4. Resultado | Semáforo con icono + palabra, tipología, puntuación, señales resaltadas, recomendaciones y aviso | `#paso-4`, `#veredicto`, `#resultado-detalle` |

La interfaz es mobile-first: una columna, base de 17 px, botones de 48 px y sin
scroll horizontal a 390 px. El veredicto y la acción principal van primero; el
detalle queda debajo.

## 8. Accesibilidad

### 8.1 Contraste

Ratios calculados con la fórmula WCAG 2.1:

| Combinación | Ratio | Mínimo | Resultado |
|---|---:|---:|---|
| Texto principal sobre fondo | 13.35:1 | 4.5:1 | ✅ |
| Texto secundario sobre panel | 7.53:1 | 4.5:1 | ✅ |
| Primario sobre panel | 7.86:1 | 4.5:1 | ✅ |
| Blanco sobre primario | 7.86:1 | 4.5:1 | ✅ |
| Borde de campo sobre panel | 4.06:1 | 3:1 | ✅ |
| Verde sobre su tinte | 5.74:1 | 4.5:1 | ✅ |
| Amarillo sobre su tinte | 6.28:1 | 4.5:1 | ✅ |
| Rojo sobre su tinte | 5.68:1 | 4.5:1 | ✅ |
| Bordes del semáforo sobre su tinte | 3.61–4.17:1 | 3:1 | ✅ |

### 8.2 Teclado y foco

- Enlace «Saltar al contenido» como primer foco.
- `:focus-visible` con contorno de 3 px en campos, botones, enlaces, `summary`
  y paneles enfocados por código.
- Al pasar al paso 3 el foco va al panel de espera; al terminar, al veredicto;
  si hay un error, al campo que lo causó.
- El modo texto/captura usa radios reales y etiquetas clicables, con un solo
  objetivo táctil por opción.
- `prefers-reduced-motion` desactiva la animación del indicador de espera.

### 8.3 Comunicación no cromática

Cada estado lleva **título, icono y color** (✔ Riesgo bajo, ⚠ Riesgo medio,
⛔ Riesgo alto). La prueba E2E comprueba que el texto del veredicto contiene la
palabra del estado y que la clase de color existe, pero no depende de ella.

### 8.4 Regiones vivas y etiquetas

| Elemento | Atributo |
|---|---|
| Errores | `#avisos[role=alert]` |
| Espera | `#paso-3[aria-live=polite]` |
| Resultado | `#paso-4[aria-live=polite]` |
| Avisos del OCR | `#avisos-ocr[aria-live=polite]` |
| Campos | `<label for="…">` para mensaje, revisión y captura |
| Contador | `aria-describedby="contador"` |

La revisión con `web-design-guidelines` añadió además `theme-color`,
`autocomplete="off"`, `touch-action: manipulation`, `text-wrap: balance`,
`[hidden]` explícito y estado `aria-busy` durante las solicitudes.

## 9. Pruebas

### 9.1 Suite de pytest

```powershell
$env:PYTHONPATH = "src"
pytest -q
ruff check src web tests scripts
```

Resultado al cierre:

| Comprobación | Resultado |
|---|---|
| `pytest` | **193 pruebas en verde** (22.8 s) |
| `ruff check` | Sin errores |
| Advertencias | 4 de `httpx2` por una API obsoleta de test; no afectan la aplicación |

`tests/test_api.py` cubre los casos exigidos por la skill:

- texto válido, vacío y de 10 001 caracteres;
- cuerpo JSON inválido;
- imagen válida, imagen > 5 MB, imagen vacía y formato no soportado;
- `429` con `Retry-After` al superar el límite;
- fallback `nivel_1_fallback` cuando el LLM falla (cliente mock);
- ausencia del texto de entrada en los logs (`caplog`);
- entrega de CSS y JS estáticos.

`tests/test_interfaz.py` cubre los invariantes estáticos de la interfaz:
idioma, salto de contenido, etiquetas, regiones vivas, privacidad, aviso
orientativo, ausencia de bloqueo del zoom, foco visible, movimiento reducido,
objetivos táctiles y escape del contenido dinámico.

### 9.2 E2E con Playwright

```powershell
pip install playwright
python -m playwright install chromium
python scripts/e2e_interfaz.py
```

Resultado: **20 comprobaciones en verde** contra el contenedor reconstruido.

| Caso | Resultado |
|---|---|
| Paso 1 con título y aviso de privacidad | ✅ |
| Flujo con texto: entrada → revisión → análisis → veredicto | ✅ |
| Foco en el veredicto al terminar | ✅ |
| Veredicto con palabra + icono + clase de color | ✅ |
| Recomendaciones (≥ 3) y aviso orientativo | ✅ |
| Señales resaltadas y texto enmascarado sin PII | ✅ |
| Error anunciado con `role=alert` y foco en el campo | ✅ |
| Flujo con imagen: OCR → revisión → veredicto | ✅ |
| Sin scroll horizontal en escritorio (1280 px) y móvil (390 px) | ✅ |
| Botón principal ≥ 44 px y campo a todo el ancho | ✅ |

Evidencia visual:

- [e2e_paso1_entrada.png](figuras/e2e_paso1_entrada.png)
- [e2e_paso4_resultado.png](figuras/e2e_paso4_resultado.png)
- [e2e_movil.png](figuras/e2e_movil.png)

Las capturas del E2E son sintéticas y se generan en el momento; no contienen
mensajes personales reales.

## 10. Revisión de diseño

La dirección visual está documentada en `docs/wireframes_interfaz.md`: una sola
columna, paleta fría de cuatro tonos más el semáforo, tipografía del sistema
(sin CDNs, coherente con la ejecución local) y el veredicto como pieza
principal. La revisión con `frontend-design` confirmó que la interfaz no usa
las plantillas genéricas de tarjetas, degradados ni tipografías externas; la
identidad se apoya en el riel de pasos, el semáforo y el tono tranquilo del
texto.

## 11. Limitaciones

- **Solo local.** No hay HTTPS, dominio, autenticación ni multiusuario; la
  publicación futura con Caddy + Let's Encrypt está documentada en
  `docs/instalacion.md` y fuera del alcance actual.
- **Límite de frecuencia por proceso.** Es suficiente con un worker de Uvicorn;
  con varios workers cada uno tendría su propio contador.
- **Latencia del LLM.** La zona gris puede tardar hasta el timeout de 180 s; la
  interfaz mantiene el estado de espera y deshabilita el botón, y si la API falla
  se muestra el fallback con aviso de análisis parcial.
- **OCR dependiente de la calidad de la captura.** Las cifras de la Fase 4 son
  una línea base con capturas sintéticas; la interfaz siempre pide revisar el
  texto extraído.
- **Sin validación con usuarios todavía.** La usabilidad, el tono y la utilidad
  percibida se medirán en la Fase 8 con SUS y con la comparación de decisiones
  antes/después de ver la alerta.

## 12. Criterios de aceptación

| Criterio de la Fase 7 | Estado |
|---|---|
| `docker compose up` levanta el sistema y responde en `http://localhost:8000` | ✅ Contenedor `healthy` y `/health` en 200 |
| Flujo de 4 pasos completo, texto e imagen | ✅ E2E 20/20 |
| Límites de texto, imagen y frecuencia aplicados y probados | ✅ Pruebas de API |
| Aviso de privacidad y aviso orientativo visibles | ✅ Prueba estática y E2E |
| Contraste, teclado y comunicación no cromática verificados | ✅ Ratios WCAG, E2E y revisión de guías web |
| Sin persistencia ni logs de contenido | ✅ Contenedor de solo lectura y prueba con `caplog` |
