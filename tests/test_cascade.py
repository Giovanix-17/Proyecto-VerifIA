"""Pruebas de la cascada con modelos y clientes mockeados (skill, sin API).

Casos del §8.6:

1. Alta confianza → no se llama al LLM.
2. Zona gris + JSON válido → ``max(LLM, Nivel 1)`` y ``discrepancia_niveles``.
3. Zona gris + fallo del LLM → fallback con aviso de análisis parcial.
4. Sin cliente (sin API) → fallback para toda zona gris.
5. El texto del mensaje nunca se registra en los logs de metadatos.
"""

from __future__ import annotations

import numpy as np

from verifia.classifier.cascade import ADVERTENCIA_PARCIAL, CascadeVerifIA
from verifia.classifier.level2_llm import FalloLLM
from verifia.schemas import TIPOLOGIAS

TEXTO = "Su cuenta será bloqueada hoy. Ingrese su código en [ENLACE:banco-verify.com]"


class ModeloFalso:
    """Sustituye al modelo calibrado: probabilidades fijas por texto."""

    def __init__(self, proba: list[float]) -> None:
        self.proba = np.array(proba)
        self.classes_ = np.array(TIPOLOGIAS)
        self.llamadas = 0

    def predict_proba(self, registros):  # noqa: ANN001
        self.llamadas += 1
        return np.array([self.proba])


class ClienteFalso:
    """Sustituye al cliente de OpenAI."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.llamadas = 0

    @property
    def chat(self):  # noqa: ANN201
        return self

    @property
    def completions(self):  # noqa: ANN201
        return self

    def create(self, **_kwargs):  # noqa: ANN001, ANN202
        self.llamadas += 1
        eleccion = type("Eleccion", (), {})()
        eleccion.message = type("Mensaje", (), {"content": self.contenido})()
        eleccion.finish_reason = "stop"
        respuesta = type("Respuesta", (), {})()
        respuesta.choices = [eleccion]
        respuesta.usage = type("Uso", (), {"prompt_tokens": 10, "completion_tokens": 5})()
        return respuesta


def dictamen_llm(tipologia: str, puntuacion: int) -> str:
    nivel = "bajo" if puntuacion <= 33 else ("medio" if puntuacion <= 66 else "alto")
    frase = "Su cuenta será bloqueada hoy"
    return (
        f'{{"tipologia": "{tipologia}", "nivel_riesgo": "{nivel}", '
        f'"puntuacion": {puntuacion}, "senales_alerta": '
        f'[{{"frase": "{frase}", "motivo": "urgencia y amenaza"}}], '
        f'"justificacion": "Suplantación bancaria con amenaza de bloqueo."}}'
    )


def probar(  # noqa: ANN201
    proba_nivel1: list[float], cliente=None, contenido: str | None = None
):
    modelo = ModeloFalso(proba_nivel1)
    if cliente is None and contenido is not None:
        cliente = ClienteFalso(contenido)
    cascada = CascadeVerifIA(modelo, cliente, ejemplos=[])
    resultado = cascada.analizar(TEXTO)
    return modelo, cliente, resultado


# --------------------------------------------------------------------------- #
# 1. Alta confianza: el LLM no se llama
# --------------------------------------------------------------------------- #
def test_alta_confianza_no_escala() -> None:
    proba = [0.95, 0.02, 0.01, 0.01, 0.01]  # legítimo
    modelo, cliente, resultado = probar(proba, ClienteFalso(dictamen_llm("legitimo", 5)))
    assert cliente.llamadas == 0
    assert resultado.fuente_diccionario == "nivel_1"
    assert not resultado.escalado_a_llm
    assert not resultado.discrepancia_niveles
    # puntuacion = round(100*(1-0.95)) = 5
    assert resultado.puntuacion == 5
    assert resultado.nivel_riesgo == "bajo"
    assert modelo.llamadas == 1


def test_alta_confianza_fraude() -> None:
    proba = [0.02, 0.90, 0.03, 0.03, 0.02]  # suplantación
    _modelo, cliente, resultado = probar(
        proba, ClienteFalso(dictamen_llm("suplantacion_bancaria", 95))
    )
    assert cliente.llamadas == 0
    assert resultado.tipologia == "suplantacion_bancaria"
    assert resultado.puntuacion == 98
    assert resultado.nivel_riesgo == "alto"
    assert resultado.fuente_diccionario == "nivel_1"


# --------------------------------------------------------------------------- #
# 2. Zona gris con JSON válido
# --------------------------------------------------------------------------- #
def test_zona_gris_llm_valido_con_discrepancia() -> None:
    # prob_max = 0.70 < 0.75 (umbral por defecto del entorno) → zona gris.
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]
    contenido = dictamen_llm("suplantacion_bancaria", 60)
    _modelo, _cliente, resultado = probar(proba, None, contenido)
    assert resultado.fuente_diccionario == "nivel_2"
    assert resultado.escalado_a_llm
    # max(60, round(100*(1-0.30)) = 70) = 70 y hay discrepancia (LLM menor).
    # La puntuación 70 cae en la banda alta (67–100, §8.5).
    assert resultado.puntuacion == 70
    assert resultado.discrepancia_niveles
    assert resultado.nivel_riesgo == "alto"


def test_zona_gris_llm_con_riesgo_mayor() -> None:
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]
    contenido = dictamen_llm("suplantacion_bancaria", 90)
    _modelo, _cliente, resultado = probar(proba, None, contenido)
    assert resultado.puntuacion == 90
    assert resultado.nivel_riesgo == "alto"
    assert not resultado.discrepancia_niveles


# --------------------------------------------------------------------------- #
# 3. Zona gris con fallo del LLM → fallback (regla 8)
# --------------------------------------------------------------------------- #
def test_zona_gris_json_invalido_fallback() -> None:
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]
    _modelo, _cliente, resultado = probar(proba, None, "no soy json")
    assert resultado.fuente_diccionario == "nivel_1_fallback"
    assert resultado.escalado_a_llm
    assert any("parcial" in a for a in resultado.advertencias)
    assert resultado.puntuacion == 70  # puntuacion_nivel1
    assert not resultado.discrepancia_niveles


def test_zona_gris_timeout_fallback() -> None:
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]

    class ClienteTimeout(ClienteFalso):
        def create(self, **_kwargs):  # noqa: ANN202
            raise FalloLLM("timeout", "timeout simulado")

    _modelo, _cliente, resultado = probar(proba, ClienteTimeout("x"))
    assert resultado.fuente_diccionario == "nivel_1_fallback"
    assert ADVERTENCIA_PARCIAL in resultado.advertencias


# --------------------------------------------------------------------------- #
# 4. Sin cliente → toda zona gris es fallback
# --------------------------------------------------------------------------- #
def test_sin_cliente_fallback() -> None:
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]
    _modelo, _cliente, resultado = probar(proba, cliente=None)
    assert resultado.fuente_diccionario == "nivel_1_fallback"
    assert resultado.escalado_a_llm


# --------------------------------------------------------------------------- #
# 5. Privacidad: el texto no se guarda en el detalle ni en los logs
# --------------------------------------------------------------------------- #
def test_texto_no_queda_en_metadatos() -> None:
    proba = [0.30, 0.70, 0.0, 0.0, 0.0]
    _modelo, _cliente, resultado = probar(
        proba, None, dictamen_llm("suplantacion_bancaria", 60)
    )
    detalle_str = str(resultado.detalle)
    assert "bloqueada" not in detalle_str
    assert "banco-verify" not in detalle_str
