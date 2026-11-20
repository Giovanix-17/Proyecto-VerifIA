"""Errores HTTP consistentes de la API (Fase 7).

Toda respuesta de error usa el mismo cuerpo JSON::

    {"detail": "<mensaje claro>", "codigo": "<codigo_estable>"}

Reglas de la skill ``verifia-api-docker``: mensajes en lenguaje claro, sin
trazas internas, sin rutas del sistema y sin contenido del usuario.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from verifia.ocr.errors import (
    ErrorOCR,
    FormatoNoSoportado,
    ImagenInvalida,
    LimiteExcedido,
    OCRNoDisponible,
    TextoInsuficiente,
)
from verifia.sanitizer.engine import ErrorSanitizacion


class ErrorAPI(Exception):
    """Error controlado con código estable y mensaje para la persona usuaria."""

    def __init__(
        self,
        estado: int,
        codigo: str,
        mensaje: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(mensaje)
        self.estado = estado
        self.codigo = codigo
        self.mensaje = mensaje
        self.headers = headers or {}


def _respuesta(
    estado: int, codigo: str, mensaje: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=estado,
        content={"detail": mensaje, "codigo": codigo},
        headers=headers or {},
    )


#: Clase de error OCR → (estado HTTP, código estable). Los mensajes ya los
#: redacta el módulo OCR (Fase 4); aquí solo se traducen a HTTP.
ESTADOS_OCR: dict[type[ErrorOCR], tuple[int, str]] = {
    LimiteExcedido: (413, "imagen_demasiado_grande"),
    FormatoNoSoportado: (422, "formato_no_soportado"),
    ImagenInvalida: (422, "imagen_invalida"),
    OCRNoDisponible: (503, "ocr_no_disponible"),
    TextoInsuficiente: (422, "texto_insuficiente"),
}


def _mapear_validacion(exc: RequestValidationError) -> tuple[str, str] | None:
    """Traduce los errores de Pydantic a códigos claros cuando aplica."""
    for error in exc.errors():
        ubicacion = tuple(error.get("loc", ()))
        tipo = error.get("type", "")
        if "texto" in ubicacion:
            if tipo == "string_too_long":
                return (
                    "texto_muy_largo",
                    "El mensaje es demasiado largo (máximo 10 000 caracteres).",
                )
            if tipo == "string_too_short":
                return ("texto_vacio", "Escribe el mensaje que quieres verificar.")
    return None


def instalar_manejadores(app: FastAPI) -> None:
    """Registra los manejadores de excepciones de toda la API."""

    @app.exception_handler(ErrorAPI)
    async def _error_api(_request: Request, exc: ErrorAPI) -> JSONResponse:
        return _respuesta(exc.estado, exc.codigo, exc.mensaje, exc.headers)

    @app.exception_handler(ErrorOCR)
    async def _error_ocr(_request: Request, exc: ErrorOCR) -> JSONResponse:
        estado, codigo = ESTADOS_OCR.get(type(exc), (422, "error_ocr"))
        return _respuesta(estado, codigo, str(exc))

    @app.exception_handler(ErrorSanitizacion)
    async def _error_sanitizacion(
        _request: Request, _exc: ErrorSanitizacion
    ) -> JSONResponse:
        # Falla cerrada: si la sanitización no está disponible, el texto no se
        # clasifica (regla 1). Nunca se devuelve un dictamen "sin enmascarar".
        return _respuesta(
            503,
            "servicio_no_disponible",
            "El servicio no está disponible en este momento. Inténtalo más tarde.",
        )

    @app.exception_handler(RequestValidationError)
    async def _entrada_invalida(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        mapeo = _mapear_validacion(exc)
        if mapeo is not None:
            return _respuesta(422, mapeo[0], mapeo[1])
        return _respuesta(422, "entrada_invalida", "Revisa los datos enviados.")

    @app.exception_handler(Exception)
    async def _error_interno(
        _request: Request, _exc: Exception
    ) -> JSONResponse:
        # Sin trazas ni detalles internos en la respuesta; la traza técnica la
        # registra el servidor, que no incluye contenido del usuario.
        detalles: dict[str, Any] = {
            "detail": "No se pudo completar el análisis. Inténtalo de nuevo.",
            "codigo": "error_interno",
        }
        return JSONResponse(status_code=500, content=detalles)
