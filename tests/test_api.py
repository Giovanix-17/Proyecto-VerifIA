"""Pruebas de la API (Fase 7).

Casos exigidos por la skill ``verifia-api-docker``:

* texto válido, texto vacío, texto de 10 001 caracteres;
* imagen válida, imagen > 5 MB, formato no soportado;
* 429 al superar el límite de frecuencia;
* ``fuente_diccionario="nivel_1_fallback"`` cuando el LLM falla (mock);
* ningún log contiene el texto de entrada (caplog).

Los casos con OCR se omiten si el entorno no tiene Tesseract con ``spa``
(misma convención que ``test_ocr.py``). El modelo del Nivel 1 y el
sanitizador reales se usan en la prueba de análisis de extremo a extremo;
el LLM nunca se llama de verdad (sin ``NVIDIA_API_KEY`` en las pruebas o
cliente mockeado).
"""

from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace

import pytest
from openai import APIConnectionError
from PIL import Image, ImageDraw, ImageFont

from verifia.api import main as api_main
from verifia.api.limites import LimiteFrecuencia
from verifia.classifier.cascade import CascadeVerifIA
from verifia.ocr import disponibilidad
from verifia.schemas import TIPOLOGIAS

TEXTO_FRAUDE = (
    "BANCOMEX: su cuenta sera bloqueada HOY. Confirme su codigo en "
    "http://banco-verify.com/acceso o llame al 55 1234 5678"
)
TELEFONO_REAL = "55 1234 5678"


