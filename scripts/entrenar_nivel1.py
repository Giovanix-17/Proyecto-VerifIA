"""Entrenamiento del Nivel 1 — TF-IDF + modelo clásico (Fase 5, §9).

Pasos:

1. Carga ``train`` y ``validación`` del corpus (textos ya sanitizados).
2. Para cada candidato (regresión logística, SVM lineal, Naive Bayes) hace
   búsqueda en cuadrícula con **validación cruzada estratificada de 5
   pliegues** sobre train, optimizando F1 macro (memoria §9).
3. Entrena cada ganador en train y lo evalúa en validación.
4. Se queda con el de mejor F1 en validación, lo calibra
   (``CalibratedClassifierCV``, sigmoide, cv=5) y lo guarda en
   ``models/nivel1.joblib`` con su metadata en ``models/nivel1_meta.json``.

El modelo calibrado entrega probabilidades, requisito del §8.6 para la
puntuación ``100 × (1 − P(legítimo))``. El conjunto de prueba no se toca.

Uso::

    python scripts/entrenar_nivel1.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from corpus_common import ROOT, sha256_archivo
from fase5_common import (
    MODELOS,
    cargar_split,
    metricas_clasificacion,
    registros_y_etiquetas,
)
from sklearn.metrics import f1_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold

from verifia.classifier.level1 import CANDIDATOS, calibrar, construir_pipeline
from verifia.schemas import TIPOLOGIAS

SEMILLA = 42
META = MODELOS / "nivel1_meta.json"


def main() -> int:
    train = cargar_split("train")
    val = cargar_split("val")
    X_train, y_train = registros_y_etiquetas(train)
    X_val, y_val = registros_y_etiquetas(val)
    print(f"train: {len(X_train)} mensajes · validación: {len(X_val)}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEMILLA)
    resultados: dict[str, dict] = {}

    for nombre, (estimador, cuadricula) in CANDIDATOS.items():
        pipeline = construir_pipeline(estimador)
        busqueda = GridSearchCV(
            pipeline,
            param_grid=cuadricula,
            scoring="f1_macro",
            cv=cv,
            n_jobs=-1,
            refit=True,
        )
        busqueda.fit(X_train, y_train)
        y_pred = busqueda.predict(X_val)
        f1_val = f1_score(y_val, y_pred, labels=list(TIPOLOGIAS), average="macro", zero_division=0)
        resultados[nombre] = {
            "mejores_parametros": {k: str(v) for k, v in busqueda.best_params_.items()},
            "f1_macro_cv_train": round(busqueda.best_score_, 4),
            "f1_macro_val": round(float(f1_val), 4),
        }
        print(
            f"  {nombre}: CV F1 macro={busqueda.best_score_:.4f} · "
            f"val F1 macro={f1_val:.4f} · parámetros {busqueda.best_params_}"
        )

    ganador = max(resultados, key=lambda n: resultados[n]["f1_macro_val"])
    print(f"Ganador: {ganador}")

    estimador, cuadricula = CANDIDATOS[ganador]
    pipeline = construir_pipeline(estimador)
    busqueda = GridSearchCV(
        pipeline,
        param_grid=cuadricula,
        scoring="f1_macro",
        cv=cv,
        n_jobs=-1,
        refit=True,
    )
    busqueda.fit(X_train, y_train)
    modelo_calibrado = calibrar(busqueda.best_estimator_)
    modelo_calibrado.fit(X_train, y_train)
    # La calibración (cv interno) cambia la predicción dura; se reporta la
    # métrica del modelo calibrado, que es el que usará la cascada.
    y_pred_calibrado = modelo_calibrado.predict(X_val)
    metricas_val = metricas_clasificacion(y_val, list(y_pred_calibrado))
    print(f"  modelo calibrado · val F1 macro={metricas_val['f1_macro']}")
    for clase, valores in metricas_val["por_clase"].items():
        print(f"    {clase}: F1={valores['f1']} P={valores['precision']} R={valores['recall']}")

    MODELOS.mkdir(parents=True, exist_ok=True)
    ruta_modelo = MODELOS / "nivel1.joblib"
    import joblib

    joblib.dump(modelo_calibrado, ruta_modelo)

    metadata = {
        "version": "1.0",
        "fecha": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "ganador": ganador,
        "mejores_parametros": resultados[ganador]["mejores_parametros"],
        "candidatos": resultados,
        "metricas_val_calibrado": metricas_val,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "semilla": SEMILLA,
        "calibracion": "CalibratedClassifierCV(sigmoid, cv=5)",
        "hashes_splits": {
            f"{nombre}.jsonl": sha256_archivo(
                ROOT / "data" / "splits" / f"{nombre}.jsonl"
            )
            for nombre in ("train", "val", "test")
        },
    }
    META.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Modelo guardado en {ruta_modelo}")
    print(f"Metadata en {META}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
