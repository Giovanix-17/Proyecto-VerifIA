"""Prueba de humo de los modelos de la API de NVIDIA.

Verifica, con una llamada por modelo, que la clave funciona, que el modelo está
disponible y que la respuesta se puede interpretar:

- ``LLM_CORPUS_MODEL``: usa el prompt real de generación de corpus;
- ``LLM_MODEL``: clasificación con salida JSON (Nivel 2);
- ``LLM_REVIEWER_MODEL``: clasificación con salida JSON (revisor).

No modifica el corpus ni escribe archivos. Devuelve código 1 si algún modelo
falla, para que pueda usarse en una comprobación automática.

Uso::

    docker run --rm --env-file .env -v "${PWD}:/app" -w /app verifia:0.1.0 \
      python scripts/verificar_api.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_common import extraer_primer_json
from corpus_generate import llamar_lote

PROMPT_CLASIFICACION = """Clasifica este mensaje en una de estas cinco clases:
legitimo, suplantacion_bancaria, paqueteria_retenida,
oferta_laboral_fraudulenta, extorsion.

Mensaje: "Banco: su cuenta será bloqueada hoy; comparta el código que recibió."

Devuelve solo un objeto JSON con el campo "tipologia". No agregues texto."""


def _cliente() -> OpenAI:
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta NVIDIA_API_KEY en el entorno.")
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        timeout=90.0,
        max_retries=0,
    )


def _probar_corpus(cliente: OpenAI, modelo: str) -> bool:
    inicio = time.perf_counter()
    try:
        items, meta = llamar_lote(
            cliente,
            modelo,
            "suplantacion_bancaria",
            1,
            123456,
            2000,
            "low",
        )
        latencia = round(time.perf_counter() - inicio, 2)
        print(
            f"[corpus] OK  modelo={modelo}  latencia={latencia}s  "
            f"items={len(items)}  tokens={meta.get('tokens_entrada')}/"
            f"{meta.get('tokens_salida')}"
        )
        if not items:
            print("         ADVERTENCIA: no se normalizó ningún mensaje")
            return False
        print(f"         texto={items[0]['texto'][:120]!r}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[corpus] ERROR modelo={modelo}  {type(exc).__name__}: {str(exc)[:250]}")
        return False


def _probar_clasificacion(cliente: OpenAI, rol: str, modelo: str) -> bool:
    inicio = time.perf_counter()
    try:
        respuesta = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": "Eres un clasificador de fraude."},
                {"role": "user", "content": PROMPT_CLASIFICACION},
            ],
            temperature=0,
            max_tokens=500,
            extra_body={"reasoning_effort": "low"},
        )
        latencia = round(time.perf_counter() - inicio, 2)
        contenido = respuesta.choices[0].message.content or ""
        datos = extraer_primer_json(contenido)
        uso = respuesta.usage
        print(
            f"[{rol}] OK  modelo={modelo}  latencia={latencia}s  "
            f"tokens={getattr(uso, 'prompt_tokens', None)}/"
            f"{getattr(uso, 'completion_tokens', None)}  "
            f"json={json.dumps(datos, ensure_ascii=False)}"
        )
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[{rol}] ERROR modelo={modelo}  {type(exc).__name__}: {str(exc)[:250]}")
        return False


def main() -> int:
    cliente = _cliente()
    modelos = {
        "corpus": os.getenv("LLM_CORPUS_MODEL", "nvidia/nemotron-3.5-bolt-e4b"),
        "nivel2": os.getenv("LLM_MODEL", "deepseek-ai/deepseek-v4.1-flash"),
        "revisor": os.getenv("LLM_REVIEWER_MODEL", "minimaxai/minimax-m3.1-flash"),
    }
    print(f"Endpoint: {cliente.base_url}")
    print(f"Modelos: {json.dumps(modelos, ensure_ascii=False)}")

    resultados = [
        _probar_corpus(cliente, modelos["corpus"]),
        _probar_clasificacion(cliente, "nivel2", modelos["nivel2"]),
        _probar_clasificacion(cliente, "revisor", modelos["revisor"]),
    ]
    if modelos["nivel2"] == modelos["revisor"]:
        print(
            "ADVERTENCIA: Nivel 2 y revisor usan el mismo modelo; revisa la regla "
            "de no circularidad del §8.7."
        )
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
