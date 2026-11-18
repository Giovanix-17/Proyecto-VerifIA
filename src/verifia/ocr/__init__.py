"""OCR de capturas de pantalla (Fase 4, OE2).

Uso::

    from verifia.ocr import extraer_texto, extraer_y_sanitizar

    borrador = extraer_texto("captura.png")
    borrador.texto  # texto editable que se muestra al usuario

``Tesseract`` con el paquete ``spa`` y OpenCV se ejecutan en local; la imagen
nunca se envía a un servicio externo.
"""

from verifia.ocr.errors import (
    ErrorOCR,
    FormatoNoSoportado,
    ImagenInvalida,
    LimiteExcedido,
    OCRNoDisponible,
    TextoInsuficiente,
)
from verifia.ocr.extraccion import disponibilidad
from verifia.ocr.models import OpcionesOCR, TextoOCR
from verifia.ocr.pipeline import extraer_texto, extraer_y_sanitizar

__all__ = [
    "ErrorOCR",
    "FormatoNoSoportado",
    "ImagenInvalida",
    "LimiteExcedido",
    "OCRNoDisponible",
    "OpcionesOCR",
    "TextoInsuficiente",
    "TextoOCR",
    "disponibilidad",
    "extraer_texto",
    "extraer_y_sanitizar",
]
