"""Sanitización de datos personales (Fase 3, OE1).

Uso::

    from verifia.sanitizer import sanitizar

    resultado = sanitizar("Mi teléfono es 55 1234 5678")
    resultado.texto  # "Mi teléfono es [TELEFONO]"

El módulo nunca almacena el texto original ni crea una tabla reversible.
"""

from verifia.sanitizer.engine import (
    ENTIDAD_A_MARCADOR,
    ErrorSanitizacion,
    obtener_analizador,
    sanitizar,
)
from verifia.sanitizer.models import RasgoEnlace, TextoSanitizado

__all__ = [
    "ENTIDAD_A_MARCADOR",
    "ErrorSanitizacion",
    "RasgoEnlace",
    "TextoSanitizado",
    "obtener_analizador",
    "sanitizar",
]
