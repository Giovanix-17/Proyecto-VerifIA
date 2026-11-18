"""Contratos de entrada y salida del OCR (Fase 4)."""

from __future__ import annotations

from dataclasses import dataclass

# Modos de segmentación de Tesseract aceptados para capturas de mensajería.
PSM_VALIDOS = frozenset({3, 4, 6, 11, 12})


@dataclass(frozen=True)
class OpcionesOCR:
    """Parámetros del pipeline; los valores por omisión sirven para chats.

    ``recorte`` es una caja relativa ``(x0, y0, x1, y1)`` en el rango 0-1.
    Se usa para excluir barras de estado, encabezados y campos de escritura;
    es opcional porque un recorte agresivo puede borrar mensajes.
    """

    idioma: str = "spa"
    psm: int = 6
    recorte: tuple[float, float, float, float] | None = None
    ampliar: bool = True
    invertir_automatico: bool = True
    unir_lineas: bool = True
    minimo_caracteres: int = 10

    def __post_init__(self) -> None:
        if self.psm not in PSM_VALIDOS:
            raise ValueError(f"psm debe ser uno de {sorted(PSM_VALIDOS)}")
        if self.minimo_caracteres < 0:
            raise ValueError("minimo_caracteres no puede ser negativo")
        if self.recorte is not None:
            if len(self.recorte) != 4:
                raise ValueError("recorte debe tener cuatro valores (x0, y0, x1, y1)")
            x0, y0, x1, y1 = self.recorte
            if not all(0.0 <= valor <= 1.0 for valor in self.recorte):
                raise ValueError("los valores de recorte deben estar entre 0 y 1")
            if x0 >= x1 or y0 >= y1:
                raise ValueError("recorte requiere x0 < x1 y y0 < y1")


@dataclass(frozen=True)
class TextoOCR:
    """Borrador editable que se muestra al usuario antes de clasificar.

    No contiene la imagen ni se persiste: vive solo durante la petición.
    """

    texto: str
    caracteres_utiles: int
    confianza: float | None
    modo: str
    ancho: int
    alto: int
    operaciones: tuple[str, ...] = ()
    advertencias: tuple[str, ...] = ()
