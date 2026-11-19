"""Figuras de la Fase 5 (memoria §11: matriz de confusión y curvas).

Genera, a partir de los JSON de resultados (sin recalcular nada):

1. ``matrices_confusion_fase5.png`` — matrices de confusión de las tres
   configuraciones sobre el conjunto de prueba, con conteos anotados (el
   color nunca es el único canal, WCAG 2.1).
2. ``barrido_umbral.png`` — barrido del umbral de confianza sobre la
   validación: recall seguro en fraude y % de escalado.

Anotación de origen (skill ``scientific-visualization`` §1): los datos vienen
de ``data/reportes_fase5/evaluacion_test.json`` y
``data/reportes_fase5/ajuste_umbral.json``; sin transformaciones más allá del
conteo de la matriz ya calculada por ``fase5_common``. Opciones de
publicación (DPI, tamaño) son provisionales: el destino es el reporte
académico del proyecto, no una revista concreta.

Uso::

    python scripts/figuras_fase5.py
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from corpus_common import ROOT
from fase5_common import REPORTES

FIGURAS = ROOT / "docs" / "reportes" / "figuras"
ETIQUETAS_CORTAS = [
    "legítimo",
    "suplantación",
    "paquetería",
    "oferta lab.",
    "extorsión",
]


def _matriz(ax, matriz: list[list[int]], titulo: str) -> None:
    datos = np.array(matriz)
    maximo = datos.max() if datos.max() else 1
    imagen = ax.imshow(datos, cmap="Blues", vmin=0, vmax=maximo, interpolation="nearest")
    marcas = np.arange(len(ETIQUETAS_CORTAS))
    ax.set_xticks(
        marcas,
        ETIQUETAS_CORTAS,
        rotation=55,
        ha="right",
        rotation_mode="anchor",
        fontsize=7.5,
    )
    ax.set_yticks(marcas, ETIQUETAS_CORTAS, fontsize=8)
    for i in range(datos.shape[0]):
        for j in range(datos.shape[1]):
            valor = datos[i, j]
            # Conteo redundante con el color; el texto cambia de tono según la
            # luminancia real del relleno para conservar contraste (WCAG 2.1).
            rojo, verde, azul, _ = imagen.cmap(imagen.norm(valor))
            luminancia = 0.2126 * rojo + 0.7152 * verde + 0.0722 * azul
            color = "white" if luminancia < 0.45 else "#1a1a1a"
            ax.text(j, i, str(valor), ha="center", va="center", color=color, fontsize=9)
    ax.set_title(titulo, fontsize=10)
    ax.set_xlabel("Predicción del sistema", fontsize=9)
    ax.set_ylabel("Etiqueta humana", fontsize=9)
    return imagen


def figuras_matrices() -> None:
    ruta = REPORTES / "evaluacion_test.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    configuraciones = [
        ("solo_nivel1", "Solo Nivel 1"),
        ("solo_nivel2", "Solo Nivel 2 (LLM)"),
        ("hibrido", "Híbrido (cascada)"),
    ]
    fig, ejes = plt.subplots(
        1,
        3,
        figsize=(190 / 25.4, 70 / 25.4),
        layout="constrained",
    )
    for ax, (clave, titulo) in zip(ejes, configuraciones, strict=True):
        metricas = datos["configuraciones"][clave]["metricas"]
        _matriz(ax, metricas["matriz_confusion"], f"{titulo}\nF1 macro {metricas['f1_macro']:.3f}")
    fig.suptitle(
        f"Matrices de confusión en el conjunto de prueba (n={datos['n_test']})",
        fontsize=11,
    )
    destino = FIGURAS / "matrices_confusion_fase5.png"
    fig.savefig(destino, dpi=300, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"Figura: {destino.relative_to(ROOT)}")


def figura_umbral() -> None:
    ruta = REPORTES / "ajuste_umbral.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    tabla = datos["tabla"]
    umbrales = [f["umbral"] for f in tabla]
    recall = [f["recall_seguro_fraude"] for f in tabla]
    escalado = [f["escalado_pct"] for f in tabla]
    elegido = datos["umbral_elegido"]

    fig, ax = plt.subplots(figsize=(120 / 25.4, 70 / 25.4), layout="constrained")
    ax.plot(umbrales, recall, marker="o", color="#0072B2", label="Recall seguro en fraude")
    ax.plot(umbrales, escalado, marker="s", color="#D55E00", label="% escalado al LLM")
    ax.axhline(0.90, color="#777777", linestyle="--", linewidth=1)
    ax.text(0.945, 0.912, "meta 90 %", fontsize=8, color="#555555", va="bottom", ha="right")
    ax.axvline(elegido, color="#009E73", linestyle=":", linewidth=1.5)
    ax.text(
        elegido - 0.008,
        0.30,
        f"elegido {elegido:.2f}",
        fontsize=8,
        color="#007a53",
        ha="right",
    )
    ax.set_xlabel("Umbral de confianza de la cascada")
    ax.set_ylabel("Proporción")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Barrido del umbral sobre validación (n=75)", fontsize=10)
    ax.grid(axis="y", color="#cccccc", linewidth=0.6, alpha=0.7)
    ax.legend(
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.55, 0.88),
        frameon=True,
        framealpha=0.95,
    )
    destino = FIGURAS / "barrido_umbral.png"
    fig.savefig(destino, dpi=300, facecolor="white")
    plt.close(fig)
    print(f"Figura: {destino.relative_to(ROOT)}")


def main() -> int:
    FIGURAS.mkdir(parents=True, exist_ok=True)
    if (REPORTES / "evaluacion_test.json").exists():
        figuras_matrices()
    else:
        print("Sin evaluacion_test.json: ejecuta primero scripts/evaluar_fase5.py")
    if (REPORTES / "ajuste_umbral.json").exists():
        figura_umbral()
    else:
        print("Sin ajuste_umbral.json: ejecuta primero scripts/ajustar_umbral.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
