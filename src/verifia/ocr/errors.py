"""Errores del módulo OCR (Fase 4).

Cada error declara el código HTTP con el que la API debe responder, para que
la Fase 7 no tenga que adivinar el tipo de falla.
"""

from __future__ import annotations


class ErrorOCR(RuntimeError):
    """Falla controlada del pipeline de OCR."""

    codigo_http = 422


class FormatoNoSoportado(ErrorOCR):
    """El archivo no es PNG ni JPEG (verificado por magic bytes)."""

    codigo_http = 422


class LimiteExcedido(ErrorOCR):
    """La imagen supera un límite de entrada; no se reescala ni se recorta."""

    codigo_http = 413


class ImagenInvalida(ErrorOCR):
    """El archivo no decodifica o está truncado."""

    codigo_http = 422


class OCRNoDisponible(ErrorOCR):
    """Falta Tesseract, el paquete ``spa`` o el binario no responde."""

    codigo_http = 503


class TextoInsuficiente(ErrorOCR):
    """El OCR no recuperó texto útil; se debe pedir otra captura."""

    codigo_http = 422
