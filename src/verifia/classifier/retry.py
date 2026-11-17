"""Reintentos con espera exponencial para las llamadas al LLM (Fase 5).

La API de NVIDIA devuelve errores que no dependen del mensaje enviado: ``503``
(*content safety screening temporarily unavailable*), ``429`` por límite de
frecuencia, ``5xx`` de la pasarela y timeouts. En las pruebas del 17/11/2026
MiniMax también devolvió ``400 Invalid request`` de forma esporádica con un
cuerpo de petición que funcionaba en la llamada siguiente, por lo que ese estado
se reintenta un número acotado de veces.

El módulo no añade dependencias: usa ``time.sleep`` y lee la configuración de
``LLM_MAX_REINTENTOS`` (intentos totales, mínimo 1) y ``LLM_RETRY_BASE_S``
(espera inicial; se duplica en cada reintento, con un pequeño jitter).
"""

from __future__ import annotations

import logging
import os
import random
import time
from collections.abc import Callable
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError

T = TypeVar("T")

#: Estados HTTP que se consideran transitorios. El 400 se incluye por la
#: evidencia de MiniMax; los errores de validación propios se detectan antes
#: de llamar a la API (Pydantic) y no llegan aquí.
ESTADOS_REINTENTABLES = frozenset({400, 408, 409, 429, 500, 502, 503, 504})

#: Tope de la espera entre intentos, para no bloquear una petición indefinidamente.
ESPERA_MAXIMA_S = 20.0

_LOGGER = logging.getLogger(__name__)


def _entero_env(nombre: str, defecto: int, minimo: int) -> int:
    try:
        valor = int(os.getenv(nombre, str(defecto)))
    except ValueError:
        valor = defecto
    return max(minimo, valor)


def _flotante_env(nombre: str, defecto: float, minimo: float) -> float:
    try:
        valor = float(os.getenv(nombre, str(defecto)))
    except ValueError:
        valor = defecto
    return max(minimo, valor)


def es_reintentable(exc: BaseException) -> bool:
    """Indica si el error es transitorio y conviene repetir la llamada."""
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in ESTADOS_REINTENTABLES
    return False


def con_reintentos(llamar: Callable[[], T], *, descripcion: str = "llamada al LLM") -> T:
    """Ejecuta ``llamar`` y repite los fallos transitorios con espera creciente.

    ``llamar`` debe ser una función sin argumentos que realice una sola petición
    (por ejemplo, ``lambda: cliente.chat.completions.create(...)``). Los errores
    no reintentables (404, 401, JSON inválido, etc.) se propagan de inmediato.
    """
    intentos = _entero_env("LLM_MAX_REINTENTOS", 3, 1)
    base = _flotante_env("LLM_RETRY_BASE_S", 2.0, 0.0)

    numero = 0
    while True:
        numero += 1
        try:
            return llamar()
        except Exception as exc:  # noqa: BLE001 - se filtra con es_reintentable
            if numero >= intentos or not es_reintentable(exc):
                raise
            espera = min(ESPERA_MAXIMA_S, base * 2 ** (numero - 1))
            espera += random.uniform(0, base / 2)
            _LOGGER.warning(
                "%s falló (intento %d/%d): %s: %s. Reintento en %.1f s",
                descripcion,
                numero,
                intentos,
                type(exc).__name__,
                str(exc)[:200],
                espera,
            )
            time.sleep(espera)
