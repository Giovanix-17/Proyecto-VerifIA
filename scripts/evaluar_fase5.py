"""Evaluación final de la Fase 5 sobre el conjunto de prueba (reservado).

Compara las **tres configuraciones** (memoria §9 Fase 5):

1. ``solo_nivel1`` — solo el filtro clásico;
2. ``solo_nivel2`` — solo el LLM (una llamada por mensaje);
3. ``hibrido`` — la cascada con el umbral ajustado en validación.

El híbrido reutiliza las llamadas de ``solo_nivel2`` para la zona gris
(mismo modelo, mismo prompt, mismas condiciones): no duplica llamadas.

Métricas (§11): precisión/recall/F1 por clase y macro, matriz de confusión,
% de mensajes escalados, tiempo de respuesta y tokens por análisis.

Uso::

    python scripts/evaluar_fase5.py --dry-run
    python scripts/evaluar_fase5.py --timeout 180   # ~75 llamadas
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import joblib
from corpus_common import ROOT, escribir_jsonl
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


def _p50_p95(valores: list[float]) -> tuple[float, float]:
    if not valores:
        return 0.0, 0.0
    ordenados = sorted(valores)
    return (
        round(ordenados[int(0.50 * (len(ordenados) - 1))], 2),
        round(ordenados[min(len(ordenados) - 1, int(0.95 * (len(ordenados) - 1)))], 2),
    )


def llamar_todos(
    filas: list[dict[str, Any]],
    ejemplos: list[dict[str, str]],
    temperature: float,
    top_p: float,
    *,
    max_hilos: int = 4,
    ruta_jsonl: Path | None = None,
) -> list[dict[str, Any]]:
    """Llama al Nivel 2 a cada mensaje del conjunto indicado (en paralelo).

    Si se indica ``ruta_jsonl``, cada llamada se escribe y se descarga a disco
    en cuanto termina: un corte a mitad de la corrida no pierde las llamadas
    ya pagadas. El archivo final se reescribe ordenado por el llamador.
    """
    cliente = _cliente()
    resultados: dict[str, dict[str, Any]] = {}

    def una(fila: dict[str, Any]) -> dict[str, Any]:
        inicio = time.perf_counter()
        registro: dict[str, Any] = {"id": fila["id"]}
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
                    "latencia_s": meta["latencia_s"],
                    "tokens_entrada": meta["tokens_entrada"],
                    "tokens_salida": meta["tokens_salida"],
                }
            )
        except Exception as exc:  # noqa: BLE001 - el fallo es un dato de evaluación
            registro.update(
                {
                    "ok": False,
                    "motivo_fallo": getattr(exc, "motivo", type(exc).__name__),
                    "latencia_s": round(time.perf_counter() - inicio, 2),
                }
            )
        registro["tipologia_verdad"] = fila["tipologia"]
        return registro

    with ThreadPoolExecutor(max_workers=max_hilos) as ejecutor:
        archivo = None
        if ruta_jsonl is not None:
            ruta_jsonl.parent.mkdir(parents=True, exist_ok=True)
            archivo = ruta_jsonl.open("w", encoding="utf-8", newline="\n")
        try:
            futuros = {ejecutor.submit(una, fila): fila for fila in filas}
            for numero, futuro in enumerate(as_completed(futuros), start=1):
                registro = futuro.result()
                resultados[registro["id"]] = registro
                if archivo is not None:
                    archivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
                    archivo.flush()
                if numero % 15 == 0 or numero == len(filas):
                    ok = sum(1 for r in resultados.values() if r["ok"])
                    print(f"    {numero}/{len(filas)} llamadas ({ok} válidas)", flush=True)
        finally:
            if archivo is not None:
                archivo.close()

    return [resultados[f["id"]] for f in filas]


def resumen_llamadas(filas: list[dict[str, Any]]) -> dict[str, Any]:
    validas = [f for f in filas if f["ok"]]
    latencias = [f["latencia_s"] for f in validas]
    p50, p95 = _p50_p95(latencias)
    return {
        "n": len(filas),
        "pct_json_valido": round(len(validas) / len(filas), 4) if filas else 0.0,
        "latencia_media_s": round(sum(latencias) / len(latencias), 2) if validas else 0.0,
        "latencia_p50_s": p50,
        "latencia_p95_s": p95,
        "tokens_entrada_media": round(
            sum(f.get("tokens_entrada") or 0 for f in validas) / len(validas), 1
        )
        if validas
        else 0.0,
        "tokens_salida_media": round(
            sum(f.get("tokens_salida") or 0 for f in validas) / len(validas), 1
        )
        if validas
        else 0.0,
        "tokens_entrada_total": sum(f.get("tokens_entrada") or 0 for f in validas),
        "tokens_salida_total": sum(f.get("tokens_salida") or 0 for f in validas),
        "fallos": dict(
            sorted(
                (motivo, sum(1 for f in filas if not f["ok"] and f.get("motivo_fallo") == motivo))
                for motivo in {f.get("motivo_fallo") for f in filas if not f["ok"]}
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-hilos", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    if args.timeout:
        os.environ["LLM_TIMEOUT_S"] = str(args.timeout)

    test = cargar_split("test")
    ejemplos = elegir_few_shot(cargar_split("train"))
    registros, y_verdad = registros_y_etiquetas(test)
    modelo_n1 = joblib.load(MODELOS / "nivel1.joblib")
    meta = json.loads((MODELOS / "nivel1_meta.json").read_text(encoding="utf-8"))
    umbral = float(meta.get("umbral_confianza", 0.75))
    celda = "temp0_determinista"
    eleccion_path = REPORTES / "eleccion_llm.json"
    if eleccion_path.exists():
        eleccion = json.loads(eleccion_path.read_text(encoding="utf-8"))
        celda = eleccion["celda_elegida"]
        temperature = 0.0 if celda.startswith("temp0") else 1.0
        top_p = 1.0 if celda.startswith("temp0") else 0.95
    else:
        temperature, top_p = 0.0, 1.0

    print(f"Conjunto de prueba: {len(test)} mensajes · umbral {umbral} · celda {celda}")
    if args.dry_run:
        print(f"Llamadas previstas al LLM: {len(test)} (solo_nivel2; el híbrido las reutiliza)")
        return 0

    REPORTES.mkdir(parents=True, exist_ok=True)
    salida: dict[str, Any] = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_test": len(test),
        "umbral": umbral,
        "celda_muestreo": celda,
        "timeout_experimento_s": args.timeout or os.getenv("LLM_TIMEOUT_S"),
        "configuraciones": {},
    }

    # --- 1. Solo Nivel 1 --------------------------------------------------- #
    print("\n[1/3] solo_nivel1")
    inicio_lote = time.perf_counter()
    probabilidades = modelo_n1.predict_proba(registros)
    tiempo_lote_n1 = round(time.perf_counter() - inicio_lote, 4)
    inicio_individual = time.perf_counter()
    for registro in registros:
        modelo_n1.predict_proba([registro])
    latencia_n1_ms = round(
        1000 * (time.perf_counter() - inicio_individual) / len(registros), 2
    )
    clases = list(modelo_n1.classes_)
    y_n1 = [clases[int(p.argmax())] for p in probabilidades]
    p_n1 = [level1.puntuacion_nivel1(p) for p in probabilidades]
    salida["configuraciones"]["solo_nivel1"] = {
        "metricas": metricas_clasificacion(y_verdad, y_n1),
        "escalado_pct": 0.0,
        "llamadas_llm": 0,
        "tiempo_lote_s": tiempo_lote_n1,
        "latencia_media_ms": latencia_n1_ms,
        "tokens_entrada_total": 0,
        "tokens_salida_total": 0,
    }

    # --- 2. Solo Nivel 2 --------------------------------------------------- #
    print(f"\n[2/3] solo_nivel2 ({len(test)} llamadas)")
    llm_rows = llamar_todos(
        test,
        ejemplos,
        temperature,
        top_p,
        max_hilos=args.max_hilos,
        ruta_jsonl=REPORTES / "evaluacion_test_llm.jsonl",
    )
    escribir_jsonl(REPORTES / "evaluacion_test_llm.jsonl", llm_rows)
    validos = {f["id"]: f for f in llm_rows if f["ok"]}
    y_n2 = [validos[f["id"]]["tipologia_llm"] if f["id"] in validos else "legitimo" for f in test]
    resumen_llm = resumen_llamadas(llm_rows)
    metricas_n2 = metricas_clasificacion(y_verdad, y_n2)
    salida["configuraciones"]["solo_nivel2"] = {
        "metricas": metricas_n2,
        "escalado_pct": 1.0,
        "llamadas_llm": len(test),
        "llamadas": resumen_llm,
    }

    # --- 3. Híbrido (cascada) ---------------------------------------------- #
    print("\n[3/3] hibrido (reutiliza las llamadas de solo_nivel2)")
    y_hibrido: list[str] = []
    escalados = 0
    fallbacks = 0
    discrepancias = 0
    latencias_hibrido: list[float] = []
    tokens_entrada_hibrido = 0
    tokens_salida_hibrido = 0
    lat_llm = {f["id"]: float(f.get("latencia_s") or 0.0) for f in llm_rows if f["ok"]}
    for fila, proba, puntuacion1 in zip(test, probabilidades, p_n1, strict=True):
        if float(proba.max()) >= umbral:
            y_hibrido.append(clases[int(proba.argmax())])
            latencias_hibrido.append(latencia_n1_ms / 1000)
            continue
        escalados += 1
        acierto = validos.get(fila["id"])
        if acierto is None:
            fallbacks += 1
            y_hibrido.append(clases[int(proba.argmax())])
            latencias_hibrido.append(latencia_n1_ms / 1000)
            continue
        discrepancias += int(acierto.get("puntuacion_llm", 0) < puntuacion1)
        y_hibrido.append(acierto["tipologia_llm"])
        latencias_hibrido.append(latencia_n1_ms / 1000 + lat_llm.get(fila["id"], 0.0))
        tokens_entrada_hibrido += int(acierto.get("tokens_entrada") or 0)
        tokens_salida_hibrido += int(acierto.get("tokens_salida") or 0)
    p50_h, p95_h = _p50_p95(latencias_hibrido)
    salida["configuraciones"]["hibrido"] = {
        "metricas": metricas_clasificacion(y_verdad, y_hibrido),
        "escalado_pct": round(escalados / len(test), 4),
        "escalados": escalados,
        "fallbacks_en_zona_gris": fallbacks,
        "discrepancias_puntuacion": discrepancias,
        "llamadas_llm_propias": escalados,
        "llamadas_llm_reutilizadas": escalados - fallbacks,
        "llamadas_llm_evitadas": len(test) - escalados,
        "latencia_media_s": round(sum(latencias_hibrido) / len(latencias_hibrido), 2),
        "latencia_p50_s": p50_h,
        "latencia_p95_s": p95_h,
        "tokens_entrada_total": tokens_entrada_hibrido,
        "tokens_salida_total": tokens_salida_hibrido,
        "nota_tiempo": (
            "latencia secuencial estimada: medición real del Nivel 1 por mensaje "
            "+ latencia registrada de cada llamada al LLM en la zona gris; no "
            "mide concurrencia ni red del usuario"
        ),
    }

    (REPORTES / "evaluacion_test.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for nombre, datos in salida["configuraciones"].items():
        m = datos["metricas"]
        print(f"\n{nombre}: F1 macro={m['f1_macro']} · accuracy={m['accuracy']}")
        for clase, valores in m["por_clase"].items():
            print(
                f"    {clase}: P={valores['precision']:.2f} R={valores['recall']:.2f} "
                f"F1={valores['f1']:.2f} (n={valores['soporte']})"
            )
    print(f"\nResultados en {REPORTES / 'evaluacion_test.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
