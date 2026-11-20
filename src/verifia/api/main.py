"""Servicio HTTP de VerifIA (Fase 7, OE4).

Endpoints (skill ``verifia-api-docker``):

* ``GET  /health``              — comprobación de vida (Docker / pytest).
* ``GET  /``                    — interfaz estática (``web/index.html``).
* ``POST /api/analizar/texto``  — texto (1–10 000 caracteres) → dictamen.
* ``POST /api/analizar/imagen`` — captura PNG/JPEG → borrador de texto OCR.

Flujo de imagen en dos llamadas: OCR → la persona corrige el texto →
``/api/analizar/texto``. La imagen nunca sale del equipo (§5) y el análisis
siempre pasa por sanitización (regla 1).

Invariantes: sin persistencia ni caché de resultados (regla 2), sin logs de
contenido, límite de frecuencia por IP en memoria, y sin ``NVIDIA_API_KEY``
la zona gris cae al fallback con aviso de análisis parcial (regla 8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from verifia import __version__
from verifia.api.errores import ErrorAPI, instalar_manejadores
from verifia.api.limites import LimiteFrecuencia, espera_redondeada
from verifia.api.servicio import (
    EstadoServicio,
    analizar_texto,
    cargar_estado,
    extraer_texto_imagen,
)
from verifia.schemas import RespuestaAnalisis, RespuestaOCR, SolicitudTexto

#: Carpeta del frontend estático (sin build, servida por este mismo servicio).
RAIZ_WEB = Path(__file__).resolve().parents[3] / "web"

#: 5 MB: techo de lectura del archivo subido, aplicado por fragmentos para no
#: cargar en memoria una petición gigante (el límite autoritativo es el de la
#: Fase 4, que valida bytes, lado mayor y megapíxeles).
LIMITE_IMAGEN_BYTES = 5 * 1024 * 1024
_FRAGMENTO = 1024 * 1024

app = FastAPI(
    title="VerifIA",
    description=(
        "Detección orientativa de fraude y extorsión digital en mensajes en "
        "español. Los mensajes se sanitizan y no se almacenan."
    ),
    version=__version__,
)
instalar_manejadores(app)

if RAIZ_WEB.exists():
    app.mount("/static", StaticFiles(directory=RAIZ_WEB), name="static")


# --------------------------------------------------------------------------- #
# Dependencias
# --------------------------------------------------------------------------- #
def _servicio(request: Request) -> EstadoServicio:
    """Estado del pipeline, cargado la primera vez que se necesita.

    La carga perezosa permite probar endpoints ligeros (health, errores de
    entrada) sin modelo y hace que el primer análisis tarde unos segundos
    más (carga de spaCy), igual que en las demás fases.
    """
    if not hasattr(request.app.state, "servicio"):
        request.app.state.servicio = cargar_estado()
    return request.app.state.servicio


def _limite(request: Request) -> None:
    """Límite de frecuencia por IP, en memoria (sin Redis)."""
    if not hasattr(request.app.state, "limite"):
        request.app.state.limite = LimiteFrecuencia.desde_entorno()
    limite: LimiteFrecuencia = request.app.state.limite
    cliente = request.client
    clave = cliente.host if cliente else "desconocida"
    permitido, espera = limite.verificar(clave)
    if not permitido:
        raise ErrorAPI(
            429,
            "demasiadas_solicitudes",
            "Estás enviando solicitudes muy rápido. Espera un momento e "
            "inténtalo de nuevo.",
            headers={"Retry-After": str(espera_redondeada(espera))},
        )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Comprobación de vida usada por el healthcheck de Docker y por pytest."""
    return {"status": "ok", "version": __version__}


@app.get("/", include_in_schema=False)
def inicio() -> FileResponse:
    """Sirve la interfaz estática (paso 1 del flujo de 4 pasos)."""
    ruta = RAIZ_WEB / "index.html"
    if not ruta.exists():
        raise ErrorAPI(
            404,
            "interfaz_no_disponible",
            "La interfaz no está disponible en esta instalación.",
        )
    return FileResponse(ruta, media_type="text/html")


@app.post(
    "/api/analizar/texto",
    response_model=RespuestaAnalisis,
    tags=["análisis"],
    summary="Analiza un mensaje de texto (paso 3 del flujo).",
)
def analizar(
    solicitud: SolicitudTexto,
    _limite: Annotated[None, Depends(_limite)],
    servicio: Annotated[EstadoServicio, Depends(_servicio)],
) -> RespuestaAnalisis:
    """Sanitiza el texto, lo clasifica y devuelve semáforo + recomendaciones."""
    if not solicitud.texto.strip():
        raise ErrorAPI(
            422, "texto_vacio", "Escribe el mensaje que quieres verificar."
        )
    return analizar_texto(servicio, solicitud.texto)


@app.post(
    "/api/analizar/imagen",
    response_model=RespuestaOCR,
    tags=["análisis"],
    summary="Extrae el texto de una captura para revisión (paso 1 → 2).",
)
async def analizar_imagen(
    _limite: Annotated[None, Depends(_limite)],
    servicio: Annotated[EstadoServicio, Depends(_servicio)],
    imagen: Annotated[
        UploadFile, File(description="Captura PNG o JPEG (≤ 5 MB, ≤ 4000 px).")
    ],
) -> RespuestaOCR:
    """Ejecuta el OCR local y devuelve el borrador editable.

    **No clasifica**: el análisis ocurre después, con ``/api/analizar/texto``
    y el texto corregido por la persona (§9 Fase 7, flujo de 4 pasos).
    """
    datos = bytearray()
    while fragmento := await imagen.read(_FRAGMENTO):
        datos.extend(fragmento)
        if len(datos) > LIMITE_IMAGEN_BYTES:
            raise ErrorAPI(
                413,
                "imagen_demasiado_grande",
                "La imagen supera 5 MB. Reduce su tamaño e inténtalo de nuevo.",
            )
    await imagen.close()
    if not datos:
        raise ErrorAPI(
            422, "imagen_vacia", "Selecciona una captura PNG o JPEG."
        )
    return extraer_texto_imagen(servicio, bytes(datos))
