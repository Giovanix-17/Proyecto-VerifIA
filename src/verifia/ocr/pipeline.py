"""Pipeline imagen → texto de VerifIA (Fase 4).

    imagen → validar límites → preprocesar → Tesseract(spa) → posprocesar
           → mostrar texto editable → sanitizar → clasificar

La imagen nunca sale del equipo. El resultado es un borrador que el usuario
corrige antes del análisis; el pipeline no clasifica ni decide riesgo.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from verifia.ocr.errors import ErrorOCR, TextoInsuficiente
from verifia.ocr.extraccion import LineaOCR, reconocer_lineas
from verifia.ocr.models import OpcionesOCR, TextoOCR
from verifia.ocr.posprocesamiento import posprocesar
from verifia.ocr.preprocesamiento import preprocesar
from verifia.ocr.validacion import validar_imagen

if TYPE_CHECKING:
    from verifia.sanitizer import TextoSanitizado

_ADVERTENCIA_CORTO = "texto_muy_corto"
_ADVERTENCIA_CONFIANZA = "confianza_baja"
UMBRAL_CONFIANZA_BAJA = 60.0
MINIMO_TEXTO_COMODO = 20


def _confianza_global(lineas: list[LineaOCR]) -> float | None:
    pares = [
        (linea.confianza, len(linea.texto))
        for linea in lineas
        if linea.confianza is not None and linea.texto
    ]
    peso = sum(largo for _, largo in pares)
    if not peso:
        return None
    return sum(conf * largo for conf, largo in pares) / peso


def extraer_texto(
    fuente: bytes | bytearray | memoryview | str | Path,
    opciones: OpcionesOCR | None = None,
) -> TextoOCR:
    """Extrae un borrador de texto de una captura PNG/JPEG.

    Lanza :class:`ErrorOCR` (con ``codigo_http``) si la imagen no cumple los
    límites, no decodifica, falta Tesseract/spa o no hay texto suficiente.
    """
    opciones = opciones or OpcionesOCR()
    validada = validar_imagen(fuente)
    preparada = preprocesar(validada.datos, validada, opciones)
    lineas = reconocer_lineas(preparada.binaria, opciones)
    texto = posprocesar(lineas, opciones)
    utiles = sum(1 for caracter in texto if caracter.isalnum())

    if utiles < opciones.minimo_caracteres:
        raise TextoInsuficiente(
            "No se pudo extraer texto suficiente de la imagen. "
            "Intenta con una captura más nítida o completa."
        )

    confianza = _confianza_global(lineas)
    advertencias: list[str] = []
    if utiles < MINIMO_TEXTO_COMODO:
        advertencias.append(_ADVERTENCIA_CORTO)
    if confianza is not None and confianza < UMBRAL_CONFIANZA_BAJA:
        advertencias.append(_ADVERTENCIA_CONFIANZA)

    return TextoOCR(
        texto=texto,
        caracteres_utiles=utiles,
        confianza=round(confianza, 2) if confianza is not None else None,
        modo=preparada.modo,
        ancho=validada.ancho,
        alto=validada.alto,
        operaciones=preparada.operaciones,
        advertencias=tuple(advertencias),
    )


def extraer_y_sanitizar(
    fuente: bytes | bytearray | memoryview | str | Path,
    opciones: OpcionesOCR | None = None,
) -> tuple[TextoOCR, TextoSanitizado]:
    """Encadena OCR y sanitización; el texto OCR nunca viaja sin enmascarar."""
    from verifia.sanitizer import sanitizar

    borrador = extraer_texto(fuente, opciones)
    return borrador, sanitizar(borrador.texto)


__all__ = [
    "ErrorOCR",
    "OpcionesOCR",
    "TextoOCR",
    "extraer_texto",
    "extraer_y_sanitizar",
]
