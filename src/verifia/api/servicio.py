"""Estado del servicio de análisis (Fase 7).

Carga una sola vez por proceso:

* el modelo calibrado del Nivel 1 (``models/nivel1.joblib``);
* el few-shot del Nivel 2 (``models/fewshot_nivel2.json``, horneado por
  ``scripts/generar_fewshot.py`` para que el contenedor no necesite ``data/``);
* el cliente del LLM, **solo si** hay ``NVIDIA_API_KEY``; sin clave, toda la
  zona gris cae al fallback del Nivel 1 con aviso de análisis parcial (regla 8).

Expone las dos operaciones que consume la API:

* :func:`extraer_texto_imagen` — OCR local de una captura (la imagen nunca
  viaja a ningún servicio, memoria §5);
* :func:`analizar_texto` — sanitización → cascada → explicación.

Ninguna función registra el texto ni la imagen del usuario (invariante 3 de
la skill: sin logs de contenido).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from joblib import load as cargar_joblib

from verifia import __version__
from verifia.classifier.cascade import CascadeVerifIA
from verifia.classifier.level2_llm import cliente_si_hay_clave
from verifia.ocr import pipeline as pipeline_ocr
from verifia.sanitizer.engine import sanitizar
from verifia.schemas import RespuestaAnalisis, RespuestaOCR

_LOGGER = logging.getLogger(__name__)

#: Raíz del proyecto: ``src/verifia/api/servicio.py`` → 3 niveles arriba.
RAIZ = Path(__file__).resolve().parents[3]
MODELOS = RAIZ / "models"

#: Traducción de los códigos internos del OCR a frases para la persona usuaria.
_ADVERTENCIAS_OCR: dict[str, str] = {
    "texto_muy_corto": "Se extrajo poco texto: revisa que la captura esté completa.",
    "confianza_baja": "La lectura de la imagen no fue muy segura; revisa el texto.",
}

#: La sanitización se serializa: el analizador de Presidio + spaCy es un
#: recurso compartido del proceso y FastAPI atiende los endpoints síncronos
#: en un grupo de hilos.
_candado_sanitizador = threading.Lock()


@dataclass
class EstadoServicio:
    """Componentes cargados del pipeline, listos para atender peticiones."""

    version: str
    modelo: Any
    ejemplos: list[dict[str, str]]
    cliente: Any | None
    cascada: CascadeVerifIA = field(init=False)

    def __post_init__(self) -> None:
        self.cascada = CascadeVerifIA(
            self.modelo, self.cliente, ejemplos=self.ejemplos
        )


def cargar_estado() -> EstadoServicio:
    """Carga modelo, few-shot y cliente del LLM (si hay clave).

    En Docker las variables ya llegan por ``env_file``; en la ejecución con
    venv se leen de ``.env`` (idempotente, como en los scripts de la Fase 5).
    """
    load_dotenv(RAIZ / ".env")

    # Invariante 3 de la skill: ningún log contiene el texto del usuario.
    # Presidio registra en DEBUG los contextos de las coincidencias, que
    # incluyen fragmentos del mensaje (incluso la PII detectada): se fija su
    # nivel en WARNING para que el invariante se cumpla a cualquier
    # configuración de logging.
    logging.getLogger("presidio_analyzer").setLevel(logging.WARNING)

    modelo = cargar_joblib(MODELOS / "nivel1.joblib")

    ejemplos: list[dict[str, str]] = []
    ruta_fewshot = MODELOS / "fewshot_nivel2.json"
    if ruta_fewshot.exists():
        ejemplos = json.loads(ruta_fewshot.read_text(encoding="utf-8"))
    else:
        _LOGGER.warning(
            "Falta models/fewshot_nivel2.json; el Nivel 2 trabajará sin "
            "ejemplos en el prompt."
        )

    cliente = cliente_si_hay_clave()
    if cliente is None:
        _LOGGER.warning(
            "Sin NVIDIA_API_KEY: la zona gris se resuelve con el Nivel 1 y "
            "aviso de análisis parcial (regla 8)."
        )

    return EstadoServicio(
        version=__version__,
        modelo=modelo,
        ejemplos=ejemplos,
        cliente=cliente,
    )


def analizar_texto(estado: EstadoServicio, texto: str) -> RespuestaAnalisis:
    """Sanitiza y clasifica un mensaje revisado por la persona usuaria.

    Es el paso final del flujo de 4 pasos: el texto ya pasó por la revisión
    humana (paso 2), pero **aún así se sanitiza aquí** — es la última barrera
    antes de cualquier clasificador (regla 1).
    """
    with _candado_sanitizador:
        limpio = sanitizar(texto)

    resultado = estado.cascada.analizar(
        limpio.texto, limpio.marcadores, limpio.rasgos_enlace
    )
    return RespuestaAnalisis(
        **resultado.model_dump(), texto_analizado=limpio.texto
    )


def extraer_texto_imagen(estado: EstadoServicio, datos: bytes) -> RespuestaOCR:
    """Extrae el borrador de texto de una captura (paso 1 → paso 2).

    Los límites (5 MB, 4000 px, 12 MP) los aplica la Fase 4; los errores de
    OCR viajan con su código HTTP ya declarado. El servicio no se usa para
    clasificar: el análisis ocurre después, con el texto corregido.
    """
    del estado  # el OCR es local y no depende del modelo; firma uniforme
    borrador = pipeline_ocr.extraer_texto(datos)
    advertencias = [
        _ADVERTENCIAS_OCR.get(codigo, codigo) for codigo in borrador.advertencias
    ]
    return RespuestaOCR(
        texto_extraido=borrador.texto,
        confianza=borrador.confianza,
        ancho=borrador.ancho,
        alto=borrador.alto,
        advertencias=advertencias,
    )


__all__ = [
    "EstadoServicio",
    "analizar_texto",
    "cargar_estado",
    "extraer_texto_imagen",
]
