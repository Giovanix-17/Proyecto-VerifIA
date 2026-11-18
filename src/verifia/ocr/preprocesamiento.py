"""Preprocesamiento de capturas con OpenCV (Fase 4).

Orden: orientación EXIF → escala de grises → ampliación → inversión en modo
oscuro → reducción de ruido → binarización adaptativa. Cada paso aplicado se
registra en ``operaciones`` para poder reproducir el CER.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

from verifia.ocr.errors import ImagenInvalida
from verifia.ocr.models import OpcionesOCR
from verifia.ocr.validacion import ImagenValidada

UMBRAL_MODO_OSCURO = 110
ALTO_MINIMO_AMPLIACION = 800
FACTOR_AMPLIACION = 2


@dataclass(frozen=True)
class ImagenPreprocesada:
    """Imagen binaria lista para Tesseract y la traza de operaciones."""

    binaria: NDArray[np.uint8]
    modo: str
    operaciones: tuple[str, ...]


def detectar_modo(gris: NDArray[np.uint8]) -> str:
    """Clasifica la captura como clara u oscura según la luminancia mediana."""
    return "oscuro" if float(np.median(gris)) < UMBRAL_MODO_OSCURO else "claro"


def _recortar(
    gris: NDArray[np.uint8],
    recorte: tuple[float, float, float, float],
) -> NDArray[np.uint8]:
    alto, ancho = gris.shape[:2]
    x0, y0, x1, y1 = recorte
    izquierda = max(0, min(ancho - 1, round(x0 * ancho)))
    arriba = max(0, min(alto - 1, round(y0 * alto)))
    derecha = max(izquierda + 1, min(ancho, round(x1 * ancho)))
    abajo = max(arriba + 1, min(alto, round(y1 * alto)))
    return gris[arriba:abajo, izquierda:derecha]


def _bloque_adaptativo(ancho: int, alto: int) -> int:
    """Elige un ``blockSize`` impar proporcional al ancho y válido para OpenCV."""
    bloque = max(31, min(51, int(ancho / 25)))
    if bloque % 2 == 0:
        bloque += 1
    limite = min(ancho, alto)
    maximo = limite - 1 if limite % 2 == 0 else limite - 2
    return max(3, min(bloque, maximo))


def preprocesar(
    datos: bytes,
    validada: ImagenValidada,
    opciones: OpcionesOCR,
) -> ImagenPreprocesada:
    """Convierte la captura a una imagen binaria de texto oscuro sobre fondo claro."""
    operaciones: list[str] = []

    try:
        with Image.open(io.BytesIO(datos)) as original:
            # 1. EXIF antes que cualquier otra operación.
            orientada = ImageOps.exif_transpose(original).convert("RGB")
            rgb = np.asarray(orientada)
    except (OSError, ValueError) as exc:  # pragma: no cover - validado antes
        raise ImagenInvalida("La imagen no se pudo decodificar para preprocesar.") from exc

    gris = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    operaciones.append("gris")

    if opciones.recorte is not None:
        gris = _recortar(gris, opciones.recorte)
        operaciones.append("recorte")

    alto, ancho = gris.shape[:2]
    if min(alto, ancho) < 16:
        raise ImagenInvalida("La imagen es demasiado pequeña para extraer texto.")

    # 2. Ampliación de capturas pequeñas (causa frecuente de CER alto).
    if opciones.ampliar and alto < ALTO_MINIMO_AMPLIACION:
        gris = cv2.resize(
            gris,
            (ancho * FACTOR_AMPLIACION, alto * FACTOR_AMPLIACION),
            interpolation=cv2.INTER_CUBIC,
        )
        operaciones.append(f"escala_{FACTOR_AMPLIACION}x")

    # 3. Modo oscuro: se invierte para que Tesseract vea tinta sobre papel.
    modo = detectar_modo(gris)
    if modo == "oscuro" and opciones.invertir_automatico:
        gris = cv2.bitwise_not(gris)
        operaciones.append("invertido")

    # 4. Ruido de compresión o de captura.
    gris = cv2.fastNlMeansDenoising(gris, None, h=10, templateWindowSize=7, searchWindowSize=21)
    operaciones.append("denoise")

    # 5. Normalización de fondo: aplana la diferencia entre la burbuja y el
    #    fondo (crítica en modo oscuro) antes de binarizar.
    sigma = max(9.0, gris.shape[1] / 30)
    fondo = cv2.GaussianBlur(gris, (0, 0), sigmaX=sigma)
    normalizada = cv2.divide(gris, fondo, scale=255)
    operaciones.append("fondo_normalizado")

    # 6. Otsu sobre la imagen normalizada. Se midió contra el umbral adaptativo:
    #    este último generaba ruido en los bordes de las burbujas. El adaptativo
    #    queda como respaldo si Otsu satura la imagen.
    _, binaria = cv2.threshold(normalizada, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    operaciones.append("otsu")
    proporcion_tinta = float(np.count_nonzero(binaria == 0)) / binaria.size
    if proporcion_tinta > 0.6:
        bloque = _bloque_adaptativo(gris.shape[1], gris.shape[0])
        binaria = cv2.adaptiveThreshold(
            normalizada,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            bloque,
            12,
        )
        operaciones.append("adaptativo_respaldo")

    return ImagenPreprocesada(binaria=binaria, modo=modo, operaciones=tuple(operaciones))
