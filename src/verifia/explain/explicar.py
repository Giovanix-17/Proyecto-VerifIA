"""Orquestador de la explicabilidad (Fase 6).

Recibe un dictamen ya calculado y lo traduce a semáforo, resumen, señales y
recomendaciones. No recalcula la puntuación ni la tipología: eso es
responsabilidad de la cascada (Fase 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from verifia.explain.catalogo import (
    ADVERTENCIA_PARCIAL,
    AVISO,
    recomendaciones,
)
from verifia.explain.resumen import construir_resumen
from verifia.explain.semaforo import semaforo
from verifia.explain.senales import senales_nivel1, senales_nivel2
from verifia.schemas import Explicacion, Senal


def explicar(
    *,
    texto: str,
    tipologia: str,
    puntuacion: int,
    modelo: Any | None = None,
    senales_llm: Sequence[Senal] | None = None,
    fuente: str = "nivel_1",
    advertencias: Sequence[str] = (),
) -> Explicacion:
    """Convierte el dictamen en una explicación lista para el usuario.

    ``senales_llm`` se pasa solo cuando el dictamen viene del Nivel 2; en ese
    caso se usan sus señales ya verificadas. En Nivel 1 o fallback se extraen
    términos del modelo. El aviso orientativo se añade siempre, y el fallback
    incorpora además la advertencia de análisis parcial.
    """
    datos = semaforo(puntuacion)
    if senales_llm is not None:
        senales = senales_nivel2(texto, senales_llm)
    else:
        senales = senales_nivel1(texto, modelo, tipologia, puntuacion)

    avisos = list(advertencias)
    if fuente == "nivel_1_fallback" and ADVERTENCIA_PARCIAL not in avisos:
        avisos.append(ADVERTENCIA_PARCIAL)

    return Explicacion(
        estado=datos["estado"],
        nivel_riesgo=datos["nivel_riesgo"],
        titulo=datos["titulo"],
        icono=datos["icono"],
        descripcion=datos["descripcion"],
        accion=datos["accion"],
        resumen_legible=construir_resumen(tipologia, senales),
        senales_alerta=senales,
        recomendaciones=recomendaciones(tipologia),
        advertencias=avisos,
        aviso=AVISO,
    )
