"""Pruebas del Nivel 2: extracción de JSON, esquema y verificación de señales.

No hacen llamadas de red: solo la lógica local (skill ``verifia-nivel2-llm``,
"Pruebas sin gastar API").
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from verifia.classifier.level2_llm import (
    construir_mensajes,
    extraer_json,
    verificar_senales,
)
from verifia.schemas import DictamenLLM, banda_de_riesgo

TEXTO = "Su cuenta será bloqueada hoy. Ingrese su código en [ENLACE:banco-verify.com]"


# --------------------------------------------------------------------------- #
# extraer_json
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "crudo,esperado",
    [
        ('{"tipologia": "extorsion"}', {"tipologia": "extorsion"}),
        (
            "Pienso... el mensaje es de fraude.\n```json\n"
            '{"tipologia": "extorsion", "puntuacion": 90}\n```',
            {"tipologia": "extorsion", "puntuacion": 90},
        ),
        (
            '{"a": "llaves en cadena { no cuentan"}',
            {"a": "llaves en cadena { no cuentan"},
        ),
        (
            '{"a": {"b": 1}, "c": 2}',
            {"a": {"b": 1}, "c": 2},
        ),
        (
            '{"tipologia": "extorsion"} texto sobrante {"otra": 1}',
            {"tipologia": "extorsion"},
        ),
        (
            'razonamiento previo {"a": 1}',
            {"a": 1},
        ),
    ],
)
def test_extraer_json_casos_validos(crudo: str, esperado: dict) -> None:
    assert extraer_json(crudo) == esperado


@pytest.mark.parametrize(
    "crudo",
    [
        "no hay json aquí",
        '{"tipologia": "extorsion", "incompleto": ',  # truncado
        '{"a": "cadena sin cerrar}',
        "[]",  # no es objeto
    ],
)
def test_extraer_json_casos_invalidos(crudo: str) -> None:
    from verifia.classifier.level2_llm import FalloLLM

    with pytest.raises(FalloLLM) as exc:
        extraer_json(crudo)
    assert exc.value.motivo == "json_invalido"


# --------------------------------------------------------------------------- #
# DictamenLLM (esquema §8.4)
# --------------------------------------------------------------------------- #
DICTAMEN_OK = {
    "tipologia": "suplantacion_bancaria",
    "nivel_riesgo": "alto",
    "puntuacion": 92,
    "senales_alerta": [
        {"frase": "Su cuenta será bloqueada hoy", "motivo": "urgencia y amenaza"}
    ],
    "justificacion": "Suplanta a un banco y presiona para entregar un código.",
}


def test_dictamen_valido() -> None:
    dictamen = DictamenLLM.model_validate(DICTAMEN_OK)
    assert dictamen.puntuacion == 92
    assert dictamen.senales_alerta[0].frase.startswith("Su cuenta")


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("tipologia", "otra_clase"),  # tipología inventada
        ("nivel_riesgo", "critico"),  # nivel fuera del catálogo
        ("puntuacion", 150),  # fuera de rango
        ("puntuacion", -1),
    ],
)
def test_dictamen_campos_invalidos(campo: str, valor) -> None:
    datos = dict(DICTAMEN_OK)
    datos[campo] = valor
    with pytest.raises(ValidationError):
        DictamenLLM.model_validate(datos)


def test_dictamen_justificacion_vacia() -> None:
    datos = dict(DICTAMEN_OK, justificacion="   ")
    with pytest.raises(ValidationError):
        DictamenLLM.model_validate(datos)


@pytest.mark.parametrize(
    "puntuacion,nivel",
    [(10, "bajo"), (50, "medio"), (90, "alto")],
)
def test_bandas_coherentes(puntuacion: int, nivel: str) -> None:
    datos = dict(DICTAMEN_OK, puntuacion=puntuacion, nivel_riesgo=nivel)
    DictamenLLM.model_validate(datos)


def test_banda_incoherente_se_rechaza() -> None:
    # §8.4: si nivel_riesgo no coincide con la banda de la puntuación, la
    # salida se descarta (es lo que dispara el fallback en la cascada).
    datos = dict(DICTAMEN_OK, puntuacion=10, nivel_riesgo="alto")
    with pytest.raises(ValidationError):
        DictamenLLM.model_validate(datos)


def test_banda_de_riesgo_semaforo() -> None:
    assert banda_de_riesgo(0) == "bajo"
    assert banda_de_riesgo(33) == "bajo"
    assert banda_de_riesgo(34) == "medio"
    assert banda_de_riesgo(66) == "medio"
    assert banda_de_riesgo(67) == "alto"
    assert banda_de_riesgo(100) == "alto"


# --------------------------------------------------------------------------- #
# Verificación de señales (post-Pydantic)
# --------------------------------------------------------------------------- #
def test_senal_verificada_y_descartada() -> None:
    dictamen = DictamenLLM.model_validate(
        {
            "tipologia": "suplantacion_bancaria",
            "nivel_riesgo": "alto",
            "puntuacion": 90,
            "senales_alerta": [
                {"frase": "Su cuenta será bloqueada hoy", "motivo": "urgencia"},
                {"frase": "esta frase NO está en el mensaje", "motivo": "alucinación"},
            ],
            "justificacion": "Suplantación bancaria con amenaza de bloqueo.",
        }
    )
    limpio, descartadas = verificar_senales(dictamen, TEXTO)
    assert len(limpio.senales_alerta) == 1
    assert descartadas == ["esta frase NO está en el mensaje"]


def test_fraude_sin_senales_verificadas_se_rechaza() -> None:
    from verifia.classifier.level2_llm import FalloLLM

    dictamen = DictamenLLM.model_validate(
        {
            "tipologia": "extorsion",
            "nivel_riesgo": "alto",
            "puntuacion": 90,
            "senales_alerta": [
                {"frase": "frase alucinada que no existe", "motivo": "inventada"}
            ],
            "justificacion": "Amenaza directa para exigir dinero.",
        }
    )
    with pytest.raises(FalloLLM) as exc:
        verificar_senales(dictamen, TEXTO)
    assert exc.value.motivo == "senal_no_verificada"


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def test_prompt_mensaje_en_user_no_en_system() -> None:
    mensajes = construir_mensajes(
        TEXTO, ejemplos=[{"texto": "ejemplo train", "tipologia": "legitimo"}]
    )
    assert len(mensajes) == 2
    system, user = mensajes[0], mensajes[1]
    assert TEXTO not in system["content"]
    assert f"<mensaje>{TEXTO}</mensaje>" == user["content"]
    assert "DATOS" in system["content"]  # defensa de inyección
    assert "ejemplo train" in system["content"]  # few-shot de train
