# Guía de instalación — VerifIA

Cómo ejecutar el prototipo en una sola computadora. El camino principal es
**Docker Desktop (WSL2)**; el entorno virtual con Python es la alternativa.

Fuente: `VerifIA_memoria_proyecto.md` §9 Fase 1 y §15.1 #8 y #10.

---

## Requisitos

| Requisito | Mínimo | Verificado en este equipo |
|---|---|---|
| Sistema operativo | Windows 11 (64 bits) | Windows 11 Pro, build 26300 |
| RAM | 8 GB (16 GB recomendado) | 15.7 GB |
| Disco libre | 10 GB | 47 GB (16/11/2026) |
| CPU | Con virtualización habilitada (VT-x/AMD-V) | i5-12450H, virtualización activa |
| Docker Desktop | 4.x con motor WSL2 (Compose ≥ 2) | 4.99 / Compose 5.7, instalado el 16/11/2026 |
| Clave de API de NVIDIA | Con créditos de prueba | en `.env` (no se versiona) |

---

## Camino principal: Docker Desktop

### 1. Comprobar Docker

```powershell
docker version
docker compose version
docker run --rm hello-world
```

Los tres deben responder sin error. Si `docker` no existe, instálalo con:

```powershell
winget install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements
```

y reinicia la sesión al terminar.

### 2. Configurar las variables de entorno

```powershell
Copy-Item .env.example .env
notepad .env
```

Rellena `NVIDIA_API_KEY` con tu clave de <https://build.nvidia.com> (formato `nvapi-…`).
El resto de los valores ya viene con los defaults del proyecto. **`.env` nunca se sube
al repositorio** (está en `.gitignore`).

### 3. Construir y levantar

```powershell
docker compose up --build -d
```

La primera construcción tarda varios minutos: instala Tesseract con el paquete de
español, las dependencias de Python y descarga el modelo `es_core_news_md`.

### 4. Verificar

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

Esperado: el contenedor en estado `healthy` y la respuesta
`status=ok  version=0.1.0`.

### 5. Operación diaria

| Acción | Comando |
|---|---|
| Ver registros | `docker compose logs -f` |
| Detener | `docker compose down` |
| Reconstruir tras cambiar dependencias | `docker compose up --build -d` |
| Recrear tras cambiar `.env` | `docker compose up -d --force-recreate` |
| Entrar al contenedor | `docker compose exec verifia bash` |

Notas del diseño del contenedor:

- Corre con usuario sin privilegios y con `read_only: true`, de modo que **no puede
  escribir nada** de forma permanente (regla 2: no almacenar mensajes).
- El puerto se publica solo en `127.0.0.1`: no queda expuesto a la red local.
- `.env` **no** se copia a la imagen; entra como variable de entorno al arrancar.

---

## Alternativa: entorno virtual (sin Docker)

Útil para desarrollar módulos aislados o si Docker Desktop no está disponible.

1. **Python 3.12** (recomendado). Con 3.13 funciona casi todo, pero spaCy, Presidio y
   OpenCV publican ruedas más probadas para 3.12. Si tienes varias versiones:
   `py -3.12 -m venv .venv`.
2. Crear y activar el entorno:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   Si PowerShell bloquea el script: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

3. Instalar dependencias y el modelo de español:

   ```powershell
   pip install -r requirements-dev.txt
   python -m spacy download es_core_news_md
   ```

4. Instalar Tesseract para Windows (necesario a partir de la Fase 4): instalador
   UB-Mannheim, marcando el idioma **Spanish** (`spa.traineddata`). Añade su carpeta
   al `PATH` y comprueba: `tesseract --list-langs` debe listar `spa`.

5. Arrancar el servicio:

   ```powershell
   $env:PYTHONPATH = "src"
   uvicorn verifia.api.main:app --reload --port 8000
   ```

6. Pruebas: `pytest`.

---

## Variables de entorno

