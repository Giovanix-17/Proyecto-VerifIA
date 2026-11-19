"""Explicabilidad y recomendaciones (Fase 6).

Uso::

    from verifia.explain import explicar

    explicacion = explicar(
        texto="Su cuenta será bloqueada hoy. Ingrese su código.",
        tipologia="suplantacion_bancaria",
        puntuacion=90,
        modelo=modelo_nivel1,
    )
    explicacion.estado       # "rojo"
    explicacion.resumen_legible
    explicacion.recomendaciones

Semáforo de riesgo, señales de alerta sobre el texto sanitizado y catálogo de
recomendaciones por tipología. El módulo no decide: recibe tipología y
puntuación ya calculadas.
"""

from verifia.explain.catalogo import (
    ADVERTENCIA_PARCIAL,
    AVISO,
    CONSECUENCIAS,
    GENERALES,
    NUMERO_EMERGENCIAS,
    POR_TIPOLOGIA,
    TIPOLOGIA_LLANA,
    consecuencia,
    recomendaciones,
    tipologia_llana,
)
from verifia.explain.explicar import explicar
from verifia.explain.resumen import construir_resumen
from verifia.explain.semaforo import ESTADOS, semaforo
from verifia.explain.senales import (
    MAX_SENALES,
    categoria_de,
    extraer_terminos,
    localizar_frase,
    senales_desde_marcadores,
    senales_desde_terminos,
    senales_nivel1,
    senales_nivel2,
)

__all__ = [
    "ADVERTENCIA_PARCIAL",
    "AVISO",
    "CONSECUENCIAS",
    "ESTADOS",
    "GENERALES",
    "MAX_SENALES",
    "NUMERO_EMERGENCIAS",
    "POR_TIPOLOGIA",
    "TIPOLOGIA_LLANA",
    "categoria_de",
    "consecuencia",
    "construir_resumen",
    "explicar",
    "extraer_terminos",
    "localizar_frase",
    "recomendaciones",
    "semaforo",
    "senales_desde_marcadores",
    "senales_desde_terminos",
    "senales_nivel1",
    "senales_nivel2",
    "tipologia_llana",
]
