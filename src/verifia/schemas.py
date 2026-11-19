"""Esquemas Pydantic de VerifIA (memoria §8.4 y §8.6).

Dos niveles de esquema:

* :class:`DictamenLLM` — el objeto JSON que debe devolver el Nivel 2.
  Se valida con Pydantic y **además** se exige la coherencia
  ``nivel_riesgo`` ↔ banda de la ``puntuacion`` (§8.5): si no coincide, la
  salida del LLM se descarta y aplica el fallback (regla 8).
* :class:`ResultadoClasificacion` — la respuesta del sistema al usuario,
  común a Nivel 1, Nivel 2 y fallback.

Las recomendaciones **no** las genera el LLM: se llenan desde el catálogo
predefinido por tipología (Fase 6, regla 6).

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

EstadoSemaforo = Literal["verde", "amarillo", "rojo"]

CategoriaSenal = Literal[
    "urgencia",
    "amenaza",
    "suplantacion",
    "solicitud_datos",
    "solicitud_codigo",
    "enlace_sospechoso",
    "pago_anticipado",
    "premio_falso",
    "oferta_laboral",
    "otro",
]

OrigenSenal = Literal["nivel_1", "nivel_2"]

#: Correspondencia cerrada entre el color del semáforo y la banda (§8.5).
ESTADO_A_NIVEL: dict[str, str] = {
    "verde": "bajo",
    "amarillo": "medio",
    "rojo": "alto",
}


def banda_de_riesgo(puntuacion: int) -> Literal["bajo", "medio", "alto"]:
    """Devuelve la banda del semáforo para una puntuación 0–100 (§8.5)."""
    if puntuacion <= 33:
        return "bajo"
    if puntuacion <= 66:
        return "medio"
    return "alto"


def estado_de_puntuacion(puntuacion: int) -> EstadoSemaforo:
    """Traduce la puntuación final al color del semáforo (§8.5).

    Se deriva **siempre de la puntuación**, nunca del ``nivel_riesgo`` que
    propuso el LLM (skill ``verifia-explicabilidad``).
    """
    if puntuacion <= 33:
        return "verde"
    if puntuacion <= 66:
        return "amarillo"
    return "rojo"


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


class SenalResaltada(Senal):
    """Señal ya localizada sobre el texto sanitizado (Fase 6).

    ``inicio``/``fin`` son offsets sobre el **texto sanitizado** para que la
    interfaz pueda resaltar la frase sin volver a buscarla. No contienen el
    dato original: el texto ya viene enmascarado (regla 3).
    """

    categoria: CategoriaSenal = "otro"
    origen: OrigenSenal = "nivel_1"
    inicio: int | None = Field(default=None, ge=0)
    fin: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _span_coherente(self) -> SenalResaltada:
        if (self.inicio is None) != (self.fin is None):
            raise ValueError("inicio y fin deben venir juntos")
        if self.inicio is not None and self.fin is not None and self.fin <= self.inicio:
            raise ValueError("fin debe ser mayor que inicio")
        return self


class Explicacion(BaseModel):
    """Traducción del dictamen a lenguaje ciudadano (Fase 6).

    El semáforo se deriva de la puntuación final; este objeto no decide nada,
    solo explica. Las recomendaciones son un catálogo fijo (regla 6) y el
    aviso orientativo es obligatorio (regla 13).
    """

    estado: EstadoSemaforo
    nivel_riesgo: TipologiaRiesgo
    titulo: str = Field(min_length=1, max_length=40)
    icono: str = Field(min_length=1, max_length=4)
    descripcion: str = Field(min_length=1, max_length=200)
    accion: str = Field(min_length=1, max_length=200)
    resumen_legible: str = Field(min_length=1, max_length=300)
    senales_alerta: list[SenalResaltada] = Field(default_factory=list, max_length=5)
    recomendaciones: list[str] = Field(default_factory=list, min_length=3, max_length=6)
    advertencias: list[str] = Field(default_factory=list)
    aviso: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _estado_coherente(self) -> Explicacion:
        if ESTADO_A_NIVEL[self.estado] != self.nivel_riesgo:
            raise ValueError(
                f"estado {self.estado!r} incoherente con nivel_riesgo "
                f"{self.nivel_riesgo!r}"
            )
        return self


class ResultadoClasificacion(Explicacion):
    """Respuesta completa del sistema al usuario (memoria §8.6).

    Hereda la explicación (semáforo, señales, catálogo y aviso) y añade la
    trazabilidad del dictamen: tipología, puntuación y fuente.
    """

    tipologia: Tipologia
    puntuacion: int = Field(ge=0, le=100)
    justificacion: str = Field(default="", max_length=400)
    #: ``nivel_1`` · ``nivel_2`` · ``nivel_1_fallback`` (regla 8).
    fuente_diccionario: FuenteDictamen
    escalado_a_llm: bool = False
    discrepancia_niveles: bool = False
    #: Metadatos de diagnóstico, sin el texto del mensaje (regla 2).
    detalle: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _puntuacion_coherente(self) -> ResultadoClasificacion:
        esperado_nivel = banda_de_riesgo(self.puntuacion)
        if self.nivel_riesgo != esperado_nivel:
            raise ValueError(
                f"nivel_riesgo {self.nivel_riesgo!r} incoherente con la "
                f"puntuación {self.puntuacion} (banda esperada: {esperado_nivel!r})"
            )
        esperado_estado = estado_de_puntuacion(self.puntuacion)
        if self.estado != esperado_estado:
            raise ValueError(
                f"estado {self.estado!r} incoherente con la puntuación "
                f"{self.puntuacion} (esperado: {esperado_estado!r})"
            )
        return self
