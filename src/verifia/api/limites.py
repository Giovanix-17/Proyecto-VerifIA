"""Límite de frecuencia en memoria, por IP (Fase 7).

Ventana deslizante por cliente, **sin Redis ni persistencia** (memoria §4 y
skill ``verifia-api-docker``): el estado vive solo en el proceso y se reinicia
al reiniciar el contenedor. Las claves inactivas se podan para que la
estructura no crezca sin control.

Valores configurables por entorno (``.env``):

* ``RATE_LIMIT_MAX`` — peticiones permitidas por ventana (10 por defecto).
* ``RATE_LIMIT_VENTANA_S`` — tamaño de la ventana en segundos (60 por defecto).
"""

from __future__ import annotations

import math
import os
import time
from collections import deque

#: Número de IPs con historial a partir del cual se poda la tabla.
TOPE_TABLA = 512


class LimiteFrecuencia:
    """Contador de peticiones por clave (IP) con ventana deslizante."""

    def __init__(self, maximo: int = 10, ventana_s: float = 60.0) -> None:
        self.maximo = max(1, int(maximo))
        self.ventana_s = max(1.0, float(ventana_s))
        self._registro: dict[str, deque[float]] = {}

    @classmethod
    def desde_entorno(cls) -> LimiteFrecuencia:
        """Construye el limitador con los valores de las variables de entorno."""
        try:
            maximo = int(os.getenv("RATE_LIMIT_MAX", "10"))
            ventana = float(os.getenv("RATE_LIMIT_VENTANA_S", "60"))
        except ValueError:
            maximo, ventana = 10, 60.0
        return cls(maximo=maximo, ventana_s=ventana)

    def verificar(self, clave: str) -> tuple[bool, float]:
        """Registra la petición de ``clave`` y decide si pasa.

        Devuelve ``(permitido, espera_s)``: ``espera_s`` es 0.0 cuando la
        petición pasa y los segundos que faltan para reintentar cuando se
        bloquea (valor para la cabecera ``Retry-After``).
        """
        ahora = time.monotonic()
        peticiones = self._registro.setdefault(clave, deque())

        while peticiones and ahora - peticiones[0] >= self.ventana_s:
            peticiones.popleft()

        if len(peticiones) >= self.maximo:
            espera = self.ventana_s - (ahora - peticiones[0])
            return False, max(0.0, espera)

        peticiones.append(ahora)
        if len(self._registro) > TOPE_TABLA:
            self._podar(ahora)
        return True, 0.0

    def _podar(self, ahora: float) -> None:
        """Descarta las claves sin actividad dentro de la ventana."""
        vivas = [
            clave
            for clave, peticiones in self._registro.items()
            if peticiones and ahora - peticiones[-1] < self.ventana_s
        ]
        self._registro = {clave: self._registro[clave] for clave in vivas}


def espera_redondeada(segundos: float) -> int:
    """Segundos mínimos que cabe en la cabecera ``Retry-After`` (entero ≥ 1)."""
    return max(1, math.ceil(segundos))
