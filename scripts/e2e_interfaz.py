"""Pruebas E2E de la interfaz con Playwright (Fase 7).

Ejercita el flujo de 4 pasos contra un servidor en marcha (por defecto
``http://127.0.0.1:8000``, el de Docker; acepta ``--base-url``). Deja
capturas en ``docs/reportes/figuras/`` como evidencia para el reporte.

Casos (skill ``verifia-api-docker`` §5):

* flujo de 4 pasos con texto: entrada → revisión → análisis → veredicto;
* flujo con imagen: OCR → revisión del texto extraído → veredicto;
* el veredicto se comunica con icono + palabra, no solo con color;
* navegación por teclado y errores anunciados (``role="alert"``);
* sin scroll horizontal en escritorio y en móvil (390 px).

Uso::

    python scripts/e2e_interfaz.py [--base-url http://127.0.0.1:8000]

Requiere el servidor encendido (``docker compose up`` o uvicorn local) y
Playwright con Chromium: ``pip install playwright`` + ``python -m playwright
install chromium`` (una sola vez).
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

# La consola de Windows puede usar cp1252: sin esto, los símbolos ≥ — « » fallan.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
FIGURAS = RAIZ / "docs" / "reportes" / "figuras"

TEXTO_FRAUDE = (
    "BANCOMEX: su cuenta sera bloqueada HOY. Confirme su codigo en "
    "http://banco-verify.com/acceso o llame al 55 1234 5678"
)
LINEAS_CAPTURA = ["Su cuenta sera bloqueada hoy", "Confirme su codigo urgente"]
VEREDICTOS = ("Riesgo bajo", "Riesgo medio", "Riesgo alto")


def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidatas = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for ruta in candidatas:
        if ruta.is_file():
            return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(size=tamano)


def generar_captura(destino: Path) -> Path:
    """Captura sintética PNG con texto claro (misma técnica que la Fase 4)."""
    imagen = Image.new("RGB", (900, 360), (233, 226, 218))
    dibujo = ImageDraw.Draw(imagen)
    fuente = _fuente(30)
    y = 50
    for linea in LINEAS_CAPTURA:
        ancho, alto = dibujo.textbbox((0, 0), linea, font=fuente)[2:]
        dibujo.rounded_rectangle(
            (30, y, 30 + ancho + 50, y + alto + 36), radius=14, fill="white"
        )
        dibujo.text((55, y + 18), linea, font=fuente, fill=(22, 22, 22))
        y += alto + 70
    imagen.save(destino, format="PNG")
    return destino


def sin_scroll_horizontal(page) -> bool:
    return page.evaluate(
        "document.documentElement.scrollWidth <= window.innerWidth + 1"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    FIGURAS.mkdir(parents=True, exist_ok=True)
    captura_png = generar_captura(Path(tempfile.gettempdir()) / "verifia_e2e.png")

    fallos: list[str] = []

    def comprobar(nombre: str, condicion: bool, detalle: str = "") -> None:
        estado = "OK " if condicion else "FALLA"
        print(f"{estado} {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))
        if not condicion:
            fallos.append(nombre)

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)

        # ---------------- escritorio: flujo con texto ----------------
        pagina = navegador.new_page(viewport={"width": 1280, "height": 900})
        pagina.goto(base, wait_until="networkidle")

        comprobar(
            "paso 1 visible con título",
            pagina.locator("#paso-1 h1, .intro h1").first.is_visible(),
        )
        comprobar(
            "aviso de privacidad visible en el paso 1",
            pagina.locator(".privacidad").is_visible()
            and "enmascaramos" in pagina.locator(".privacidad").inner_text().lower(),
        )
        pagina.locator("#paso-1").screenshot(path=str(FIGURAS / "e2e_paso1_entrada.png"))

        pagina.fill("#mensaje", TEXTO_FRAUDE)
        pagina.click("#boton-paso1")
        pagina.wait_for_selector("#paso-2:not([hidden])", state="attached", timeout=10_000)
        texto_revision = pagina.input_value("#texto-revision")
        comprobar("paso 2 muestra el texto a revisar", TEXTO_FRAUDE in texto_revision)

        pagina.click("#boton-analizar")
        pagina.wait_for_selector("#paso-4:not([hidden])", state="attached", timeout=90_000)
        veredicto = pagina.locator("#veredicto").inner_text()
        comprobar(
            "paso 4 con veredicto (icono + palabra, no solo color)",
            any(v in veredicto for v in VEREDICTOS),
            veredicto[:80],
        )
        comprobar(
            "el foco pasa al veredicto al terminar",
            pagina.evaluate("document.activeElement?.id") == "veredicto",
        )
        comprobar(
            "clase de color presente además del texto",
            pagina.locator("#veredicto[class*='veredicto--']").count() == 1,
        )
        comprobar(
            "recomendaciones visibles (≥ 3)",
            pagina.locator(".recomendaciones li").count() >= 3,
        )
        comprobar("aviso orientativo presente", pagina.locator(".aviso-final").is_visible())

        pagina.locator("details summary").click()
        marcadores = pagina.locator(".texto-analizado mark").count()
        texto_enmascarado = pagina.locator(".texto-analizado").inner_text()
        comprobar("señales resaltadas sobre el texto", marcadores >= 1)
        comprobar(
            "texto mostrado ya enmascarado (sin PII)",
            "55 1234 5678" not in texto_enmascarado and "[TELEFONO]" in texto_enmascarado,
        )
        pagina.locator("#paso-4").screenshot(path=str(FIGURAS / "e2e_paso4_resultado.png"))

        comprobar("sin scroll horizontal (1280 px)", sin_scroll_horizontal(pagina))
        pagina.close()

        # ---------------- teclado y errores anunciados ----------------
        pagina = navegador.new_page(viewport={"width": 1280, "height": 900})
        pagina.goto(base, wait_until="networkidle")
        pagina.keyboard.press("Tab")
        primero = pagina.evaluate("document.activeElement?.textContent?.trim() || ''")
        comprobar(
            "primer foco: enlace para saltar al contenido",
            "Saltar al contenido" in primero,
            primero,
        )

        pagina.focus("#boton-paso1")
        pagina.keyboard.press("Enter")  # sin texto: debe fallar anunciando
        pagina.wait_for_selector("#avisos:not([hidden])", state="attached", timeout=5_000)
        comprobar(
            "error anunciado con role=alert",
            pagina.locator("#avisos[role='alert']").count() == 1
            and "Escribe el mensaje" in pagina.locator("#avisos").inner_text(),
        )
        comprobar(
            "el foco vuelve al campo con error",
            pagina.evaluate("document.activeElement?.id") == "mensaje",
        )
        pagina.close()

        # ---------------- flujo con imagen ----------------
        pagina = navegador.new_page(viewport={"width": 1280, "height": 900})
        pagina.goto(base, wait_until="networkidle")
        # El radio es invisible (patrón accesible): se activa con su etiqueta.
        pagina.locator(".modo-opcion").filter(has_text="Subir captura").click()
        pagina.set_input_files("#captura", str(captura_png))
        pagina.click("#boton-paso1")
        pagina.wait_for_selector("#paso-2:not([hidden])", state="attached", timeout=60_000)
        extraido = pagina.input_value("#texto-revision")
        comprobar(
            "OCR: el texto extraído llega al paso 2",
            "Su cuenta sera bloqueada" in extraido,
            extraido[:80],
        )
        pagina.click("#boton-analizar")
        pagina.wait_for_selector("#paso-4:not([hidden])", state="attached", timeout=90_000)
        comprobar(
            "flujo con imagen termina en veredicto",
            any(v in pagina.locator("#veredicto").inner_text() for v in VEREDICTOS),
        )
        comprobar("sin scroll horizontal tras la imagen", sin_scroll_horizontal(pagina))
        pagina.close()

        # ---------------- móvil (390 px) ----------------
        pagina = navegador.new_page(viewport={"width": 390, "height": 844})
        pagina.goto(base, wait_until="networkidle")
        comprobar("móvil: sin scroll horizontal (390 px)", sin_scroll_horizontal(pagina))
        alto_boton = pagina.locator("#boton-paso1").bounding_box()["height"]
        comprobar("botón principal ≥ 44 px", alto_boton >= 44, f"alto={alto_boton}")
        ancho_textarea = pagina.locator("#mensaje").bounding_box()["width"]
        comprobar("campo a todo el ancho útil", ancho_textarea >= 300, f"ancho={ancho_textarea}")
        pagina.screenshot(path=str(FIGURAS / "e2e_movil.png"), full_page=True)
        pagina.close()

        navegador.close()

    print()
    if fallos:
        print(f"E2E: {len(fallos)} casos fallaron: {', '.join(fallos)}")
        return 1
    print("E2E: todos los casos pasaron.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
