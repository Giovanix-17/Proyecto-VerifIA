"""Resumen legible y determinista (Fase 6).

Tres frases como máximo, en este orden:

1. qué se detectó (tipología en lenguaje llano),
2. la señal más relevante,
3. la consecuencia de actuar conforme al mensaje.

No se usa el LLM para redactar: el mismo dictamen produce siempre el mismo
texto. Frases cortas, sin tecnicismos y sin segunda persona acusatoria.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from verifia.explain.catalogo import consecuencia, tipologia_llana
from verifia.schemas import SenalResaltada

PLANTILLA = (
    "El mensaje se parece a {tipologia}. "
    "La señal más importante es: {senal}. "
    "{consecuencia}"
)

SIN_SENAL = "no se identificó una señal textual concreta"


def _limpiar(texto: str, maximo: int) -> str:
    """Quita saltos, puntos finales y recorta sin cortar palabras a la mitad."""
    limpio = re.sub(r"\s+", " ", texto).strip().rstrip(".")
    if len(limpio) <= maximo:
        return limpio
    recorte = limpio[:maximo].rsplit(" ", 1)[0]
    return recorte.rstrip(" ,;:") + "…"


def construir_resumen(tipologia: str, senales: Sequence[SenalResaltada]) -> str:
    """Arma el resumen de tres frases a partir del dictamen ya calculado."""
    if senales:
        principal = senales[0]
        frase = _limpiar(principal.frase, 70)
        motivo = _limpiar(principal.motivo, 70)
        senal = f"«{frase}»: {motivo}"
    else:
        senal = SIN_SENAL
    return PLANTILLA.format(
        tipologia=tipologia_llana(tipologia),
        senal=senal,
        consecuencia=consecuencia(tipologia),
    )
