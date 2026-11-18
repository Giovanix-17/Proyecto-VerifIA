"""Contrato de salida del módulo de sanitización.

Ningún objeto de este módulo es reversible: no se guarda el valor original ni
una tabla de equivalencias (regla 2 de la memoria).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RasgoEnlace(BaseModel):
    """Rasgos estructurales de un enlace, calculados sin conservar la URL.

    Estos rasgos alimentan al Nivel 1 como características numéricas
    (regla 4 de la memoria); nunca se concatenan al texto sanitizado.
    """

    host: str = Field(description="Host registrable que queda en el marcador.")
    es_acortador: bool = False
    ip_literal: bool = False
    num_subdominios: int = 0
    tld_sospechoso: bool = False
    guiones_en_host: int = 0
    longitud_host: int = 0
    tiene_puerto: bool = False

    def como_dict(self) -> dict[str, Any]:
        """Devuelve el rasgo como diccionario serializable."""
        return self.model_dump()


class TextoSanitizado(BaseModel):
    """Resultado de sanitizar un mensaje.

    ``texto`` solo contiene los marcadores tipificados; ``marcadores`` cuenta
    cuántas veces aparece cada uno. No hay forma de recuperar los valores
    originales.
    """

    texto: str
    marcadores: dict[str, int] = Field(default_factory=dict)
    rasgos_enlace: list[RasgoEnlace] = Field(default_factory=list)
    entidades: int = 0
