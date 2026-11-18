"""Validación de entrada del OCR (Fase 4).

Los límites se aplican **antes** de preprocesar: si la imagen los excede se
informa y se detiene; nunca se reescala en silencio. El formato se decide por
magic bytes, no por la extensión del archivo.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from verifia.ocr.errors import FormatoNoSoportado, ImagenInvalida, LimiteExcedido

LIMITE_BYTES = 5 * 1024 * 1024
LIMITE_LADO = 4000
LIMITE_PIXELES = 12_000_000

_FIRMAS = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
)

_RUTA_IMAGEN = str | Path


@dataclass(frozen=True)
class ImagenValidada:
    """Metadatos de la imagen que ya pasó los límites."""

    datos: bytes
    formato: str
    ancho: int
    alto: int

    @property
    def megapixeles(self) -> float:
        return self.ancho * self.alto / 1_000_000


def _firma(datos: bytes) -> str | None:
    for firma, formato in _FIRMAS:
        if datos.startswith(firma):
            return formato
    return None


def leer_archivo(ruta: _RUTA_IMAGEN) -> bytes:
    """Lee la imagen desde disco sin cargarla al pipeline si no existe."""
    try:
        return Path(ruta).read_bytes()
    except OSError as exc:
        raise ImagenInvalida("No se pudo leer el archivo de imagen.") from exc


def validar_imagen(fuente: bytes | bytearray | memoryview | _RUTA_IMAGEN) -> ImagenValidada:
    """Comprueba tamaño, formato, dimensiones y que la imagen decodifique."""
    if isinstance(fuente, (str, Path)):
        datos = leer_archivo(fuente)
    elif isinstance(fuente, (bytes, bytearray, memoryview)):
        datos = bytes(fuente)
    else:
        raise TypeError("La imagen debe ser bytes, una ruta o un Path.")

    if not datos:
        raise ImagenInvalida("El archivo de imagen está vacío.")

    if len(datos) > LIMITE_BYTES:
        raise LimiteExcedido(
            f"La imagen pesa {len(datos) / (1024 * 1024):.1f} MB; "
            f"el límite es {LIMITE_BYTES // (1024 * 1024)} MB."
        )

    formato = _firma(datos)
    if formato is None:
        raise FormatoNoSoportado("Solo se aceptan imágenes PNG o JPEG.")

    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            ancho, alto = imagen.size
            if getattr(imagen, "format", None) != formato:
                raise FormatoNoSoportado("El contenido no corresponde a un PNG o JPEG válido.")
            if ancho <= 0 or alto <= 0:
                raise ImagenInvalida("La imagen no tiene dimensiones válidas.")

            if max(ancho, alto) > LIMITE_LADO:
                raise LimiteExcedido(
                    f"La imagen mide {ancho}×{alto} px; el lado mayor debe ser "
                    f"≤ {LIMITE_LADO} px."
                )
            if ancho * alto > LIMITE_PIXELES:
                raise LimiteExcedido(
                    f"La imagen tiene {ancho * alto / 1_000_000:.1f} MP; "
                    f"el límite es {LIMITE_PIXELES // 1_000_000} MP."
                )

            # Fuerza la decodificación completa: un JPEG truncado debe fallar
            # aquí (422) y no más adelante como error interno.
            imagen.load()
    except (FormatoNoSoportado, LimiteExcedido, ImagenInvalida):
        raise
    except Image.DecompressionBombError as exc:
        raise LimiteExcedido("La imagen excede el límite de píxeles permitido.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImagenInvalida("La imagen está dañada o truncada y no se pudo decodificar.") from exc

    return ImagenValidada(datos=datos, formato=formato, ancho=ancho, alto=alto)
