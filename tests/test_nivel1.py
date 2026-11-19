"""Pruebas del Nivel 1: rasgos estructurales y pipeline con datos mínimos.

No cargan el modelo entrenado (eso es un artefacto del entrenamiento); se
prueba la lógica de construcción de características y que el pipeline
entrena y predice probabilidades sobre datos sintéticos pequeños.
"""

from __future__ import annotations

import numpy as np

from verifia.classifier.level1 import (
    CANDIDATOS,
    construir_pipeline,
    nivel_riesgo_de_puntuacion,
    preparar_registro,
    puntuacion_nivel1,
    rasgos_estructurales,
)
from verifia.schemas import TIPOLOGIAS


def test_preparar_registro_marcadores() -> None:
    registro = preparar_registro(
        "Llama al [TELEFONO] o entra a [ENLACE:bit.ly] con tu [CODIGO]",
        marcadores={"[TELEFONO]": 1, "[CODIGO]": 1},
        rasgos_enlace=[{"es_acortador": True, "ip_literal": False, "num_subdominios": 1,
                        "tld_sospechoso": False, "guiones_en_host": 0, "tiene_puerto": False}],
    )
    rasgos = registro["estructurales"]
    assert rasgos["marcador_telefono"] == 1
    assert rasgos["marcador_codigo"] == 1
    assert rasgos["enlace_acortador"] == 1
    assert rasgos["num_enlaces"] == 1


def test_rasgos_estructurales_sin_entrada() -> None:
    registro = {"texto": "", "marcadores": {}, "rasgos_enlace": []}
    rasgos = rasgos_estructurales(registro)
    assert rasgos["longitud_caracteres"] == 0
    assert rasgos["proporcion_mayusculas"] == 0
    assert rasgos["num_enlaces"] == 0


def test_puntuacion_y_banda() -> None:
    proba = np.array([0.30, 0.70, 0.0, 0.0, 0.0])
    # round(100 * (1 - 0.30)) = 70 (§8.6)
    assert puntuacion_nivel1(proba) == 70
    assert nivel_riesgo_de_puntuacion(70) == "alto"
    assert nivel_riesgo_de_puntuacion(50) == "medio"
    assert nivel_riesgo_de_puntuacion(10) == "bajo"


def _datos_minimos() -> tuple[list[dict], list[str]]:
    fraude = (
        "Su cuenta será bloqueada hoy. Confirme su código en [ENLACE:pago-seguro-mx.com] "
        "o llame al [TELEFONO]."
    )
    fraude2 = "Último aviso: pague $500 antes de las 6 pm o su paquete se devuelve."
    oferta = "Felicidades: tu perfil fue seleccionado. Paga $350 de capacitación y empiezas mañana."
    legitimo = "Tu pedido fue entregado. Gracias por tu compra. Guía 1234567890."
    legitimo2 = "Hola mamá, ya llegué bien, te aviso cuando salga de la escuela."
    textos = [fraude, fraude2, fraude, oferta, legitimo, legitimo2, legitimo] * 4
    por_grupo = [
        "suplantacion_bancaria",
        "paqueteria_retenida",
        "extorsion",
        "oferta_laboral_fraudulenta",
        "legitimo",
        "legitimo",
        "legitimo",
    ]
    etiquetas = por_grupo * 4
    registros = [preparar_registro(t) for t in textos]
    return registros, etiquetas


def test_pipeline_entrena_y_predice_probabilidades() -> None:
    registros, etiquetas = _datos_minimos()
    _nombre, (estimador, cuadricula) = next(iter(CANDIDATOS.items()))
    pipeline = construir_pipeline(estimador)
    # Se fija el primer valor de cada hiperparámetro de la cuadrícula.
    primer_valor = {clave: valores[0] for clave, valores in cuadricula.items()}
    pipeline.set_params(**primer_valor)
    pipeline.fit(registros, etiquetas)
    proba = pipeline.predict_proba(registros[:2])
    assert proba.shape == (2, len(TIPOLOGIAS))
    assert abs(proba.sum(axis=1) - 1).max() < 1e-6
