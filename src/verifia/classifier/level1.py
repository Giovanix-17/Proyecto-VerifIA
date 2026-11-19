"""Nivel 1 — filtro rápido con TF-IDF y modelos clásicos (Fase 5, OE3).

Características (memoria §9 Fase 5):

* TF-IDF de **palabras** (unigramas + bigramas);
* TF-IDF de **caracteres** (n-gramas 3–5, tolera escritura ofuscada);
* **rasgos estructurales**: tipo de enlace (acortador, IP literal, TLD
  sospechoso…), proporción de mayúsculas, longitud y **marcadores de datos
  sanitizados** (regla 4: los enlaces se cuentan, nunca se concatenan).

La entrada del modelo es el texto **ya sanitizado** (regla 1): el registro se
construye desde :class:`verifia.sanitizer.models.TextoSanitizado`.

Modelos a comparar: regresión logística, SVM lineal y Naive Bayes
(sin XGBoost, decisión §15.1). La elección se hace por **F1 macro en
validación**; el modelo ganador se calibra con ``CalibratedClassifierCV``
(método sigmoide, cv=5) para obtener probabilidades y alimentar la cascada.

El corpus es balanceado por diseño (100 mensajes por clase), así que la
ponderación de clases es un seguro, no una corrección: ``class_weight=
"balanced"`` en LR/SVM; ``MultinomialNB`` no admite pesos de clase y no lo
necesita con clases balanceadas.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

from verifia.schemas import TIPOLOGIAS, banda_de_riesgo

INDICE_LEGITIMO = TIPOLOGIAS.index("legitimo")

# Marcadores del catálogo cerrado (regla 3) que se convierten en rasgos.
MARCADORES_RASGO: tuple[str, ...] = (
    "TELEFONO",
    "CORREO",
    "NOMBRE",
    "CUENTA",
    "TARJETA",
    "CODIGO",
    "CURP",
    "RFC",
)

UMBRAL = 0.80  # valor inicial de la cascada; se ajusta una vez en validación


# --------------------------------------------------------------------------- #
# Registro de entrada: del TextoSanitizado al dict que consume el modelo
# --------------------------------------------------------------------------- #
def preparar_registro(texto: str, marcadores: dict[str, int] | None = None,
                      rasgos_enlace: Iterable | None = None) -> dict:
    """Construye el registro del Nivel 1 a partir de un texto sanitizado.

    ``texto`` debe venir **ya enmascarado** (los marcadores ``[TELEFONO]``,
    ``[ENLACE:dominio.tld]``, … forman parte del texto). ``marcadores`` y
    ``rasgos_enlace`` provienen de :func:`verifia.sanitizer.sanitizar`; si no
    se pasan, los marcadores se cuentan desde el propio texto (útil para
    pruebas) y no hay rasgos de enlace.
    """
    marcadores = dict(marcadores or {})
    rasgos_enlace = list(rasgos_enlace or [])
    registro: dict = {
        "texto": texto,
        "marcadores": marcadores,
        "rasgos_enlace": [
            r.como_dict() if hasattr(r, "como_dict") else dict(r) for r in rasgos_enlace
        ],
    }
    registro["estructurales"] = rasgos_estructurales(registro)
    return registro


def rasgos_estructurales(registro: dict) -> dict[str, float]:
    """Rasgos numéricos derivados del texto sanitizado (regla 4).

    Nunca incluyen el contenido del dato original: solo conteos, longitudes y
    proporciones. Los enlaces entran por sus rasgos estructurales, no por su
    dominio en el texto (el dominio sí queda en el marcador y lo ve TF-IDF).
    """
    texto: str = registro.get("texto", "")
    letras = [c for c in texto if c.isalpha()]
    total_letras = len(letras)

    rasgos: dict[str, float] = {
        "longitud_caracteres": float(len(texto)),
        "longitud_palabras": float(len(texto.split())),
        "proporcion_mayusculas": (
            sum(1 for c in letras if c.isupper()) / total_letras if total_letras else 0.0
        ),
        "proporcion_digitos": (
            sum(1 for c in texto if c.isdigit()) / len(texto) if texto else 0.0
        ),
        "exclamaciones": float(texto.count("!") + texto.count("¡")),
        "interrogaciones": float(texto.count("?") + texto.count("¿")),
    }

    marcadores = registro.get("marcadores") or {}
    for nombre in MARCADORES_RASGO:
        rasgos[f"marcador_{nombre.lower()}"] = float(marcadores.get(f"[{nombre}]", 0))

    enlaces = registro.get("rasgos_enlace") or []
    rasgos["num_enlaces"] = float(len(enlaces))
    rasgos["enlace_acortador"] = float(any(e.get("es_acortador") for e in enlaces))
    rasgos["enlace_ip_literal"] = float(any(e.get("ip_literal") for e in enlaces))
    rasgos["enlace_tld_sospechoso"] = float(any(e.get("tld_sospechoso") for e in enlaces))
    rasgos["enlace_puerto"] = float(any(e.get("tiene_puerto") for e in enlaces))
    rasgos["enlace_max_subdominios"] = float(
        max((e.get("num_subdominios", 0) for e in enlaces), default=0)
    )
    rasgos["enlace_total_guiones"] = float(sum(e.get("guiones_en_host", 0) for e in enlaces))
    return rasgos


# --------------------------------------------------------------------------- #
# Transformadores (picklables para joblib: clases a nivel de módulo)
# --------------------------------------------------------------------------- #
class ExtraerTextos:
    """Devuelve la lista de textos del registro para los TF-IDF."""

    def fit(self, X: list[dict], y: np.ndarray | None = None) -> ExtraerTextos:
        return self

    def transform(self, X: list[dict]) -> list[str]:
        return [registro["texto"] for registro in X]

    def get_params(self, deep: bool = True) -> dict:
        return {}

    def set_params(self, **params) -> ExtraerTextos:
        return self


class ExtraerRasgos:
    """Vectoriza los rasgos estructurales de cada registro."""

    def fit(self, X: list[dict], y: np.ndarray | None = None) -> ExtraerRasgos:
        return self

    def transform(self, X: list[dict]) -> list[dict[str, float]]:
        return [
            registro.get("estructurales") or rasgos_estructurales(registro)
            for registro in X
        ]

    def get_params(self, deep: bool = True) -> dict:
        return {}

    def set_params(self, **params) -> ExtraerRasgos:
        return self


def construir_pipeline(estimador) -> Pipeline:
    """Une los tres bloques de características y el estimador final."""
    caracteristicas = FeatureUnion(
        [
            ("palabras", Pipeline([
                ("extraer", ExtraerTextos()),
                ("tfidf", TfidfVectorizer(
                    ngram_range=(1, 2),
                    min_df=2,
                    sublinear_tf=True,
                    strip_accents="unicode",
                )),
            ])),
            ("caracteres", Pipeline([
                ("extraer", ExtraerTextos()),
                ("tfidf", TfidfVectorizer(
                    analyzer="char",
                    ngram_range=(3, 5),
                    min_df=2,
                    sublinear_tf=True,
                    lowercase=True,
                )),
            ])),
            ("estructurales", Pipeline([
                ("extraer", ExtraerRasgos()),
                ("dict", DictVectorizer(sparse=True)),
            ])),
        ]
    )
    return Pipeline([
        ("caracteristicas", caracteristicas),
        ("modelo", estimador),
    ])


# --------------------------------------------------------------------------- #
# Candidatos y cuadrículas (§9 Fase 5: LR, SVM lineal, NB; sin XGBoost)
# --------------------------------------------------------------------------- #
CANDIDATOS: dict[str, tuple[object, dict]] = {
    "regresion_logistica": (
        LogisticRegression(max_iter=10000, class_weight="balanced", random_state=42),
        {"modelo__C": [0.1, 1.0, 3.0, 10.0]},
    ),
    "svm_lineal": (
        LinearSVC(max_iter=10000, class_weight="balanced", random_state=42),
        {"modelo__C": [0.1, 1.0, 3.0, 10.0]},
    ),
    "naive_bayes": (
        MultinomialNB(),
        {"modelo__alpha": [0.1, 0.5, 1.0]},
    ),
}


# --------------------------------------------------------------------------- #
# Probabilidades → puntuación (§8.6)
# --------------------------------------------------------------------------- #
def puntuacion_nivel1(probabilidades: np.ndarray) -> int:
    """``round(100 × (1 − P(mensaje_legitimo)))`` con el modelo calibrado."""
    p_legitimo = float(np.asarray(probabilidades)[INDICE_LEGITIMO])
    return int(round(100 * (1 - p_legitimo)))


def nivel_riesgo_de_puntuacion(puntuacion: int) -> str:
    """Banda del semáforo (§8.5). Envoltorio explícito para el Nivel 1."""
    return banda_de_riesgo(puntuacion)


def calibrar(pipeline: Pipeline) -> CalibratedClassifierCV:
    """Calibra el pipeline ganador (sigmoide, cv=5) para producir probabilidades."""
    return CalibratedClassifierCV(estimator=pipeline, method="sigmoid", cv=5)
