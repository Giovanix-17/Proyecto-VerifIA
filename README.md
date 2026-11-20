# VerifIA

Prototipo académico que analiza mensajes y capturas de pantalla en español mexicano
para advertir sobre posibles fraudes o extorsiones digitales. Devuelve un semáforo de
riesgo, la tipología probable, las señales de alerta y acciones seguras recomendadas.

- **Institución:** Universidad Tecnológica de Tabasco (DATIC)
- **Asignatura:** Fundamentos de Inteligencia Artificial
- **Autor:** Giovani Hernández Arias
- **Alcance:** prototipo local en `http://localhost:8000`; no es un servicio público

<div align="center">
  <img src="docs/reportes/figuras/Demostracion.png" alt="Demostración de VerifIA — interfaz web de 4 pasos" width="600">
</div>

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

### 1. Configurar variables de entorno

```powershell
Copy-Item .env.example .env
```

Abre `.env` y rellena `NVIDIA_API_KEY` con tu clave de [build.nvidia.com](https://build.nvidia.com) (formato `nvapi-...`). El resto de variables tienen valores por defecto.

### 2. Levantar el contenedor

```powershell
docker compose up --build -d
```

Esto inicia la API FastAPI con Uvicorn y sirve la interfaz web estática.

### 3. Verificar que está funcionando

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Respuesta esperada: `{"status":"ok","version":"0.1.0"}`.

### 4. Abrir la interfaz

En tu navegador ve a:

```
http://localhost:8000
```

Verás el flujo de 4 pasos: pegar mensaje o subir captura, revisar texto extraído, analizar y ver el semáforo de riesgo.

### 5. Detener el contenedor

```powershell
docker compose down
```

### Ejecución sin Docker (opcional)

Si prefieres no usar Docker, instala las dependencias y ejecuta la API directamente:

```powershell
pip install -r requirements.txt
$env:PYTHONPATH = "src"
uvicorn verifia.api.main:app --reload --port 8000
```

## Estructura

```
├── Dockerfile / docker-compose.yml
├── .env.example                 # plantilla; el .env real no se versiona
├── pyproject.toml               # configuración de pruebas
├── requirements.txt             # dependencias de ejecución
├── requirements-dev.txt         # dependencias de pruebas
├── models/                      # modelo entrenado (nivel1.joblib)
├── src/verifia/                 # código fuente: sanitizer, ocr, classifier, explain, api
├── tests/                       # pruebas unitarias
└── web/                         # HTML, CSS y JS estáticos (sin build)
```

## Privacidad

Los mensajes se enmascaran y **no se almacenan**: no hay base de datos ni caché de
resultados, y el contenedor corre en modo de solo lectura. El resultado es
**orientativo** y no sustituye el criterio del usuario ni una denuncia formal.