# --------------------------------------------------------------------------- #
# Ayudas
# --------------------------------------------------------------------------- #
def _fuente(tamano: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    from pathlib import Path

    candidatas = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for ruta in candidatas:
        if ruta.is_file():
            return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(size=tamano)


def _render_captura(lineas: list[str]) -> bytes:
    """Captura sintética PNG con texto claro (mismo enfoque que test_ocr)."""
    imagen = Image.new("RGB", (900, 400), (233, 226, 218))
    dibujo = ImageDraw.Draw(imagen)
    fuente = _fuente(30)
    y = 60
    for linea in lineas:
        ancho, alto = dibujo.textbbox((0, 0), linea, font=fuente)[2:]
        dibujo.rounded_rectangle(
            (30, y, min(870, 30 + ancho + 50), y + alto + 36),
            radius=14,
            fill=(255, 255, 255),
        )
        dibujo.text((55, y + 18), linea, font=fuente, fill=(22, 22, 22))
        y += alto + 64
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


class _ModeloFalso:
    """Probabilidades fijas (misma técnica que test_cascade)."""

    def __init__(self, proba: list[float]) -> None:
        import numpy as np

        self.proba = np.array(proba)
        self.classes_ = list(TIPOLOGIAS)

    def predict_proba(self, _registros):  # noqa: ANN001, ANN202
        return [self.proba]


class _ClienteExplosivo:
    """Cliente del LLM que siempre falla con un error de conexión."""

    @property
    def chat(self):  # noqa: ANN201
        return self

    @property
    def completions(self):  # noqa: ANN201
        return self

    def create(self, **_kwargs):  # noqa: ANN001, ANN202
        raise APIConnectionError(request=None)


@pytest.fixture()
def cliente():
    """Cliente de pruebas con límite generoso y sin estado residual."""
    from fastapi.testclient import TestClient as _Cliente

    api_main.app.state.limite = LimiteFrecuencia(maximo=1000, ventana_s=60)
    return _Cliente(api_main.app)


# --------------------------------------------------------------------------- #
# Sistema
# --------------------------------------------------------------------------- #
def test_health(cliente) -> None:
    respuesta = cliente.get("/health")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["version"]


def test_inicio_sirve_la_interfaz(cliente) -> None:
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert "VerifIA" in respuesta.text
    assert "Analizar mensaje" in respuesta.text


def test_estaticos_css_y_js_disponibles(cliente) -> None:
    for ruta, tipo in (
        ("/static/estilos.css", "text/css"),
        ("/static/app.js", "javascript"),
    ):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200
        assert tipo in respuesta.headers["content-type"]


# --------------------------------------------------------------------------- #
# Texto: límites de entrada
# --------------------------------------------------------------------------- #
def test_texto_vacio_rechazado(cliente) -> None:
    respuesta = cliente.post("/api/analizar/texto", json={"texto": "   "})
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "texto_vacio"


def test_texto_de_10001_caracteres_rechazado(cliente) -> None:
    respuesta = cliente.post("/api/analizar/texto", json={"texto": "a" * 10_001})
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "texto_muy_largo"
    assert "10 000" in cuerpo["detail"]


def test_cuerpo_invalido_devuelve_422_consistente(cliente) -> None:
    respuesta = cliente.post("/api/analizar/texto", data=b"{no es json")
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "entrada_invalida"
    assert cuerpo["detail"]


# --------------------------------------------------------------------------- #
# Texto: análisis de extremo a extremo (Nivel 1 real, sin LLM)
# --------------------------------------------------------------------------- #
def test_analisis_texto_completo(cliente) -> None:
    respuesta = cliente.post("/api/analizar/texto", json={"texto": TEXTO_FRAUDE})
    assert respuesta.status_code == 200
    r = respuesta.json()

    # Contrato mínimo de la respuesta (§8.6 + skill).
    assert r["tipologia"] in TIPOLOGIAS
    assert r["nivel_riesgo"] in {"bajo", "medio", "alto"}
    assert 0 <= r["puntuacion"] <= 100
    assert isinstance(r["senales_alerta"], list)
    assert isinstance(r["recomendaciones"], list) and len(r["recomendaciones"]) >= 3
    assert r["fuente_diccionario"] in {"nivel_1", "nivel_2", "nivel_1_fallback"}
    assert isinstance(r["escalado_a_llm"], bool)
    assert isinstance(r["discrepancia_niveles"], bool)
    assert r["aviso"]
    assert r["resumen_legible"]

    # Sanitización antes de clasificar (regla 1): el teléfono no sobrevive.
    assert TELEFONO_REAL not in r["texto_analizado"]
    assert "[TELEFONO]" in r["texto_analizado"]
    # El enlace se reduce a dominio (regla 4): la ruta no viaja.
    assert "/acceso" not in r["texto_analizado"]
    assert "[ENLACE:banco-verify.com]" in r["texto_analizado"]
    # El detalle de diagnóstico no contiene el mensaje (regla 2).
    assert TEXTO_FRAUDE not in json.dumps(r["detalle"], ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Fallback cuando el LLM falla (mock, regla 8)
# --------------------------------------------------------------------------- #
def test_fallback_cuando_llm_falla(cliente, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "1")
    monkeypatch.setenv("LLM_RETRY_BASE_S", "0")
    cascada = CascadeVerifIA(
        _ModeloFalso([0.50, 0.20, 0.10, 0.10, 0.10]),  # zona gris: 0.50 < 0.75
        _ClienteExplosivo(),
        ejemplos=[],
    )
    estado_falso = SimpleNamespace(version="prueba", cascada=cascada)
    monkeypatch.setattr(api_main.app.state, "servicio", estado_falso, raising=False)

    respuesta = cliente.post("/api/analizar/texto", json={"texto": TEXTO_FRAUDE})
    assert respuesta.status_code == 200
    r = respuesta.json()
    assert r["fuente_diccionario"] == "nivel_1_fallback"
    assert r["escalado_a_llm"] is True
    assert any("parcial" in aviso.lower() for aviso in r["advertencias"])


# --------------------------------------------------------------------------- #
# Imagen: límites y OCR
# --------------------------------------------------------------------------- #
def test_imagen_formato_no_soportado(cliente) -> None:
    respuesta = cliente.post(
        "/api/analizar/imagen",
        files={"imagen": ("captura.gif", b"GIF89a" + b"\x00" * 100, "image/gif")},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "formato_no_soportado"


def test_imagen_mayor_a_5_mb_rechazada(cliente) -> None:
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024)
    respuesta = cliente.post(
        "/api/analizar/imagen",
        files={"imagen": ("captura.png", grande, "image/png")},
    )
    assert respuesta.status_code == 413
    assert respuesta.json()["codigo"] == "imagen_demasiado_grande"


def test_imagen_vacia_rechazada(cliente) -> None:
    respuesta = cliente.post(
        "/api/analizar/imagen",
        files={"imagen": ("captura.png", b"", "image/png")},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "imagen_vacia"


@requiere_ocr
def test_imagen_valida_devuelve_texto_para_revision(cliente) -> None:
    png = _render_captura(["Su cuenta sera bloqueada", "Confirme su codigo hoy"])
    respuesta = cliente.post(
        "/api/analizar/imagen",
        files={"imagen": ("captura.png", png, "image/png")},
    )
    assert respuesta.status_code == 200
    r = respuesta.json()
    assert "texto_extraido" in r
    assert len(r["texto_extraido"]) >= 10
    assert r["ancho"] >= 1 and r["alto"] >= 1
    assert isinstance(r["advertencias"], list)
    # El endpoint de imagen no clasifica: no trae campos del dictamen.
    assert "tipologia" not in r


# --------------------------------------------------------------------------- #
# Límite de frecuencia (429 + Retry-After)
# --------------------------------------------------------------------------- #
def test_429_al_superar_el_limite(cliente, monkeypatch) -> None:
    monkeypatch.setattr(
        api_main.app.state,
        "limite",
        LimiteFrecuencia(maximo=2, ventana_s=60),
        raising=False,
    )
    for _ in range(2):
        respuesta = cliente.post("/api/analizar/texto", data=b"{mal")
        assert respuesta.status_code == 422  # el límite cuenta toda petición
    respuesta = cliente.post("/api/analizar/texto", data=b"{mal")
    assert respuesta.status_code == 429
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "demasiadas_solicitudes"
    assert int(respuesta.headers["retry-after"]) >= 1


def test_limite_se_reinicia_al_renovar_la_ventana() -> None:
    limite = LimiteFrecuencia(maximo=1, ventana_s=1)
    permitido, _ = limite.verificar("1.2.3.4")
    assert permitido
    permitido, espera = limite.verificar("1.2.3.4")
    assert not permitido and espera > 0


# --------------------------------------------------------------------------- #
# Sin contenido en los logs (invariante 3)
# --------------------------------------------------------------------------- #
def test_los_logs_no_contienen_el_mensaje(cliente, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        respuesta = cliente.post("/api/analizar/texto", json={"texto": TEXTO_FRAUDE})
    assert respuesta.status_code == 200
    assert TELEFONO_REAL not in caplog.text
    assert "banco-verify.com" not in caplog.text
