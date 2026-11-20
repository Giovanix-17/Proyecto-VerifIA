"""Pruebas estáticas de la interfaz (Fase 7).

Complementan ``test_api.py`` y la prueba E2E de ``scripts/e2e_interfaz.py``:
aquí se vigilan los invariantes de accesibilidad y privacidad que no dependen
de un navegador (etiquetas, regiones vivas, foco visible, movimiento reducido
y ausencia de CDNs externos). La comprobación visual y de teclado se hace con
Playwright contra el servidor en marcha.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"


def _texto(nombre: str) -> str:
    return (WEB / nombre).read_text(encoding="utf-8")


def test_html_declaracion_de_idioma_y_salto_de_contenido() -> None:
    html = _texto("index.html")
    assert 'lang="es"' in html
    assert 'class="salto"' in html
    assert 'href="#contenido"' in html
    assert 'id="contenido"' in html


def test_campos_tienen_etiqueta_asociada() -> None:
    html = _texto("index.html")
    for identificador in ("mensaje", "texto-revision", "captura"):
        assert f'id="{identificador}"' in html
        assert f'for="{identificador}"' in html


def test_regiones_vivas_para_errores_espera_y_resultado() -> None:
    html = _texto("index.html")
    assert 'id="avisos"' in html and 'role="alert"' in html
    assert 'id="paso-3"' in html and 'aria-live="polite"' in html
    assert 'id="paso-4"' in html and 'aria-live="polite"' in html
    assert 'id="avisos-ocr"' in html and 'aria-live="polite"' in html


def test_privacidad_y_aviso_orientativo_visibles() -> None:
    html = _texto("index.html")
    assert "enmascaramos tus datos" in html.lower()
    assert "no guardamos" in html.lower()
    assert "orientativa" in html.lower()
    assert "servicio externo" in html.lower()


def test_no_se_bloquea_el_zoom_ni_se_cargan_recursos_externos() -> None:
    html = _texto("index.html")
    assert "user-scalable=no" not in html
    assert "maximum-scale=1" not in html
    # El prototipo funciona sin red para la interfaz: nada de CDNs.
    assert "cdn." not in html.lower()


def test_css_foco_visible_movimiento_reducido_y_objetivos_tactiles() -> None:
    css = _texto("estilos.css")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "min-height: 48px" in css
    assert "transition: all" not in css
    assert "outline: none" not in css


def test_js_gestiona_foco_y_estado_de_carga() -> None:
    js = _texto("app.js")
    assert "aria-busy" in js
    assert "ui.secciones[3].focus()" in js
    assert "ui.veredicto.focus()" in js
    # El contenido dinámico se escapa antes de inyectarse.
    assert "const escapar" in js
    assert "escapar(" in js
