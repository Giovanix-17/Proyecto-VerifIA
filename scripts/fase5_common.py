"""Utilidades compartidas de la Fase 5 (scripts).

Agrupa lo que usan entrenamiento, ajuste de umbral, comparación de LLM,
evaluación y el Experimento B del kappa:

* carga de un split con los textos **ya sanitizados** (regla 1: el Nivel 1 y
  el Nivel 2 solo ven texto enmascarado), con caché en disco porque la carga
  de Presidio + spaCy tarda segundos;
* selección del few-shot de train para el prompt (regla 10: nunca val/test);
* métricas de clasificación (por clase y macro, matriz de confusión).

La caché guarda solo ``id``, el texto enmascarado, los conteos de marcadores
y los rasgos de enlace: es un derivado sin datos personales del corpus, que
ya vive en ``data/splits/``. No guarda mensajes de usuarios (regla 2).
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from typing import Any

from corpus_common import ROOT, TIPOLOGIAS, leer_jsonl

from verifia.sanitizer import sanitizar
from verifia.schemas import TIPOLOGIAS as TIPOLOGIAS_ESQUEMA

SPLITS = ROOT / "data" / "splits"
CACHE = SPLITS / "sanitizado"
REPORTES = ROOT / "data" / "reportes_fase5"
MODELOS = ROOT / "models"

assert TIPOLOGIAS == TIPOLOGIAS_ESQUEMA, "Las tipologías de corpus y esquema divergen"


# --------------------------------------------------------------------------- #
# Carga de splits con sanitización + caché
# --------------------------------------------------------------------------- #
def _fila_a_cache(fila: dict[str, Any]) -> dict[str, Any]:
    resultado = sanitizar(fila["texto"])
    enlaces = [e.como_dict() for e in resultado.rasgos_enlace]
    return {
        "id": fila["id"],
        "tipologia": fila["tipologia"],
        "origen": fila.get("origen", ""),
        "texto": resultado.texto,
        "marcadores": resultado.marcadores,
        "rasgos_enlace": enlaces,
    }


def cargar_split(nombre: str, *, refrescar: bool = False) -> list[dict[str, Any]]:
    """Devuelve las filas de ``data/splits/{nombre}.jsonl`` ya sanitizadas.

    La primera ejecución pasa el split por el sanitizador (Fase 3) y guarda
    el resultado en la caché; las siguientes leen la caché. ``refrescar``
    fuerza recalcular (p. ej. si cambió el sanitizador).
    """
    destino = CACHE / f"{nombre}.jsonl"
    if destino.exists() and not refrescar:
        return leer_jsonl(destino)
    filas = leer_jsonl(SPLITS / f"{nombre}.jsonl")
    cacheadas = [_fila_a_cache(fila) for fila in filas]
    CACHE.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", newline="\n") as fh:
        for fila in cacheadas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return cacheadas


def registro_de_fila(fila: dict[str, Any]) -> dict:
    """Convierte una fila cacheada en el registro que consume el Nivel 1."""
    from verifia.classifier.level1 import preparar_registro

    return preparar_registro(fila["texto"], fila["marcadores"], fila["rasgos_enlace"])


def registros_y_etiquetas(filas: Iterable[dict[str, Any]]) -> tuple[list[dict], list[str]]:
    """Registros del Nivel 1 y etiquetas alineadas."""
    registros: list[dict] = []
    etiquetas: list[str] = []
    for fila in filas:
        registros.append(registro_de_fila(fila))
        etiquetas.append(fila["tipologia"])
    return registros, etiquetas


# --------------------------------------------------------------------------- #
# Few-shot (solo train, regla 10)
# --------------------------------------------------------------------------- #
def elegir_few_shot(
    filas_train: list[dict[str, Any]], por_clase: int = 2, semilla: int = 42
) -> list[dict[str, str]]:
    """Selecciona ejemplos equilibrados por clase para el prompt del Nivel 2.

    Determinista con la semilla para que las corridas de comparación usen el
    mismo prompt. Devuelve ``{"texto", "tipologia"}`` con el texto sanitizado
    de la caché.
    """
    rng = random.Random(semilla)
    ejemplos: list[dict[str, str]] = []
    for clase in TIPOLOGIAS:
        candidatos = [f for f in filas_train if f["tipologia"] == clase]
        for fila in rng.sample(candidatos, k=min(por_clase, len(candidatos))):
            ejemplos.append({"texto": fila["texto"], "tipologia": fila["tipologia"]})
    return ejemplos


# --------------------------------------------------------------------------- #
# Métricas
# --------------------------------------------------------------------------- #
def metricas_clasificacion(
    y_true: list[str], y_pred: list[str]
) -> dict[str, Any]:
    """Precisión, recall y F1 por clase y macro (memoria §11)."""
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    reporte = classification_report(
        y_true, y_pred, labels=list(TIPOLOGIAS), output_dict=True, zero_division=0
    )
    por_clase = {
        clase: {
            "precision": round(reporte[clase]["precision"], 4),
            "recall": round(reporte[clase]["recall"], 4),
            "f1": round(reporte[clase]["f1-score"], 4),
            "soporte": reporte[clase]["support"],
        }
        for clase in TIPOLOGIAS
    }
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "f1_macro": round(reporte["macro avg"]["f1-score"], 4),
        "precision_macro": round(reporte["macro avg"]["precision"], 4),
        "recall_macro": round(reporte["macro avg"]["recall"], 4),
        "por_clase": por_clase,
        "matriz_confusion": confusion_matrix(
            y_true, y_pred, labels=list(TIPOLOGIAS)
        ).tolist(),
        "etiquetas": list(TIPOLOGIAS),
    }


def matriz_confusion_con_etiquetas(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """Matriz de confusión como pares (etiquetas, filas) para reportes."""
    metricas = metricas_clasificacion(y_true, y_pred)
    return {"etiquetas": metricas["etiquetas"], "matriz": metricas["matriz_confusion"]}
