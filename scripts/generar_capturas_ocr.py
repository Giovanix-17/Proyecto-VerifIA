"""Genera capturas sintéticas de mensajería para evaluar el OCR (Fase 4).

Las 60 capturas imitan WhatsApp y la app de SMS, en modo claro y oscuro, en
cuatro resoluciones. Solo contienen mensajes de prueba: ningún dato personal es
real. El manifiesto guarda la transcripción de referencia y la caja relativa de
la conversación, que excluye barra de estado, encabezado y campo de escritura.

Uso::

    python scripts/generar_capturas_ocr.py
    python scripts/generar_capturas_ocr.py --salida data/ocr_test --cantidad 60
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SALIDA_POR_OMISION = ROOT / "data" / "ocr_test"
SEMILLA = 20261117

RESOLUCIONES = ("720x1280", "1080x1920", "480x800", "360x640")
MODOS = ("claro", "oscuro")
APPS = ("whatsapp", "sms")

# Mensajes de prueba (sin datos personales reales).
MENSAJES = (
    "Su paquete fue retenido en la aduana. Pague 250 pesos para liberarlo.",
    "Gano 15000 pesos al día desde casa. Escriba a empleo@ejemplo.com.",
    "Su cuenta de banco será bloqueada. Llame al 55 0000 0000 ahora.",
    "Felicidades, ganó un premio de 50000 pesos. Reclame en bit.ly/premio.",
    "Verifique su identidad en el enlace https://ejemplo.com/seguridad",
    "Su código de verificación es 482913. No lo comparta.",
    "Hola, soy su sobrino. Cambié mi número, guárdeme.",
    "Necesito que me deposites 3000 pesos a esta cuenta hoy.",
    "Le informamos que su tarjeta termina en 1234 y fue usada en otro país.",
    "Pague su recibo de luz en la tienda más cercana.",
    "Su suscripción fue renovada por 299 pesos. Gracias.",
    "Tenemos una oferta de trabajo para usted. Envíe su CV.",
    "Ganó una tarjeta de regalo de 1000 pesos. Confirme sus datos.",
    "Su paquete llegó a la sucursal. Recoger con identificación.",
    "Actualice sus datos bancarios en el portal.",
    "Llame al 800 000 0000 para cancelar el cargo.",
    "Este es un aviso de entrega de su pedido.",
    "Su familiar tuvo un accidente. Envíe dinero urgente.",
    "Promoción válida solo hoy. Aproveche.",
    "Su código postal fue actualizado correctamente.",
    "Escriba a soporte@ejemplo.com si tiene dudas.",
    "Visite www.ejemplo.com para conocer su saldo.",
    "Le ofrecemos un préstamo inmediato sin aval.",
    "Confirme el pago de 750 pesos por el servicio.",
)


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatas = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for ruta in candidatas:
        if ruta.is_file():
            return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(size=tamano)


def _paleta(modo: str, app: str) -> dict[str, tuple[int, int, int]]:
    if app == "whatsapp" and modo == "claro":
        return {
            "fondo": (236, 229, 221),
            "barra": (7, 94, 84),
            "burbuja_entrada": (255, 255, 255),
            "burbuja_salida": (220, 248, 198),
            "texto_entrada": (20, 20, 20),
            "texto_salida": (20, 20, 20),
            "meta": (110, 110, 110),
            "barra_texto": (255, 255, 255),
            "campo": (255, 255, 255),
        }
    if app == "whatsapp":
        return {
            "fondo": (11, 20, 26),
            "barra": (32, 44, 51),
            "burbuja_entrada": (32, 44, 51),
            "burbuja_salida": (0, 92, 75),
            "texto_entrada": (240, 240, 240),
            "texto_salida": (240, 240, 240),
            "meta": (160, 170, 170),
            "barra_texto": (240, 240, 240),
            "campo": (32, 44, 51),
        }
    if modo == "claro":
        return {
            "fondo": (242, 242, 247),
            "barra": (255, 255, 255),
            "burbuja_entrada": (233, 233, 235),
            "burbuja_salida": (198, 224, 255),
            "texto_entrada": (20, 20, 20),
            "texto_salida": (20, 20, 20),
            "meta": (120, 120, 120),
            "barra_texto": (20, 20, 20),
            "campo": (255, 255, 255),
        }
    return {
        "fondo": (0, 0, 0),
        "barra": (28, 28, 30),
        "burbuja_entrada": (38, 38, 40),
        "burbuja_salida": (10, 132, 255),
        "texto_entrada": (245, 245, 245),
        "texto_salida": (255, 255, 255),
        "meta": (170, 170, 170),
        "barra_texto": (245, 245, 245),
        "campo": (38, 38, 40),
    }


def _envolver(
    dibujo: ImageDraw.ImageDraw,
    texto: str,
    fuente: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ancho_max: int,
) -> list[str]:
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        tentativa = f"{actual} {palabra}".strip()
        if dibujo.textlength(tentativa, font=fuente) <= ancho_max or not actual:
            actual = tentativa
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _dibujar_burbuja(
    dibujo: ImageDraw.ImageDraw,
    texto: str,
    *,
    x: int,
    y: int,
    ancho_max: int,
    fuente: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fuente_meta: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    relleno: tuple[int, int, int],
    tinta: tuple[int, int, int],
    meta: tuple[int, int, int],
    hora: str,
) -> int:
    margen = 18
    lineas = _envolver(dibujo, texto, fuente, ancho_max)
    alto_linea = int(fuente.size * 1.35) if hasattr(fuente, "size") else 24
    ancho_texto = max(dibujo.textlength(linea, font=fuente) for linea in lineas)
    ancho_burbuja = int(ancho_texto) + margen * 2
    alto_burbuja = len(lineas) * alto_linea + margen * 2 + int(fuente_meta.size * 1.6)

    dibujo.rounded_rectangle(
        (x, y, x + ancho_burbuja, y + alto_burbuja),
        radius=14,
        fill=relleno,
    )
    cursor = y + margen
    for linea in lineas:
        dibujo.text((x + margen, cursor), linea, font=fuente, fill=tinta)
        cursor += alto_linea

    ancho_hora = dibujo.textlength(hora, font=fuente_meta)
    dibujo.text(
        (x + ancho_burbuja - margen - ancho_hora, y + alto_burbuja - margen - 4),
        hora,
        font=fuente_meta,
        fill=meta,
    )
    return y + alto_burbuja


def _renderizar(
    *,
    modo: str,
    app: str,
    resolucion: tuple[int, int],
    mensajes: list[str],
    salientes: list[bool],
) -> tuple[Image.Image, tuple[float, float, float, float]]:
    ancho, alto = resolucion
    paleta = _paleta(modo, app)
    imagen = Image.new("RGB", (ancho, alto), paleta["fondo"])
    dibujo = ImageDraw.Draw(imagen)

    escala = ancho / 720
    fuente = _fuente(max(13, round(28 * escala)))
    fuente_meta = _fuente(max(10, round(20 * escala)))
    fuente_barra = _fuente(max(11, round(24 * escala)))

    barra_alto = round(alto * 0.030)
    encabezado_alto = round(alto * 0.055)
    campo_alto = round(alto * 0.075)

    # Barra de estado: fuera de la caja de conversación.
    dibujo.rectangle((0, 0, ancho, barra_alto), fill=paleta["barra"])
    dibujo.text(
        (round(14 * escala), max(2, round(barra_alto * 0.18))),
        "12:34",
        font=fuente_barra,
        fill=paleta["barra_texto"],
    )
    dibujo.text(
        (ancho // 2 - 30, max(2, round(barra_alto * 0.18))),
        "Telcel",
        font=fuente_barra,
        fill=paleta["barra_texto"],
    )
    bateria = f"{82 + (ancho % 7)}%"
    dibujo.text(
        (ancho - round(60 * escala), max(2, round(barra_alto * 0.18))),
        bateria,
        font=fuente_barra,
        fill=paleta["barra_texto"],
    )

    # Encabezado de la app: fuera de la caja de conversación.
    dibujo.rectangle((0, barra_alto, ancho, barra_alto + encabezado_alto), fill=paleta["barra"])
    dibujo.text(
        (round(20 * escala), barra_alto + round(encabezado_alto * 0.16)),
        "Contacto de prueba",
        font=fuente,
        fill=paleta["barra_texto"],
    )
    dibujo.text(
        (round(20 * escala), barra_alto + round(encabezado_alto * 0.60)),
        "en linea",
        font=fuente_meta,
        fill=paleta["meta"],
    )

    # Separador de fecha dentro de la conversación.
    contenido_arriba = barra_alto + encabezado_alto
    contenido_abajo = alto - campo_alto
    dibujo.text(
        (ancho // 2 - round(22 * escala), contenido_arriba + round(14 * escala)),
        "HOY",
        font=fuente_meta,
        fill=paleta["meta"],
    )

    margen = round(26 * escala)
    ancho_burbuja_max = int(ancho * 0.68)
    y = contenido_arriba + round(52 * escala)
    for indice, (mensaje, saliente) in enumerate(zip(mensajes, salientes, strict=True)):
        fuente_burbuja = fuente
        lineas = _envolver(dibujo, mensaje, fuente_burbuja, ancho_burbuja_max - 36)
        ancho_texto = max(dibujo.textlength(linea, font=fuente_burbuja) for linea in lineas)
        ancho_burbuja = int(ancho_texto) + 36
        x = ancho - margen - ancho_burbuja if saliente else margen
        y = _dibujar_burbuja(
            dibujo,
            mensaje,
            x=x,
            y=y,
            ancho_max=ancho_burbuja_max - 36,
            fuente=fuente_burbuja,
            fuente_meta=fuente_meta,
            relleno=paleta["burbuja_salida"] if saliente else paleta["burbuja_entrada"],
            tinta=paleta["texto_salida"] if saliente else paleta["texto_entrada"],
            meta=paleta["meta"],
            hora=f"12:{34 + indice:02d}",
        ) + round(24 * escala)

    # Campo de escritura: fuera de la caja de conversación.
    campo_y = alto - campo_alto
    dibujo.rectangle((0, campo_y, ancho, alto), fill=paleta["barra"])
    dibujo.rounded_rectangle(
        (
            round(16 * escala),
            campo_y + round(campo_alto * 0.18),
            ancho - round(70 * escala),
            alto - round(campo_alto * 0.18),
        ),
        radius=20,
        fill=paleta["campo"],
    )
    dibujo.text(
        (round(34 * escala), campo_y + round(campo_alto * 0.32)),
        "Escribe un mensaje",
        font=fuente_meta,
        fill=paleta["meta"],
    )
    centro = (ancho - round(38 * escala), campo_y + round(campo_alto * 0.5))
    dibujo.ellipse(
        (
            centro[0] - round(16 * escala),
            centro[1] - round(16 * escala),
            centro[0] + round(16 * escala),
            centro[1] + round(16 * escala),
        ),
        fill=paleta["burbuja_salida"],
    )

    recorte = (
        0.0,
        contenido_arriba / alto,
        1.0,
        contenido_abajo / alto,
    )
    return imagen, recorte


def generar(salida: Path, cantidad: int) -> Path:
    capturas = salida / "capturas"
    capturas.mkdir(parents=True, exist_ok=True)
    aleatorio = random.Random(SEMILLA)
    manifiesto = salida / "referencias.jsonl"
    resoluciones = [RESOLUCIONES[indice % len(RESOLUCIONES)] for indice in range(cantidad)]
    aleatorio.shuffle(resoluciones)

    registros: list[dict] = []
    for indice in range(cantidad):
        modo = MODOS[indice % len(MODOS)]
        resolucion_texto = resoluciones[indice]
        app = APPS[(indice // 4) % len(APPS)]
        ancho, alto = (int(valor) for valor in resolucion_texto.split("x"))

        mensajes = aleatorio.sample(MENSAJES, 2)
        salientes = [aleatorio.random() < 0.5 for _ in mensajes]
        imagen, recorte = _renderizar(
            modo=modo,
            app=app,
            resolucion=(ancho, alto),
            mensajes=mensajes,
            salientes=salientes,
        )

        identificador = f"captura-{indice + 1:03d}"
        archivo = capturas / f"{identificador}.png"
        imagen.save(archivo, format="PNG", optimize=True)

        registros.append(
            {
                "id": identificador,
                "archivo": archivo.relative_to(salida).as_posix(),
                "texto": "\n".join(mensajes),
                "mensajes": mensajes,
                "modo": modo,
                "resolucion": resolucion_texto,
                "app": app,
                "recorte": list(recorte),
            }
        )

    with manifiesto.open("w", encoding="utf-8", newline="\n") as archivo_jsonl:
        for registro in registros:
            archivo_jsonl.write(json.dumps(registro, ensure_ascii=False) + "\n")

    return manifiesto


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera capturas sintéticas para el OCR.")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_OMISION)
    parser.add_argument("--cantidad", type=int, default=60)
    argumentos = parser.parse_args()

    if argumentos.cantidad < 50:
        parser.error("Se requieren al menos 50 capturas para la evaluación de la Fase 4.")

    manifiesto = generar(argumentos.salida, argumentos.cantidad)
    print(f"Capturas generadas en {argumentos.salida}")
    print(f"Manifiesto: {manifiesto}")


if __name__ == "__main__":
    main()
