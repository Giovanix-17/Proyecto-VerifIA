"""Semáforo de riesgo de tres estados (Fase 6, §8.5).

El estado se deriva **siempre de la puntuación final** (0–100), nunca del
``nivel_riesgo`` que haya propuesto el LLM. Cada estado incluye texto e icono:
el color no es el único canal (WCAG 2.1).
"""

from __future__ import annotations

from typing import TypedDict

from verifia.schemas import EstadoSemaforo, estado_de_puntuacion


class DatosSemaforo(TypedDict):
    estado: EstadoSemaforo
    nivel_riesgo: str
    titulo: str
    icono: str
    descripcion: str
    accion: str


#: Catálogo cerrado de los tres estados. Los textos son constantes y se
#: prueban con snapshots para que no cambien sin revisión explícita.
ESTADOS: dict[EstadoSemaforo, DatosSemaforo] = {
    "verde": {
        "estado": "verde",
        "nivel_riesgo": "bajo",
        "titulo": "Riesgo bajo",
        "icono": "✔",
        "descripcion": "No se detectaron señales claras de fraude.",
        "accion": "Puede continuar, con precaución.",
    },
    "amarillo": {
        "estado": "amarillo",
        "nivel_riesgo": "medio",
        "titulo": "Riesgo medio",
        "icono": "⚠",
        "descripcion": "Hay señales que conviene verificar.",
        "accion": "Verifique por un canal oficial antes de actuar.",
    },
    "rojo": {
        "estado": "rojo",
        "nivel_riesgo": "alto",
        "titulo": "Riesgo alto",
        "icono": "⛔",
        "descripcion": "Este mensaje tiene señales fuertes de fraude.",
        "accion": "No actúe conforme al mensaje.",
    },
}


def semaforo(puntuacion: int) -> DatosSemaforo:
    """Devuelve el estado, título, icono, descripción y acción sugerida."""
    return ESTADOS[estado_de_puntuacion(puntuacion)]