| Variable | Para qué sirve | Valor por defecto |
|---|---|---|
| `NVIDIA_API_KEY` | Autenticación con la API de NVIDIA | *(obligatoria, sin default)* |
| `LLM_MODEL` | Modelo del Nivel 2 de la cascada | `deepseek-ai/deepseek-v4.1-flash` |
| `LLM_REVIEWER_MODEL` | Revisor automático del kappa (distinto del Nivel 2) | `minimaxai/minimax-m3.1-flash` |
| `LLM_CORPUS_MODEL` | Generación del corpus sintético | `nvidia/nemotron-3.5-bolt-e4b` |
| `LLM_TIMEOUT_S` | Timeout por llamada | `60` |
| `LLM_MAX_TOKENS` | Tope de tokens de salida | `1200` |
| `LLM_REASONING_EFFORT` | Esfuerzo de razonamiento | `low` |
| `NVIDIA_BASE_URL` | Endpoint compatible con OpenAI | `https://integrate.api.nvidia.com/v1` |

### Comprobar la clave sin mostrarla

```powershell
$k = (Select-String -Path .env -Pattern '^NVIDIA_API_KEY=').Line -replace '^NVIDIA_API_KEY=',''
Invoke-RestMethod -Uri 'https://integrate.api.nvidia.com/v1/models' -Headers @{ Authorization = "Bearer $k" } |
  Select-Object -ExpandProperty data | Where-Object { $_.id -match 'deepseek|minimax|nemotron' } | Select-Object id
```

Interpretación: `401` → clave mal copiada; `402`/`403` → sin créditos de prueba;
lista vacía → la cuenta no tiene acceso a esos modelos.

---

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `docker: error during connect` | Docker Desktop no está corriendo | Ábrelo y espera "Engine running" |
| `Access denied` al usar Docker | Usuario fuera del grupo `docker-users` | `net localgroup docker-users $env:USERNAME /add` (admin) y reiniciar sesión |
| `Connection refused` en `localhost:8000` | El contenedor aún arranca o falló | `docker compose logs --tail 50` |
| `TesseractNotFoundError` en local | Tesseract fuera del `PATH` | Reinstalar marcando la opción de `PATH`, o definir `pytesseract.tesseract_cmd` |
| `OSError: [E050] Can't find model 'es_core_news_md'` | Modelo no descargado | `python -m spacy download es_core_news_md` |
| La imagen pesa ≈ 2 GB | Tesseract, spaCy, Presidio y OpenCV; es el tamaño esperado | No es un error; revisar `.dockerignore` solo si crece de forma anómala |
| WSL2 consume toda la RAM | Sin límite configurado | Crear `%USERPROFILE%\.wslconfig` (ver abajo) |
| `activate.ps1 cannot be loaded` | Política de ejecución | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

Límite de memoria para WSL2 (**opcional**; si quieres acotar la RAM que usa Docker
Desktop, crea `C:\Users\<usuario>\.wslconfig`):

```ini
[wsl2]
memory=6GB
processors=4
swap=2GB
```

Se aplica con `wsl --shutdown` y reabriendo Docker Desktop.

---

## Etapa futura: publicación con HTTPS (no implementada)

El prototipo corre en `localhost` y **no** se publica en internet. Cuando exista un
dominio propio, la ruta prevista es:

1. Servidor con Docker y el mismo `docker-compose.yml`.
2. **Caddy** como proxy inverso delante de VerifIA; obtiene y renueva el certificado
   TLS de Let's Encrypt de forma automática.
3. Publicar el puerto 443 y dejar el 8000 solo en la red interna.
4. Añadir limitación de frecuencia por IP, revisar los avisos de privacidad y definir
   retención de registros (hoy no se registra contenido).

Esto queda fuera del alcance actual porque un despliegue público exige HTTPS,
dominio, monitoreo y un análisis de protección de datos que el prototipo local no
necesita.
