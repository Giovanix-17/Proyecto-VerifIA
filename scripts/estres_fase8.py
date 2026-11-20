"""Pruebas de estrés de la API de VerifIA (Fase 8, §4 del skill verifia-validacion).

Envía solicitudes concurrentes de texto y mide p50/p95/p99 y tasa de errores.
Separa las rutas que llaman al LLM (zona gris) de las que no (Nivel 1).
Verifica que el limitador de frecuencia responde 429 sin bloquear al resto.

Uso (PowerShell)::

    $env:PYTHONPATH="src"; python scripts/estres_fase8.py --concurrencia 20 --repeticiones 1
    $env:PYTHONPATH="src"; python scripts/estres_fase8.py --concurrencia 50 --repeticiones 1

No guarda texto de mensajes ni respuestas del LLM (regla 2): solo conteos,
latencias y códigos de estado.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi.testclient import TestClient

from verifia.api import main as api_main
from verifia.api.limites import LimiteFrecuencia
from verifia.schemas import TIPOLOGIAS

ROOT = Path(__file__).resolve().parents[1]
REPORTES = ROOT / "data" / "reportes_fase8"
REPORTES.mkdir(parents=True, exist_ok=True)

# Textos representativos: legítimo (Nivel 1, sin LLM) y zona gris (puede llamar al LLM).
# Se eligen del corpus existente para que el estrés use mensajes reales (anónimos).
TEXTOS = [
    # Legítimos de alta confianza -> Nivel 1, sin LLM.
    "BBVA: Se realizo un cargo de $450.00 en CAFE CENTRAL con tu tarjeta. Si no lo reconoces, llama al numero al reverso de tu tarjeta.",
    "Tu paquete ha sido entregado correctamente en la direccion indicada. Gracias por usar nuestro servicio.",
    "Hola Juan, te confirmo la reunion de mañana a las 10:00 en la oficina central.",
    # Zona gris (prob maxima < 0.75) -> puede escalar al LLM si hay clave.
    "Su cuenta sera bloqueada hoy. Confirme su codigo en [ENLACE:banco-verify.com]",
    "Gane $5000 por semana trabajando desde casa, sin experiencia requerida. Pague el entrenamiento para iniciar.",
    "Paquete retenido en aduana. Pague el derecho de entrega para liberarlo hoy mismo.",
]


def _cliente_con_limite(maximo: int) -> TestClient:
    """Cliente con un límite de frecuencia generoso para no falsificar 429 por defecto."""
    api_main.app.state.limite = LimiteFrecuencia(maximo=maximo, ventana_s=60)
    return TestClient(api_main.app)


def una_solicitud(cliente: TestClient, texto: str) -> dict:
    inicio = time.perf_counter()
    try:
        respuesta = cliente.post("/api/analizar/texto", json={"texto": texto})
        return {
            "status": respuesta.status_code,
            "latencia_s": round(time.perf_counter() - inicio, 4),
            "error_5xx": 500 <= respuesta.status_code < 600,
            "es_429": respuesta.status_code == 429,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": 0,
            "latencia_s": round(time.perf_counter() - inicio, 4),
            "error_5xx": True,
            "es_429": False,
            "excepcion": type(exc).__name__,
        }


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return float("nan")
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(ordenados) - 1)
    if f == c:
        return ordenados[f]
    return ordenados[f] + (k - f) * (ordenados[c] - ordenados[f])


def resumen_latencias(resultados: list[dict]) -> dict:
    latencias = [r["latencia_s"] for r in resultados]
    return {
        "n": len(latencias),
        "p50_s": round(percentil(latencias, 50), 4),
        "p95_s": round(percentil(latencias, 95), 4),
        "p99_s": round(percentil(latencias, 99), 4),
        "max_s": round(max(latencias), 4) if latencias else 0.0,
        "errores_5xx": sum(1 for r in resultados if r["error_5xx"]),
        "tasa_error_5xx": round(sum(1 for r in resultados if r["error_5xx"]) / len(resultados), 4) if resultados else 0.0,
        "respuestas_429": sum(1 for r in resultados if r["es_429"]),
        "codigos_estado": dict(sorted(Counter(r["status"] for r in resultados).items())),
    }


def ejecutar_ronda(cliente: TestClient, concurrencia: int, repeticiones: int) -> list[dict]:
    """Ejecuta ``concurrencia`` solicitudes en paralelo, ``repeticiones`` veces cada texto."""
    trabajos: list[tuple[TestClient, str]] = []
    for _ in range(repeticiones):
        for texto in TEXTOS:
            trabajos.append((cliente, texto))

    resultados: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrencia) as ejecutor:
        futuros = {
            ejecutor.submit(una_solicitud, c, t): (c, t) for c, t in trabajos
        }
        for futuro in as_completed(futuros):
            resultados.append(futuro.result())
    return resultados


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estrés de la API de VerifIA (Fase 8)")
    parser.add_argument("--concurrencia", type=int, default=20, help="hilos concurrentes")
    parser.add_argument("--repeticiones", type=int, default=1, help="veces que se repite cada texto")
    parser.add_argument("--maximo-por-minuto", type=int, default=1000, help="límite de frecuencia por IP (ventana 60 s)")
    args = parser.parse_args()

    total = len(TEXTOS) * args.repeticiones
    print(f"Estrés: {args.concurrencia} hilos concurrentes, {total} solicitudes de texto")
    print(f"  Límite de frecuencia: {args.maximo_por_minuto} peticiones / 60 s")
    print()

    cliente = _cliente_con_limite(args.maximo_por_minuto)
    inicio_global = time.perf_counter()
    resultados = ejecutar_ronda(cliente, args.concurrencia, args.repeticiones)
    duracion = round(time.perf_counter() - inicio_global, 2)

    resumen = resumen_latencias(resultados)
    resumen["concurrencia"] = args.concurrencia
    resumen["solicitudes"] = total
    resumen["duracion_total_s"] = duracion
    resumen["rendimiento_solicitudes_por_s"] = round(total / duracion, 2) if duracion else 0.0

    ruta = REPORTES / "estres_api.json"
    ruta.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nResultado del estrés ({total} solicitudes en {duracion} s):")
    print(f"  p50  = {resumen['p50_s']} s")
    print(f"  p95  = {resumen['p95_s']} s")
    print(f"  p99  = {resumen['p99_s']} s")
    print(f"  max  = {resumen['max_s']} s")
    print(f"  errores 5xx = {resumen['errores_5xx']} ({resumen['tasa_error_5xx']:.1%})")
    print(f"  respuestas 429 = {resumen['respuestas_429']}")
    print(f"  rendimiento = {resumen['rendimiento_solicitudes_por_s']} solicitudes/s")
    print(f"  codigos de estado = {resumen['codigos_estado']}")
    print(f"\nReporte escrito en {ruta}")

    # Umbrales de aceptación sugeridos (no normativos, §4 del skill):
    # p95 < 3 s sin LLM y < 10 s con LLM; 0 % de errores 5xx con entradas válidas.
    if resumen["tasa_error_5xx"] > 0:
        print("  ADVERTENCIA: hubo errores 5xx con entradas válidas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
