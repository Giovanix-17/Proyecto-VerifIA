"""Comparación de muestreo del Nivel 2 sobre validación (Fase 5).

Protocolo (memoria §9 Fase 5 y skill ``verifia-nivel2-llm``):

* mismo prompt, mismas filas (validación completa) y mismas condiciones;
* celdas de muestreo: ``temperature=0 / top_p=1.0`` (determinista) contra el
  muestreo recomendado por el modelo (``temperature=1.0 / top_p=0.95``);
* métricas por celda: **% de JSON válido**, **acuerdo con las etiquetas
  humanas**, latencia (p50/p95) y tokens de entrada/salida;
* elige la celda con mayor tasa de JSON válido y, en empate, mayor acuerdo;
  la elección queda en ``data/reportes_fase5/eleccion_llm.json``.

El conjunto de prueba no se toca aquí. Las llamadas van en paralelo moderado
(4 hilos) y los reintentos de ``retry.py`` absorben 429/5xx transitorios.

Uso::

    python scripts/comparar_llm.py            # corrida completa (~150 llamadas)
    python scripts/comparar_llm.py --dry-run  # solo muestra el plan
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from corpus_common import ROOT, escribir_jsonl, leer_jsonl
from dotenv import load_dotenv
from fase5_common import (
    MODELOS,
    REPORTES,
    cargar_split,
    elegir_few_shot,
    metricas_clasificacion,
    registros_y_etiquetas,
)

from verifia.classifier import level1
from verifia.classifier.level2_llm import _cliente, consultar

CELDA_0 = ("temp0_determinista", 0.0, 1.0)
CELDA_1 = ("temp1_recomendado", 1.0, 0.95)
UMBRAL_DEFECTO = 0.75


def _p50_p95(valores: list[float]) -> tuple[float, float]:
    if not valores:
        return 0.0, 0.0
    ordenados = sorted(valores)
    p50 = ordenados[int(0.50 * (len(ordenados) - 1))]
    p95 = ordenados[min(len(ordenados) - 1, int(0.95 * (len(ordenados) - 1)))]
    return round(p50, 2), round(p95, 2)


def ejecutar_celda(
    nombre: str,
    temperature: float,
    top_p: float,
    filas_val: list[dict[str, Any]],
    ejemplos: list[dict[str, str]],
    *,
    max_hilos: int = 4,
    tope_llamadas: int | None = None,
) -> list[dict[str, Any]]:
    """Ejecuta el Nivel 2 sobre toda la validación con una celda de muestreo."""
    cliente = _cliente()
    resultados: dict[str, dict[str, Any]] = {}

    def una(fila: dict[str, Any]) -> dict[str, Any]:
        inicio = time.perf_counter()
        registro: dict[str, Any] = {"id": fila["id"], "celda": nombre}
        try:
            dictamen, meta = consultar(
                cliente,
                fila["texto"],
                ejemplos=ejemplos,
                temperature=temperature,
                top_p=top_p,
            )
            registro.update(
                {
                    "ok": True,
                    "tipologia_llm": dictamen.tipologia,
                    "puntuacion_llm": dictamen.puntuacion,
                    "n_senales": len(dictamen.senales_alerta),
                    "acuerdo": dictamen.tipologia == fila["tipologia"],
                    "latencia_s": meta["latencia_s"],
                    "tokens_entrada": meta["tokens_entrada"],
                    "tokens_salida": meta["tokens_salida"],
                    "senales_descartadas": meta.get("senales_descartadas", 0),
                }
            )
        except Exception as exc:  # noqa: BLE001 - el fallo es un dato del experimento
            motivo = getattr(exc, "motivo", type(exc).__name__)
            registro.update(
                {
                    "ok": False,
                    "motivo_fallo": motivo,
                    "latencia_s": round(time.perf_counter() - inicio, 2),
                }
            )
        registro["tipologia_verdad"] = fila["tipologia"]
        return registro

    pendientes = filas_val if tope_llamadas is None else filas_val[:tope_llamadas]
    with ThreadPoolExecutor(max_workers=max_hilos) as ejecutor:
        futuros = {ejecutor.submit(una, fila): fila for fila in pendientes}
        for numero, futuro in enumerate(as_completed(futuros), start=1):
            registro = futuro.result()
            resultados[registro["id"]] = registro
            if numero % 15 == 0 or numero == len(pendientes):
                ok = sum(1 for r in resultados.values() if r["ok"])
                print(
                    f"  [{nombre}] {numero}/{len(pendientes)} completadas ({ok} válidas)",
                    flush=True,
                )

    return [resultados[f["id"]] for f in pendientes]


def resumen_celda(nombre: str, filas: list[dict[str, Any]]) -> dict[str, Any]:
    validas = [f for f in filas if f["ok"]]
    acuerdo = [f for f in validas if f["acuerdo"]]
    latencias = [f["latencia_s"] for f in validas]
    p50, p95 = _p50_p95(latencias)
    resumen = {
        "celda": nombre,
        "n": len(filas),
        "pct_json_valido": round(len(validas) / len(filas), 4) if filas else 0.0,
        "acuerdo": round(len(acuerdo) / len(validas), 4) if validas else 0.0,
        "latencia_p50_s": p50,
        "latencia_p95_s": p95,
        "tokens_entrada_media": round(
            sum(f.get("tokens_entrada") or 0 for f in validas) / len(validas), 1
        ) if validas else 0.0,
        "tokens_salida_media": round(
            sum(f.get("tokens_salida") or 0 for f in validas) / len(validas), 1
        ) if validas else 0.0,
        "senales_descartadas": sum(f.get("senales_descartadas", 0) for f in validas),
        "fallos": dict(
            sorted(
                (motivo, sum(1 for f in filas if not f["ok"] and f.get("motivo_fallo") == motivo))
                for motivo in {f.get("motivo_fallo") for f in filas if not f["ok"]}
            )
        ),
    }
    y_verdad = [f["tipologia_verdad"] for f in validas]
    y_llm = [f["tipologia_llm"] for f in validas]
    if y_verdad:
        resumen["metricas_solo_nivel2"] = metricas_clasificacion(y_verdad, y_llm)
    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="muestra el plan y sale")
    parser.add_argument("--max-hilos", type=int, default=4)
    parser.add_argument("--tope-llamadas", type=int, default=None, help="tope por celda (pruebas)")
    parser.add_argument(
        "--celdas",
        default=",".join(c[0] for c in (CELDA_0, CELDA_1)),
        help=(
            "celdas a ejecutar, separadas por coma "
            "(temp0_determinista,temp1_recomendado). Las que no se ejecuten se "
            "reutilizan de su JSONL si ya están completas."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help=(
            "timeout de llamada en segundos para ESTE experimento (anula "
            "LLM_TIMEOUT_S). Útil si el proveedor muestra latencias altas; "
            "la configuración de despliegue (.env) no cambia."
        ),
    )
    args = parser.parse_args(argv)

    if args.timeout:
        os.environ["LLM_TIMEOUT_S"] = str(args.timeout)
        print(f"timeout experimental: {args.timeout} s (no modifica .env)")

    load_dotenv(ROOT / ".env")
    modelo_llm = os.getenv("LLM_MODEL", "minimaxai/minimax-m3.1-flash")
    val = cargar_split("val")
    ejemplos = elegir_few_shot(cargar_split("train"))

    total = len(val) * 2
    print(f"Plan: celdas {[c[0] for c in (CELDA_0, CELDA_1)]} · modelo {modelo_llm}")
    print(f"  mensajes de validación: {len(val)} · llamadas totales: {total}")
    if args.dry_run:
        return 0
    if args.tope_llamadas and args.tope_llamadas * 2 > 150:
        print(
            "El tope por celda excede el presupuesto de llamadas (~150).",
            file=sys.stderr,
        )
        return 2

    REPORTES.mkdir(parents=True, exist_ok=True)
    resumenes: dict[str, dict[str, Any]] = {}
    filas_por_celda: dict[str, list[dict[str, Any]]] = {}

    celdas = (CELDA_0, CELDA_1)
    por_nombre = {celda[0]: celda for celda in celdas}
    a_ejecutar = [n.strip() for n in args.celdas.split(",") if n.strip()]
    desconocidas = [n for n in a_ejecutar if n not in por_nombre]
    if desconocidas:
        print(f"Celdas desconocidas: {desconocidas}; usa {list(por_nombre)}", file=sys.stderr)
        return 2

    for nombre, temperature, top_p in celdas:
        if nombre not in a_ejecutar:
            ruta_previa = REPORTES / f"comparacion_llm_{nombre}.jsonl"
            if not ruta_previa.exists():
                print(
                    f"Falta {ruta_previa.name}: ejecuta esa celda antes de reutilizarla.",
                    file=sys.stderr,
                )
                return 2
            previas = leer_jsonl(ruta_previa)
            if len(previas) != len(val):
                print(
                    f"{ruta_previa.name} tiene {len(previas)} filas y la validación "
                    f"{len(val)}; no se reutiliza una celda incompleta.",
                    file=sys.stderr,
                )
                return 2
            print(f"\nCelda {nombre}: reutilizada de {ruta_previa.name} ({len(previas)} filas)")
            filas_por_celda[nombre] = previas
            resumenes[nombre] = resumen_celda(nombre, previas)
            print(
                f"  JSON válido: {resumenes[nombre]['pct_json_valido']:.1%} · "
                f"acuerdo: {resumenes[nombre]['acuerdo']:.1%}"
            )
            continue

        print(f"\nCelda {nombre}: temperature={temperature} top_p={top_p}")
        filas = ejecutar_celda(
            nombre,
            temperature,
            top_p,
            val,
            ejemplos,
            max_hilos=args.max_hilos,
            tope_llamadas=args.tope_llamadas,
        )
        filas_por_celda[nombre] = filas
        escribir_jsonl(REPORTES / f"comparacion_llm_{nombre}.jsonl", filas)
        resumenes[nombre] = resumen_celda(nombre, filas)
        print(
            f"  JSON válido: {resumenes[nombre]['pct_json_valido']:.1%} · "
            f"acuerdo: {resumenes[nombre]['acuerdo']:.1%} · "
            f"latencia p50/p95: {resumenes[nombre]['latencia_p50_s']}"
            f"/{resumenes[nombre]['latencia_p95_s']} s"
        )

    # Elección: mayor % JSON válido; empate → mayor acuerdo; empate → menor p95.
    def clave(celda: dict[str, Any]) -> tuple[float, float, float]:
        return (celda["pct_json_valido"], celda["acuerdo"], -celda["latencia_p95_s"])

    elegida = max(resumenes.values(), key=clave)
    print(f"\nCelda elegida: {elegida['celda']}")

    # Cascada end-to-end en validación con la celda elegida y el umbral guardado.
    meta_path = MODELOS / "nivel1_meta.json"
    umbral = UMBRAL_DEFECTO
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        umbral = float(meta.get("umbral_confianza", umbral))
    modelo_n1 = None
    if (MODELOS / "nivel1.joblib").exists():
        import joblib

        modelo_n1 = joblib.load(MODELOS / "nivel1.joblib")

    filas = filas_por_celda[elegida["celda"]]
    dictamenes = {f["id"]: f for f in filas if f["ok"]}
    y_final: list[str] = []
    y_verdad: list[str] = []
    escalados = 0
    discrepancias = 0
    if modelo_n1 is not None:
        registros, etiquetas = registros_y_etiquetas(val)
        probabilidades = modelo_n1.predict_proba(registros)
        clases = list(modelo_n1.classes_)
        for fila, proba, etiqueta in zip(val, probabilidades, etiquetas, strict=True):
            y_verdad.append(etiqueta)
            p_max = float(proba.max())
            if p_max >= umbral:
                y_final.append(clases[int(proba.argmax())])
                continue
            escalados += 1
            acierto = dictamenes.get(fila["id"])
            p_n1 = level1.puntuacion_nivel1(proba, clases)
            if acierto is None:
                y_final.append(clases[int(proba.argmax())])  # fallback
                continue
            discrepancias += int(acierto.get("puntuacion_llm", 0) < p_n1)
            y_final.append(acierto["tipologia_llm"])
        metricas_hibrido_val = metricas_clasificacion(y_verdad, y_final)
        print(f"\nCascada en validación (umbral {umbral}):")
        print(f"  escalados: {escalados}/{len(val)} ({escalados / len(val):.1%})")
        print(f"  discrepancias de puntuación: {discrepancias}")
        m_hibrido = metricas_hibrido_val
        print(f"  F1 macro: {m_hibrido['f1_macro']} · accuracy: {m_hibrido['accuracy']}")
    else:
        metricas_hibrido_val = None

    salida = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "modelo": modelo_llm,
        "celdas": resumenes,
        "celda_elegida": elegida["celda"],
        "criterio": "mayor % JSON válido; empate → mayor acuerdo; empate → menor p95",
        "umbral_usado": umbral,
        "metricas_cascada_val": metricas_hibrido_val,
        "escalados_val": escalados,
        "discrepancias_val": discrepancias,
    }
    (REPORTES / "eleccion_llm.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nResultados en {REPORTES / 'eleccion_llm.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
