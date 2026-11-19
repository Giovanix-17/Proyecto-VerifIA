"""Esquemas Pydantic de VerifIA (memoria §8.4 y §8.6).

Dos niveles de esquema:

* :class:`DictamenLLM` — el objeto JSON que debe devolver el Nivel 2.
  Se valida con Pydantic y **además** se exige la coherencia
  ``nivel_riesgo`` ↔ banda de la ``puntuacion`` (§8.5): si no coincide, la
  salida del LLM se descarta y aplica el fallback (regla 8).
* :class:`ResultadoClasificacion` — la respuesta del sistema al usuario,
  común a Nivel 1, Nivel 2 y fallback.

Las recomendaciones **no** las genera el LLM: en la Fase 6 se llenan desde el
catálogo por tipología; aquí el campo existe vacío para conservar el contrato
de la respuesta.

Etiquetas internas en ASCII ``snake_case`` (convención de la guía de
anotación), aunque el texto de entrada lleve acentos.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

#: Catálogo cerrado de tipologías (memoria §8.1, igual que ``corpus_common``).
TIPOLOGIAS: tuple[str, ...] = (
    "legitimo",
    "suplantacion_bancaria",
    "paqueteria_retenida",
    "oferta_laboral_fraudulenta",
    "extorsion",
)

Tipologia = Literal[
    "legitimo",
    "suplantacion_bancaria",
    "paqueteria_retenida",
    "oferta_laboral_fraudulenta",
    "extorsion",
]

TipologiaRiesgo = Literal["bajo", "medio", "alto"]

FuenteDictamen = Literal["nivel_1", "nivel_2", "nivel_1_fallback"]


def banda_de_riesgo(puntuacion: int) -> Literal["bajo", "medio", "alto"]:
    """Devuelve la banda del semáforo para una puntuación 0–100 (§8.5)."""
    if puntuacion <= 33:
        return "bajo"
    if puntuacion <= 66:
        return "medio"
    return "alto"


class Senal(BaseModel):
    """Señal de alerta: una frase textual del mensaje y por qué es sospechosa."""

    frase: str = Field(min_length=3, max_length=300)
    motivo: str = Field(min_length=3, max_length=200)


class DictamenLLM(BaseModel):
    """Salida estructurada del Nivel 2 (memoria §8.4)."""

    tipologia: Tipologia
    nivel_riesgo: TipologiaRiesgo
    puntuacion: int = Field(ge=0, le=100)
    senales_alerta: list[Senal] = Field(default_factory=list, max_length=6)
    justificacion: str = Field(min_length=10, max_length=400)

    @field_validator("justificacion")
    @classmethod
    def _no_vacia(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("justificacion vacía")
        return valor

    @model_validator(mode="after")
    def _banda_coherente(self) -> DictamenLLM:
        esperado = banda_de_riesgo(self.puntuacion)
        if self.nivel_riesgo != esperado:
            raise ValueError(
                f"nivel_riesgo {self.nivel_riesgo!r} incoherente con la "
                f"puntuación {self.puntuacion} (banda esperada: {esperado!r})"
            )
        return self


class ResultadoClasificacion(BaseModel):
    """Respuesta del sistema al usuario (memoria §8.6, campos mínimos)."""

    tipologia: Tipologia
    nivel_riesgo: TipologiaRiesgo
    puntuacion: int = Field(ge=0, le=100)
    senales_alerta: list[Senal] = Field(default_factory=list)
    justificacion: str = Field(default="", max_length=400)
    resumen_legible: str = Field(default="", max_length=300)
    recomendaciones: list[str] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)
    #: ``nivel_1`` · ``nivel_2`` · ``nivel_1_fallback`` (regla 8).
    fuente_diccionario: FuenteDictamen
    escalado_a_llm: bool = False
    discrepancia_niveles: bool = False
    #: Metadatos de diagnóstico, sin el texto del mensaje (regla 2).
    detalle: dict[str, Any] = Field(default_factory=dict)
