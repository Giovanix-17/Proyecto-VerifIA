"""Cascada — umbral de confianza, puntuación y fallback (Fase 5, §8.6).

Regla de decisión:

1. Si ``P(máxima) >= UMBRAL`` (0.80 inicial) → se resuelve en el Nivel 1.
   ``puntuacion = round(100 × (1 − P(legítimo)))``.
2. Zona gris → se llama al Nivel 2:
   * JSON válido → ``puntuacion = max(puntuacion_LLM, puntuacion_nivel1)``
     (ante discrepancia gana el **riesgo mayor**, regla 11) y se marca
     ``discrepancia_niveles``.
   * JSON inválido, API caída o sin clave → ``puntuacion_nivel1`` + aviso
     visible de *análisis parcial* (regla 8), ``fuente = nivel_1_fallback``.

El ``nivel_riesgo`` mostrado SIEMPRE se deriva de la puntuación final (§8.5);
el semáforo y las recomendaciones se terminan de construir en la Fase 6.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from verifia.classifier import level1
from verifia.classifier.level2_llm import FalloLLM, consultar, dictamen_con_puntuacion_final
from verifia.schemas import (
    ResultadoClasificacion,
    banda_de_riesgo,
)

TEXTO_VACIO = "El mensaje está vacío; no hay nada que clasificar."

ADVERTENCIA_PARCIAL = "análisis parcial: el modelo avanzado no estuvo disponible."
AVISO_ORIENTATIVO = (
    "resultado orientativo: no sustituye tu criterio ni la denuncia formal "
    "ante las autoridades."
)


def umbral_confianza() -> float:
    """Umbral de la cascada (0.80 inicial; ajustado una vez en validación)."""
    try:
        return float(os.getenv("UMBRAL_CONFIANZA", "0.80"))
    except ValueError:
        return 0.80


class CascadeVerifIA:
    """Orquesta Nivel 1 y Nivel 2 sobre un texto **ya sanitizado**.

    ``modelo`` es el clasificador calibrado del Nivel 1 (acepta la lista de
    registros de :func:`verifia.classifier.level1.preparar_registro`).
    ``cliente`` es el cliente de la API (o ``None`` para operar solo con el
    Nivel 1: toda zona gris cae al fallback). ``ejemplos`` es el few-shot de
    train para el prompt del Nivel 2.
    """

    def __init__(
        self,
        modelo: Any,
        cliente: Any | None = None,
        ejemplos: list[dict] | None = None,
        *,
        llamar_llm: bool = True,
    ) -> None:
        self.modelo = modelo
        self.cliente = cliente
        self.ejemplos = ejemplos or []
        self.llamar_llm = llamar_llm
        self.umbral = umbral_confianza()

    # ------------------------------------------------------------------ #
    def analizar(
        self,
        texto: str,
        marcadores: dict[str, int] | None = None,
        rasgos_enlace: Iterable | None = None,
    ) -> ResultadoClasificacion:
        """Clasifica un mensaje sanitizado y devuelve la respuesta del sistema.

        El texto debe venir enmascarado (marcadores incluidos); la
        responsabilidad de sanitizar es del módulo anterior del pipeline
        (regla 1). Ante texto vacío se devuelve un dictamen trivial verde.
        """
        if not texto.strip():
            return ResultadoClasificacion(
                tipologia="legitimo",
                nivel_riesgo="bajo",
                puntuacion=0,
                senales_alerta=[],
                justificacion="",
                resumen_legible=TEXTO_VACIO,
                recomendaciones=[],
                advertencias=[],
                fuente_diccionario="nivel_1",
                escalado_a_llm=False,
                discrepancia_niveles=False,
                detalle={},
            )
        registro = level1.preparar_registro(texto, marcadores, rasgos_enlace)
        probabilidades = self.modelo.predict_proba([registro])[0]
        p_nivel1 = level1.puntuacion_nivel1(probabilidades)
        prob_maxima = float(probabilidades.max())
        clases = list(self.modelo.classes_)
        tipologia_nivel1 = clases[int(probabilidades.argmax())]

        advertencias: list[str] = [AVISO_ORIENTATIVO]
        detalle: dict[str, Any] = {
            "prob_maxima": round(prob_maxima, 4),
            "puntuacion_nivel1": p_nivel1,
            "tipologia_nivel1": tipologia_nivel1,
            "umbral": self.umbral,
        }

        if prob_maxima >= self.umbral:
            return self._resultado_nivel1(
                tipologia_nivel1, p_nivel1, [], detalle, advertencias, escalado=False
            )

        # Zona gris: el LLM se consulta solo si está disponible.
        if not self.llamar_llm or self.cliente is None:
            advertencias.append(ADVERTENCIA_PARCIAL)
            detalle["motivo_fallback"] = "sin_llm"
            return self._resultado_nivel1(
                tipologia_nivel1, p_nivel1, [], detalle, advertencias, escalado=True
            )

        try:
            dictamen, meta = consultar(
                self.cliente, texto, ejemplos=self.ejemplos
            )
        except FalloLLM as exc:
            advertencias.append(ADVERTENCIA_PARCIAL)
            detalle["motivo_fallback"] = exc.motivo
            return self._resultado_nivel1(
                tipologia_nivel1, p_nivel1, [], detalle, advertencias, escalado=True
            )

        puntuacion = max(int(dictamen.puntuacion), p_nivel1)
        discrepancia = int(dictamen.puntuacion) < puntuacion
        detalle["llm"] = meta
        detalle["puntuacion_llm"] = int(dictamen.puntuacion)
        final = dictamen_con_puntuacion_final(dictamen, puntuacion)
        return ResultadoClasificacion(
            tipologia=final.tipologia,
            nivel_riesgo=banda_de_riesgo(puntuacion),
            puntuacion=puntuacion,
            senales_alerta=final.senales_alerta,
            justificacion=final.justificacion,
            resumen_legible=_resumen(final.tipologia, puntuacion),
            recomendaciones=[],
            advertencias=advertencias,
            fuente_diccionario="nivel_2",
            escalado_a_llm=True,
            discrepancia_niveles=discrepancia,
            detalle=detalle,
        )

    # ------------------------------------------------------------------ #
    def _resultado_nivel1(
        self,
        tipologia: str,
        puntuacion: int,
        senales: list,
        detalle: dict[str, Any],
        advertencias: list[str],
        *,
        escalado: bool,
    ) -> ResultadoClasificacion:
        fuente = "nivel_1" if not escalado else "nivel_1_fallback"
        return ResultadoClasificacion(
            tipologia=tipologia,
            nivel_riesgo=banda_de_riesgo(puntuacion),
            puntuacion=puntuacion,
            senales_alerta=senales,
            justificacion="Clasificado por el filtro local del Nivel 1.",
            resumen_legible=_resumen(tipologia, puntuacion),
            recomendaciones=[],
            advertencias=advertencias,
            fuente_diccionario=fuente,
            escalado_a_llm=escalado,
            discrepancia_niveles=False,
            detalle=detalle,
        )


def _resumen(tipologia: str, puntuacion: int) -> str:
    """Resumen breve en lenguaje sencillo (la Fase 6 lo enriquecerá)."""
    banda = banda_de_riesgo(puntuacion)
    etiqueta = tipologia.replace("_", " ")
    return f"Riesgo {banda} ({puntuacion}/100). El mensaje se clasifica como: {etiqueta}."
