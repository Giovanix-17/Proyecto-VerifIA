"""Pruebas del módulo OCR (Fase 4).

Los casos de integración se omiten si el entorno no tiene Tesseract con el
paquete español; las pruebas de límites y posprocesamiento corren siempre.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from verifia.ocr import (
    FormatoNoSoportado,
    ImagenInvalida,
    LimiteExcedido,
    OpcionesOCR,
    TextoInsuficiente,
    disponibilidad,
    extraer_texto,
    extraer_y_sanitizar,
)
from verifia.ocr.extraccion import LineaOCR
from verifia.ocr.posprocesamiento import posprocesar, unir_lineas
from verifia.ocr.preprocesamiento import _bloque_adaptativo, detectar_modo
from verifia.ocr.validacion import validar_imagen


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatas = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for ruta in candidatas:
        if ruta.is_file():
            return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(size=tamano)


def _render(
    lineas: list[str],
    *,
    oscuro: bool = False,
    tamano: tuple[int, int] = (900, 500),
    fuente_px: int = 28,
    encabezado: str | None = None,
    emoji: bool = False,
) -> bytes:
    fondo = (16, 24, 30) if oscuro else (233, 226, 218)
    burbuja = (32, 44, 51) if oscuro else (255, 255, 255)
    tinta = (242, 242, 242) if oscuro else (22, 22, 22)

    imagen = Image.new("RGB", tamano, fondo)
    dibujo = ImageDraw.Draw(imagen)
    fuente = _fuente(fuente_px)

    y = 60
    if encabezado:
        dibujo.rectangle((0, 0, tamano[0], 90), fill=(0, 120, 90) if oscuro else (7, 94, 84))
        dibujo.text((24, 30), encabezado, font=_fuente(22), fill=(255, 255, 255))
        y = 130

    for linea in lineas:
        ancho, alto = dibujo.textbbox((0, 0), linea, font=fuente)[2:]
        alto_caja = alto + 36
        dibujo.rounded_rectangle(
            (30, y, min(tamano[0] - 30, 30 + ancho + 50), y + alto_caja),
            radius=14,
            fill=burbuja,
        )
        dibujo.text((55, y + 18), linea, font=fuente, fill=tinta)
        y += alto_caja + 28

    if emoji:
        centro = (tamano[0] - 70, y + 20)
        dibujo.ellipse(
            (centro[0] - 22, centro[1] - 22, centro[0] + 22, centro[1] + 22),
            fill=(255, 190, 40),
            outline=(90, 60, 0),
            width=2,
        )

    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    return salida.getvalue()


def _ocr_disponible() -> bool:
    try:
        return bool(disponibilidad().get("disponible"))
    except Exception:  # pragma: no cover - diagnóstico defensivo
        return False


requiere_ocr = pytest.mark.skipif(
    not _ocr_disponible(), reason="Tesseract con paquete spa no disponible"
)


# ---------------------------------------------------------------------------
# Límites y formato
# ---------------------------------------------------------------------------


def test_archivo_mayor_a_5_mb() -> None:
    with pytest.raises(LimiteExcedido) as error:
        validar_imagen(b"x" * (5 * 1024 * 1024 + 1))
    assert error.value.codigo_http == 413


def test_lado_mayor_a_4000_px() -> None:
    imagen = Image.new("RGB", (4001, 120), "white")
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    with pytest.raises(LimiteExcedido):
        validar_imagen(salida.getvalue())


def test_mas_de_12_megapixeles() -> None:
    imagen = Image.new("RGB", (3500, 3500), "white")
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    with pytest.raises(LimiteExcedido):
        validar_imagen(salida.getvalue())


def test_jpeg_corrupto() -> None:
    with pytest.raises(ImagenInvalida):
        validar_imagen(b"\xff\xd8\xff" + b"basura" * 20)


def test_gif_rechazado_por_magic_bytes() -> None:
    with pytest.raises(FormatoNoSoportado):
        validar_imagen(b"GIF89a" + b"\x00" * 100)


def test_archivo_vacio() -> None:
    with pytest.raises(ImagenInvalida):
        validar_imagen(b"")


def test_extension_no_decide_el_formato(tmp_path: Path) -> None:
    ruta = tmp_path / "captura.jpg"
    ruta.write_bytes(_render(["Mensaje de prueba"]))
    assert validar_imagen(ruta).formato == "PNG"


def test_png_valido_tiene_metadatos() -> None:
    validada = validar_imagen(_render(["Hola"]))
    assert validada.formato == "PNG"
    assert validada.ancho == 900
    assert validada.alto == 500
    assert validada.megapixeles == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Preprocesamiento y posprocesamiento (sin Tesseract)
# ---------------------------------------------------------------------------


def test_deteccion_de_modo() -> None:
    claro = np.full((50, 50), 220, dtype=np.uint8)
    oscuro = np.full((50, 50), 30, dtype=np.uint8)
    assert detectar_modo(claro) == "claro"
    assert detectar_modo(oscuro) == "oscuro"


def test_bloque_adaptativo_es_impar_y_valido() -> None:
    for ancho, alto in [(900, 500), (31, 40), (16, 16), (4000, 3000)]:
        bloque = _bloque_adaptativo(ancho, alto)
        assert bloque % 2 == 1
        assert 3 <= bloque < min(ancho, alto)


def test_unir_lineas_del_mismo_globo() -> None:
    primera = LineaOCR("Le informamos que su", 40, 10, 300, 38, 90.0)
    segunda = LineaOCR("paquete esta retenido", 40, 44, 320, 72, 90.0)
    tercera = LineaOCR("Otro mensaje distinto", 40, 160, 320, 188, 90.0)

    unidas = unir_lineas([primera, segunda, tercera])

    assert len(unidas) == 2
    assert unidas[0].texto == "Le informamos que su paquete esta retenido"
    assert unidas[1].texto == "Otro mensaje distinto"


def test_posprocesamiento_quita_horas_y_separadores() -> None:
    lineas = [
        LineaOCR("HOY", 10, 10, 60, 30, 80.0),
        LineaOCR("Su cuenta sera bloqueada 12:34", 10, 40, 400, 70, 90.0),
        LineaOCR("12:35 p.m.", 350, 80, 450, 100, 85.0),
        LineaOCR("Llame ahora", 10, 110, 200, 140, 90.0),
    ]

    texto = posprocesar(lineas, OpcionesOCR(unir_lineas=False))

    assert texto == "Su cuenta sera bloqueada\nLlame ahora"


def test_posprocesamiento_elimina_cromo_de_app() -> None:
    lineas = [
        LineaOCR("WhatsApp", 10, 10, 120, 30, 90.0),
        LineaOCR("Mensaje real", 10, 50, 200, 80, 90.0),
    ]
    assert posprocesar(lineas, OpcionesOCR()) == "Mensaje real"


def test_posprocesamiento_corrige_arroba_confundida() -> None:
    lineas = [LineaOCR("Escriba a anaQejemplo.com", 10, 10, 400, 40, 80.0)]
    assert posprocesar(lineas, OpcionesOCR()) == "Escriba a ana@ejemplo.com"


def test_posprocesamiento_corrige_arroba_con_espacio() -> None:
    lineas = [LineaOCR("Escriba a empleo Qejemplo.com", 10, 10, 400, 40, 80.0)]
    assert posprocesar(lineas, OpcionesOCR()) == "Escriba a empleo@ejemplo.com"
    lineas = [LineaOCR("Escriba a empleo Gejemplo.com", 10, 10, 400, 40, 80.0)]
    assert posprocesar(lineas, OpcionesOCR()) == "Escriba a empleo@ejemplo.com"


def test_descarta_hora_sin_dos_puntos_si_es_mas_baja() -> None:
    lineas = [
        LineaOCR("Mensaje importante", 10, 10, 400, 40, 90.0),
        LineaOCR("1234", 350, 44, 400, 58, 80.0),
    ]
    assert posprocesar(lineas, OpcionesOCR()) == "Mensaje importante"


def test_descarta_ruido_de_bordes() -> None:
    lineas = [
        LineaOCR("Mensaje real", 10, 10, 300, 40, 90.0),
        LineaOCR("| - 1 r |", 10, 50, 100, 70, 30.0),
    ]
    assert posprocesar(lineas, OpcionesOCR()) == "Mensaje real"


def test_descarta_resto_de_hora_con_baja_confianza() -> None:
    lineas = [
        LineaOCR("Mensaje real", 10, 10, 300, 40, 92.0),
        LineaOCR("' . 235 +", 10, 50, 120, 81, 38.0),
    ]
    assert posprocesar(lineas, OpcionesOCR()) == "Mensaje real"


def test_opciones_invalidas() -> None:
    with pytest.raises(ValueError):
        OpcionesOCR(psm=5)
    with pytest.raises(ValueError):
        OpcionesOCR(recorte=(0.5, 0.0, 0.4, 1.0))
    with pytest.raises(ValueError):
        OpcionesOCR(recorte=(0.0, 0.0, 1.2, 1.0))


# ---------------------------------------------------------------------------
# Integración con Tesseract
# ---------------------------------------------------------------------------


@requiere_ocr
def test_captura_clara_conserva_telefono_para_sanitizar() -> None:
    datos = _render(
        [
            "Su paquete esta retenido.",
            "Llame al 55 1234 5678 para liberarlo.",
        ]
    )

    resultado = extraer_texto(datos)

    assert resultado.modo == "claro"
    assert "55 1234 5678" in resultado.texto
    assert "retenido" in resultado.texto
    assert resultado.confianza is not None


@requiere_ocr
def test_captura_oscura_se_invierte() -> None:
    datos = _render(["Su cuenta sera bloqueada", "Llame al 55 1234 5678"], oscuro=True)

    resultado = extraer_texto(datos)

    assert resultado.modo == "oscuro"
    assert "invertido" in resultado.operaciones
    assert "bloqueada" in resultado.texto


@requiere_ocr
def test_captura_pequena_se_amplia() -> None:
    datos = _render(["Pague ahora"], tamano=(480, 220), fuente_px=18)

    resultado = extraer_texto(datos)

    assert "escala_2x" in resultado.operaciones
    assert "Pague" in resultado.texto


@requiere_ocr
def test_emoji_no_rompe_el_texto() -> None:
    datos = _render(["Aviso importante"], emoji=True)

    resultado = extraer_texto(datos)

    assert "Aviso" in resultado.texto
    assert "importante" in resultado.texto


@requiere_ocr
def test_recorte_excluye_encabezado() -> None:
    datos = _render(
        ["El mensaje que importa"],
        encabezado="ENCABEZADO DE LA APP",
        tamano=(900, 600),
    )

    completo = extraer_texto(datos)
    recortado = extraer_texto(datos, OpcionesOCR(recorte=(0.0, 0.17, 1.0, 1.0)))

    assert "ENCABEZADO" in completo.texto
    assert "ENCABEZADO" not in recortado.texto
    assert "importa" in recortado.texto


@requiere_ocr
def test_imagen_en_blanco_no_devuelve_basura() -> None:
    imagen = Image.new("RGB", (900, 500), "white")
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")

    with pytest.raises(TextoInsuficiente):
        extraer_texto(salida.getvalue())


@requiere_ocr
def test_ocr_y_sanitizacion_encadenados() -> None:
    datos = _render(["Escriba a ana@ejemplo.com o llame al 55 1234 5678"])

    borrador, limpio = extraer_y_sanitizar(datos)

    assert "ana@ejemplo.com" in borrador.texto
    assert "ana@ejemplo.com" not in limpio.texto
    assert "[CORREO]" in limpio.texto
    assert "[TELEFONO]" in limpio.texto
