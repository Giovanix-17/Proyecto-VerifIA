"""Ajuste del umbral de confianza de la cascada (Fase 5, §8.6).

El 0.80 es un valor inicial: se ajusta **una sola vez** con el conjunto de
validación para lograr **recall ≥ 90 % en las clases de fraude** sin escalar
demasiados mensajes al LLM. El conjunto de prueba no se usa para esto.

Criterio operativo, para cada umbral ``t`` sobre la probabilidad máxima del
Nivel 1:

* *resuelto*: ``prob_maxima >= t`` → el mensaje se queda en el Nivel 1;
* *escalado*: ``prob_maxima < t`` → el mensaje pasaría al LLM (que tiene una
  oportunidad de corregirlo);
* **recall seguro** de las clases de fraude = fracción de mensajes de fraude
  que **no** quedan mal clasificados en el Nivel 1, es decir 1 − (mal
  resueltos)/(fraude). Un fraude mal resuelto es el único error que la
  cascada no puede corregir, porque el LLM solo ve la zona gris.

Se elige el umbral **más bajo** (menos escalados, menos llamadas) que cumpla
el 90 % de recall seguro, y se guarda en ``models/nivel1_meta.json`` (campo
``umbral_confianza``). El runtime lo lee de ``UMBRAL_CONFIANZA``.

Uso::

    python scripts/ajustar_umbral.py
"""

from __future__ import annotations

import json

import numpy as np
from fase5_common import (
    MODELOS,
    REPORTES,
    cargar_split,
    registros_y_etiquetas,
)

from verifia.schemas import TIPOLOGIAS

CLASES_FRAUDE = tuple(t for t in TIPOLOGIAS if t != "legitimo")
GRID = [round(x, 2) for x in np.arange(0.50, 0.96, 0.05)]
META = MODELOS / "nivel1_meta.json"


def main() -> int:
    import joblib

    modelo = joblib.load(MODELOS / "nivel1.joblib")
    val = cargar_split("val")
    registros, y_verdad = registros_y_etiquetas(val)

    probabilidades = modelo.predict_proba(registros)
    clases = list(modelo.classes_)
    indice_verdad = [clases.index(e) for e in y_verdad]
    prob_max = probabilidades.max(axis=1)
    argmax = probabilidades.argmax(axis=1)
    correcto = [int(a) == i for a, i in zip(argmax, indice_verdad, strict=True)]

    es_fraude = np.array([e in CLASES_FRAUDE for e in y_verdad])
    total_fraude = int(es_fraude.sum())
    tabla: list[dict] = []

    for t in GRID:
        resuelto = prob_max >= t
        mal_resueltos = int((es_fraude & resuelto & ~np.array(correcto)).sum())
        recall_seguro = 1 - mal_resueltos / total_fraude if total_fraude else 1.0
        escalado_pct = float((~resuelto).mean())
        precision_resueltos = float(
            np.array(correcto)[resuelto].mean()
        ) if resuelto.any() else 0.0
        tabla.append(
            {
                "umbral": t,
                "escalado_pct": round(escalado_pct, 4),
                "resueltos_pct": round(1 - escalado_pct, 4),
                "fraude_mal_resuelto": mal_resueltos,
                "recall_seguro_fraude": round(recall_seguro, 4),
                "precision_en_resueltos": round(precision_resueltos, 4),
            }
        )

    # Elección (una sola vez, con validación; §8.6 y regla 11):
    #   1. recall seguro ≥ 0.90 en las clases de fraude (obligatorio);
    #   2. "sin escalar demasiados" → escalado ≤ 30 % de los mensajes;
    #   3. dentro de lo anterior, máximo recall seguro (la exhaustividad pesa
    #      más que el costo, regla 11) y, en empate, menos escalado.
    #   4. Dejando margen frente a la muerte súbita del barrido: si el máximo
    #      recall seguro aparece en dos umbrales, gana el menor escalado.
    candidatos = [
        f for f in tabla if f["recall_seguro_fraude"] >= 0.90 and f["escalado_pct"] <= 0.30
    ]
    elegido = max(
        candidatos,
        key=lambda f: (f["recall_seguro_fraude"], -f["escalado_pct"]),
        default=None,
    )
    umbral = elegido["umbral"] if elegido else GRID[-1]
    if elegido is None:
        print(
            "ADVERTENCIA: ningún umbral cumple recall ≥ 0.90 con escalado ≤ 30 %; "
            f"se conserva el más alto ({umbral}) y se documenta."
        )

    encabezado = (
        f"{'umbral':>6} | {'escalado':>8} | {'fraude mal res.':>15} | "
        f"{'recall seguro':>13} | {'prec. resueltos':>15}"
    )
    print(encabezado)
    for f in tabla:
        marca = "  <-- elegido" if f["umbral"] == umbral else ""
        print(
            f"{f['umbral']:>6.2f} | {f['escalado_pct']:>7.1%} | "
            f"{f['fraude_mal_resuelto']:>19} | {f['recall_seguro_fraude']:>13.1%} | "
            f"{f['precision_en_resueltos']:>15.1%}{marca}"
        )

    # Recall seguro por clase con el umbral elegido.
    resuelto = prob_max >= umbral
    detalle_clase: dict[str, dict] = {}
    for clase in TIPOLOGIAS:
        mascara = np.array([e == clase for e in y_verdad])
        mal = int((mascara & resuelto & ~np.array(correcto)).sum())
        total = int(mascara.sum())
        if clase == "legitimo":
            # En legítimo, "mal resuelto" es un falso positivo de fraude.
            recall_seguro = 1 - mal / total if total else 1.0
        else:
            recall_seguro = 1 - mal / total if total else 1.0
        detalle_clase[clase] = {
            "total": total,
            "mal_resueltos": mal,
            "recall_seguro": round(recall_seguro, 4),
        }

    REPORTES.mkdir(parents=True, exist_ok=True)
    (REPORTES / "ajuste_umbral.json").write_text(
        json.dumps(
            {
                "tabla": tabla,
                "umbral_elegido": umbral,
                "detalle_por_clase": detalle_clase,
                "criterio": "recall seguro ≥ 0.90 en clases de fraude, minimizando escalado",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if META.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        meta["umbral_confianza"] = umbral
        meta["umbral_criterio"] = "recall seguro ≥ 0.90 en fraude, mínimos escalados (val)"
        meta["umbral_barrido"] = tabla
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(f"ERROR: no existe {META}; ejecuta primero scripts/entrenar_nivel1.py")
        return 1

    print(f"\nUmbral elegido: {umbral} -> guardado en {META.name}")
    print("Recuerda fijar UMBRAL_CONFIANZA en .env con este valor para el runtime.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
