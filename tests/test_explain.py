"""Pruebas del módulo de explicabilidad (Fase 6).

Cubren los criterios de la skill ``verifia-explicabilidad``:

1. semáforo derivado de la puntuación y con texto + icono;
2. snapshots del resumen para 5 tipologías × 3 estados;
3. determinismo;
4. catálogo de recomendaciones sin datos inventados;
5. aviso orientativo en el 100 % de las respuestas, incluido el fallback;
6. máximo 5 señales y frases presentes en el texto;
7. extracción de términos del Nivel 1 (Naive Bayes y calibrado).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from sklearn.calibration import CalibratedClassifierCV
from sklearn.naive_bayes import MultinomialNB

from verifia.classifier.level1 import construir_pipeline, preparar_registro
from verifia.explain import (
    ADVERTENCIA_PARCIAL,
    AVISO,
    GENERALES,
    explicar,
    extraer_terminos,
    localizar_frase,
    recomendaciones,
    semaforo,
    senales_desde_marcadores,
    senales_nivel1,
)
from verifia.schemas import (
    TIPOLOGIAS,
    Explicacion,
    ResultadoClasificacion,
    Senal,
)

SNAPSHOT = Path(__file__).parent / "fixtures" / "explicaciones_snapshot.json"

TEXTO_FRAUDE = (
    "Su cuenta será bloqueada hoy. Ingrese su código en "
    "[ENLACE:banco-verify.com]"
)


# --------------------------------------------------------------------------- #
# Semáforo y coherencia del esquema
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "puntuacion,estado,nivel",
    [
        (0, "verde", "bajo"),
        (33, "verde", "bajo"),
        (34, "amarillo", "medio"),
        (66, "amarillo", "medio"),
        (67, "rojo", "alto"),
        (100, "rojo", "alto"),
    ],
)
def test_semaforo_limites(puntuacion: int, estado: str, nivel: str) -> None:
    datos = semaforo(puntuacion)
    assert datos["estado"] == estado
    assert datos["nivel_riesgo"] == nivel
    assert datos["titulo"] == f"Riesgo {nivel}"
    assert datos["icono"]
    assert datos["descripcion"]
    assert datos["accion"]


def _explicacion_valida() -> dict:
    return explicar(
        texto=TEXTO_FRAUDE,
        tipologia="suplantacion_bancaria",
        puntuacion=90,
    ).model_dump()


def test_explicacion_rechaza_estado_incoherente() -> None:
    datos = _explicacion_valida()
    datos["estado"] = "verde"
    datos["nivel_riesgo"] = "alto"
    with pytest.raises(ValidationError):
        Explicacion.model_validate(datos)


def test_resultado_rechaza_puntuacion_incoherente() -> None:
    datos = _explicacion_valida()
    with pytest.raises(ValidationError):
        ResultadoClasificacion(
            tipologia="suplantacion_bancaria",
            puntuacion=10,  # verde, pero los datos dicen rojo
            justificacion="prueba",
            fuente_diccionario="nivel_1",
            **datos,
        )


# --------------------------------------------------------------------------- #
# Snapshot del resumen
# --------------------------------------------------------------------------- #
def test_snapshot_resumen_15_casos() -> None:
    esperado = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for tipologia in TIPOLOGIAS:
        for puntuacion, banda in ((10, "bajo"), (50, "medio"), (90, "alto")):
            explicacion = explicar(
                texto="Mensaje de prueba",
                tipologia=tipologia,
                puntuacion=puntuacion,
            )
            assert explicacion.resumen_legible == esperado[tipologia][banda], (
                tipologia,
                banda,
            )


def test_determinismo() -> None:
    argumentos = dict(
        texto=TEXTO_FRAUDE,
        tipologia="suplantacion_bancaria",
        puntuacion=90,
    )
    primera = explicar(**argumentos).model_dump()
    segunda = explicar(**argumentos).model_dump()
    assert primera == segunda


# --------------------------------------------------------------------------- #
# Catálogo y aviso
# --------------------------------------------------------------------------- #
def test_catalogo_sin_datos_inventados() -> None:
    for tipologia in TIPOLOGIAS:
        recs = recomendaciones(tipologia)
        assert 3 <= len(recs) <= 6
        for recomendacion in recs:
            texto = recomendacion.lower()
            assert "http" not in texto
            assert "www." not in texto
            assert "@" not in texto
            # El 911 es la única cifra permitida; ninguna secuencia de 8+
            # dígitos puede colarse como teléfono o cuenta inventada.
            assert re.search(r"\d{8,}", recomendacion.replace("911", "")) is None
        assert GENERALES[0] in recs
        assert GENERALES[1] in recs


@pytest.mark.parametrize("fuente", ["nivel_1", "nivel_2", "nivel_1_fallback"])
def test_aviso_siempre_presente(fuente: str) -> None:
    for tipologia in TIPOLOGIAS:
        explicacion = explicar(
            texto=TEXTO_FRAUDE,
            tipologia=tipologia,
            puntuacion=50,
            senales_llm=[],
            fuente=fuente,
        )
        assert explicacion.aviso == AVISO
        assert explicacion.recomendaciones
        if fuente == "nivel_1_fallback":
            assert ADVERTENCIA_PARCIAL in explicacion.advertencias


# --------------------------------------------------------------------------- #
# Señales
# --------------------------------------------------------------------------- #
def test_maximo_cinco_senales_con_span_valido() -> None:
    frases = [
        "Su cuenta",
        "bloqueada",
        "hoy",
        "Ingrese",
        "código",
        "[ENLACE:banco-verify.com]",
        "cuenta",
    ]
    senales = [Senal(frase=frase, motivo="motivo de prueba") for frase in frases]
    explicacion = explicar(
        texto=TEXTO_FRAUDE,
        tipologia="suplantacion_bancaria",
        puntuacion=90,
        senales_llm=senales,
    )
    assert len(explicacion.senales_alerta) <= 5
    assert explicacion.senales_alerta
    for senal in explicacion.senales_alerta:
        assert senal.frase in TEXTO_FRAUDE
        assert senal.origen == "nivel_2"
        assert senal.inicio is not None and senal.fin is not None
        assert TEXTO_FRAUDE[senal.inicio : senal.fin] == senal.frase


def test_senal_alucinada_se_descarta() -> None:
    explicacion = explicar(
        texto=TEXTO_FRAUDE,
        tipologia="extorsion",
        puntuacion=90,
        senales_llm=[Senal(frase="frase que no existe", motivo="inventada")],
    )
    assert explicacion.senales_alerta == []


def test_localizar_frase_ignora_acentos_y_mayusculas() -> None:
    span = localizar_frase("Su CUENTA será bloqueáda hoy", "cuenta sera bloqueada")
    assert span is not None
    assert "CUENTA" in "Su CUENTA será bloqueáda hoy"[span[0] : span[1]]


def test_localizar_termino_dentro_de_marcador() -> None:
    texto = "Ingrese [ENLACE:bit.ly] ahora"
    span = localizar_frase(texto, "bit")
    assert span is not None
    assert texto[span[0] : span[1]] == "[ENLACE:bit.ly]"


def test_marcadores_solo_senales_utiles() -> None:
    texto = (
        "Ingrese [CODIGO] en [ENLACE:bit.ly] o llame al [TELEFONO] "
        "o escriba a [CORREO]"
    )
    senales = senales_desde_marcadores(texto)
    assert [senal.categoria for senal in senales] == [
        "solicitud_codigo",
        "enlace_sospechoso",
    ]
    assert all(senal.frase in texto for senal in senales)


def test_nivel1_no_alerta_en_verde() -> None:
    assert senales_nivel1("Ingrese [CODIGO]", None, "suplantacion_bancaria", 20) == []


def test_nivel1_legitimo_solo_conserva_marcadores() -> None:
    texto = "Su pedido [TELEFONO] llegó. Código [CODIGO]."
    senales = senales_nivel1(texto, None, "legitimo", 50)
    assert [senal.frase for senal in senales] == ["[CODIGO]"]


# --------------------------------------------------------------------------- #
# Términos del Nivel 1
# --------------------------------------------------------------------------- #
def _datos_nivel1() -> tuple[list[dict], list[str]]:
    fraudes = [
        "Su cuenta será bloqueada hoy ingrese su código",
        "Banco le informa bloqueo de cuenta confirme código",
        "Ingrese código para desbloquear su cuenta",
        "Su tarjeta será bloqueada confirme el código",
    ]
    legitimos = [
        "Pedido entregado gracias por su compra",
        "Hola mamá ya llegué bien",
        "Su paquete fue entregado en su domicilio",
        "Gracias por su compra vuelva pronto",
    ]
    textos = fraudes + legitimos
    etiquetas = ["suplantacion_bancaria"] * len(fraudes) + ["legitimo"] * len(
        legitimos
    )
    return [preparar_registro(texto) for texto in textos], etiquetas


def test_extraer_terminos_naive_bayes() -> None:
    registros, etiquetas = _datos_nivel1()
    pipeline = construir_pipeline(MultinomialNB(alpha=0.1))
    pipeline.fit(registros, etiquetas)
    terminos = extraer_terminos(
        pipeline,
        "Su cuenta será bloqueada hoy ingrese su código",
        "suplantacion_bancaria",
    )
    assert terminos
    assert any(termino in {"bloqueada", "codigo", "cuenta"} for termino in terminos)


def test_extraer_terminos_modelo_calibrado() -> None:
    registros, etiquetas = _datos_nivel1()
    base = construir_pipeline(MultinomialNB(alpha=0.1))
    calibrado = CalibratedClassifierCV(base, method="sigmoid", cv=2)
    calibrado.fit(registros, etiquetas)
    terminos = extraer_terminos(
        calibrado,
        "Su cuenta será bloqueada hoy ingrese su código",
        "suplantacion_bancaria",
    )
    assert terminos
    assert "bloqueada" in terminos or "codigo" in terminos


def test_extraer_terminos_modelo_sin_soporte() -> None:
    assert extraer_terminos(np.array([1, 2]), "texto", "legitimo") == []
