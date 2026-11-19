"""Cascada — umbral de confianza, puntuación y fallback (Fase 5, §8.6).

Regla de decisión:

1. Si ``P(máxima) >= UMBRAL`` (0.75 ajustado en validación) → se resuelve en
   el Nivel 1. ``puntuacion = round(100 × (1 − P(legítimo)))``.
2. Zona gris → se llama al Nivel 2:
   * JSON válido → ``puntuacion = max(puntuacion_LLM, puntuacion_nivel1)``
     (ante discrepancia gana el **riesgo mayor**, regla 11) y se marca
     ``discrepancia_niveles``.
   * JSON inválido, API caída o sin clave → ``puntuacion_nivel1`` + aviso
     visible de *análisis parcial* (regla 8), ``fuente = nivel_1_fallback``.

El ``nivel_riesgo`` mostrado SIEMPRE se deriva de la puntuación final (§8.5).
La explicación (semáforo, señales y recomendaciones) la construye el módulo
``verifia.explain`` de la Fase 6.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from verifia.classifier import level1
from verifia.classifier.level2_llm import FalloLLM, consultar, dictamen_con_puntuacion_final
from verifia.explain import ADVERTENCIA_PARCIAL, AVISO, explicar
from verifia.schemas import (
    ResultadoClasificacion,
    banda_de_riesgo,
)

TEXTO_VACIO = "El mensaje está vacío; no hay nada que clasificar."

#: Alias histórico: el aviso orientativo vive ahora en ``verifia.explain``.
AVISO_ORIENTATIVO = AVISO


def umbral_confianza() -> float:
    """Umbral de la cascada (0.75 ajustado en validación; 0.80 inicial)."""
    try:
        return float(os.getenv("UMBRAL_CONFIANZA", "0.75"))
    except ValueError:
        return 0.75


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
            return _construir_resultado(
                texto="",
                modelo=None,
                tipologia="legitimo",
                puntuacion=0,
                fuente="nivel_1",
                justificacion="",
                detalle={},
                advertencias=[],
                escalado=False,
                discrepancia=False,
                resumen=TEXTO_VACIO,
            )

        registro = level1.preparar_registro(texto, marcadores, rasgos_enlace)
        probabilidades = self.modelo.predict_proba([registro])[0]
        clases = [str(clase) for clase in self.modelo.classes_]
        p_nivel1 = level1.puntuacion_nivel1(probabilidades, clases)
        prob_maxima = float(probabilidades.max())
        indice_maximo = int(probabilidades.argmax())
        tipologia_nivel1 = clases[indice_maximo]

        advertencias: list[str] = []
        detalle: dict[str, Any] = {
            "prob_maxima": round(prob_maxima, 4),
            "puntuacion_nivel1": p_nivel1,
            "tipologia_nivel1": tipologia_nivel1,
            "umbral": self.umbral,
        }

        if prob_maxima >= self.umbral:
            return _construir_resultado(
                texto=texto,
                modelo=self.modelo,
                tipologia=tipologia_nivel1,
                puntuacion=p_nivel1,
                fuente="nivel_1",
                justificacion="Clasificado por el filtro local del Nivel 1.",
                detalle=detalle,
                advertencias=advertencias,
                escalado=False,
                discrepancia=False,
            )

        # Zona gris: el LLM se consulta solo si está disponible.
        if not self.llamar_llm or self.cliente is None:
            advertencias.append(ADVERTENCIA_PARCIAL)
            detalle["motivo_fallback"] = "sin_llm"
            return _construir_resultado(
                texto=texto,
                modelo=self.modelo,
                tipologia=tipologia_nivel1,
                puntuacion=p_nivel1,
                fuente="nivel_1_fallback",
                justificacion="Clasificado por el filtro local del Nivel 1.",
                detalle=detalle,
                advertencias=advertencias,
                escalado=True,
                discrepancia=False,
            )

        try:
            dictamen, meta = consultar(
                self.cliente, texto, ejemplos=self.ejemplos
            )
        except FalloLLM as exc:
            advertencias.append(ADVERTENCIA_PARCIAL)
            detalle["motivo_fallback"] = exc.motivo
            return _construir_resultado(
                texto=texto,
                modelo=self.modelo,
                tipologia=tipologia_nivel1,
                puntuacion=p_nivel1,
                fuente="nivel_1_fallback",
                justificacion="Clasificado por el filtro local del Nivel 1.",
                detalle=detalle,
                advertencias=advertencias,
                escalado=True,
                discrepancia=False,
            )

        puntuacion = max(int(dictamen.puntuacion), p_nivel1)
        discrepancia = int(dictamen.puntuacion) < puntuacion
        detalle["llm"] = meta
        detalle["puntuacion_llm"] = int(dictamen.puntuacion)
        final = dictamen_con_puntuacion_final(dictamen, puntuacion)
        return _construir_resultado(
            texto=texto,
            modelo=self.modelo,
            tipologia=final.tipologia,
            puntuacion=puntuacion,
            fuente="nivel_2",
            justificacion=final.justificacion,
            detalle=detalle,
            advertencias=advertencias,
            escalado=True,
            discrepancia=discrepancia,
            senales_llm=final.senales_alerta,
        )


def _construir_resultado(
    *,
    texto: str,
    modelo: Any | None,
    tipologia: str,
    puntuacion: int,
    fuente: str,
    justificacion: str,
    detalle: dict[str, Any],
    advertencias: list[str],
    escalado: bool,
    discrepancia: bool,
    senales_llm: list | None = None,
    resumen: str | None = None,
) -> ResultadoClasificacion:
    """Compone la explicación de la Fase 6 y el resultado completo."""
    explicacion = explicar(
        texto=texto,
        tipologia=tipologia,
        puntuacion=puntuacion,
        modelo=modelo,
        senales_llm=senales_llm,
        fuente=fuente,
        advertencias=advertencias,
    )
    datos = explicacion.model_dump()
    if resumen is not None:
        datos["resumen_legible"] = resumen
    return ResultadoClasificacion(
        tipologia=tipologia,
        puntuacion=puntuacion,
        justificacion=justificacion,
        fuente_diccionario=fuente,  # type: ignore[arg-type]
        escalado_a_llm=escalado,
        discrepancia_niveles=discrepancia,
        detalle=detalle,
        **datos,
    )


# ``banda_de_riesgo`` se importa para que los consumidores históricos del
# módulo sigan encontrándolo aquí.
__all__ = [
    "ADVERTENCIA_PARCIAL",
    "AVISO_ORIENTATIVO",
    "CascadeVerifIA",
    "TEXTO_VACIO",
    "banda_de_riesgo",
    "umbral_confianza",
]
