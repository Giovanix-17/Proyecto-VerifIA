"""Generación del corpus sintético con ``nvidia/nemotron-3.5-bolt-e4b``.

Fase 2.2 de ``VerifIA_memoria_proyecto.md``. Características:

- lotes pequeños (5 mensajes por llamada) y *pacing* entre llamadas;
- reanudable: cuenta lo ya generado por tipología y solo pide lo que falta;
- la tipología del LLM se guarda como ``tipologia_borrador``: **la etiqueta
  definitiva la asigna el autor** (§9 Fase 2 y regla 9);
- respuesta tolerante: extrae el primer objeto JSON balanceado, aunque el
  modelo añada razonamiento o bloques Markdown;
- reintentos con espera creciente ante 400/429/5xx/timeout;
- salida en ``data/synthetic/generated.jsonl`` + bitácora de llamadas.

Uso (Docker, sin instalar nada en el host)::

    docker run --rm -v "${PWD}:/app" -w /app --env-file .env verifia:0.1.0 \
        python scripts/corpus_generate.py --per-class 60

Uso con un entorno virtual que tenga ``requirements.txt``::

    python scripts/corpus_generate.py --per-class 60
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from corpus_common import (
    ROOT,
    TIPOLOGIAS,
    ahora_iso,
    escribir_jsonl,
    extraer_primer_json,
    leer_jsonl,
    normalizar_texto,
    resumen,
)

from verifia.classifier.retry import con_reintentos

SALIDA_DEFECTO = ROOT / "data" / "synthetic" / "generated.jsonl"
BITACORA_DEFECTO = ROOT / "data" / "synthetic" / "generation_log.jsonl"

# Definiciones y tácticas por tipología: el prompt no pide "inventar fraude",
# pide variar los pretextos y las señales que el clasificador debe aprender.
PERFILES: dict[str, dict[str, str]] = {
    "suplantacion_bancaria": {
        "pretexto": (
            "un banco, tarjeta de crédito, banca en línea o institución financiera "
            "mexicana (BBVA, Banorte, Santander, HSBC, Scotiabank, Nu, Banamex, "
            "Banco del Bienestar). Nunca uses el nombre real del banco como remitente "
            "verificado ni datos de clientes."
        ),
        "tacticas": (
            "cargo no reconocido, tarjeta bloqueada, cuenta suspendida, actualización "
            "de datos, validación de identidad, supuesto fraude detectado, premio o "
            "devolución; se pide entrar a un enlace, llamar, confirmar un código, "
            "NIP, contraseña o datos de la tarjeta."
        ),
        "escenarios": (
            "cargo no reconocido en la tarjeta; tarjeta bloqueada por seguridad; "
            "cuenta suspendida por intento de acceso; actualización de datos del "
            "cliente; supuesto reembolso o devolución pendiente; validación de "
            "identidad para 'evitar el cierre' de la cuenta; premio o puntos por "
            "canjear; nuevo token o código de seguridad; compra sospechosa en un "
            "comercio; supuesta campaña de protección al usuario"
        ),
        "senales": "urgencia, suplantacion, solicitud_datos, solicitud_codigo, enlace_sospechoso",
    },
    "paqueteria_retenida": {
        "pretexto": (
            "paqueterías y servicios de entrega en México (Amazon, Mercado Libre, "
            "DHL, FedEx, Estafeta, Correos de México, Coppel). El paquete está "
            "retenido, no se pudo entregar o requiere un pago."
        ),
        "tacticas": (
            "aviso de paquete retenido, dirección incompleta, intento de entrega "
            "fallido, cobro de 'derecho de entrega' o 'impuesto aduanal', "
            "reprogramación mediante enlace, plazo de 24-48 horas y devolución."
        ),
        "escenarios": (
            "paquete retenido en aduana; dirección incompleta o incorrecta; intento "
            "de entrega fallido; cobro de derecho de entrega; reprogramación de "
            "entrega; guía de rastreo inválida; paquete devuelto al remitente; "
            "supuesto impuesto aduanal; pedido de Amazon o Mercado Libre; envío de "
            "DHL, FedEx o Estafeta"
        ),
        "senales": "urgencia, suplantacion, enlace_sospechoso, pago_anticipado",
    },
    "oferta_laboral_fraudulenta": {
        "pretexto": (
            "una supuesta empresa, reclutador o plataforma de empleo que ofrece "
            "trabajo desde casa, medio tiempo, por WhatsApp o 'sin experiencia'."
        ),
        "tacticas": (
            "sueldo atractivo, contratación inmediata, pago por adelantado de "
            "uniforme/material/capacitación, solicitud de datos bancarios o de "
            "identificación, pruebas pagadas, comisiones por reclutar, enlaces a "
            "formularios."
        ),
        "escenarios": (
            "asistente remoto o atención a clientes; empacador o armador desde casa; "
            "trabajo por WhatsApp con sueldo diario; contratación inmediata sin "
            "entrevista; pago de uniforme o material de trabajo; prueba o "
            "capacitación pagada; comisiones por reclutar a más personas; solicitud "
            "de datos bancarios para 'depositar el sueldo'; empleo en el extranjero "
            "desde México; oferta de medio tiempo para estudiantes"
        ),
        "senales": "urgencia, suplantacion, solicitud_datos, pago_anticipado, enlace_sospechoso",
    },
    "extorsion": {
        "pretexto": (
            "una amenaza directa a la persona: un supuesto familiar secuestrado, "
            "una deuda con un grupo criminal, un supuesto paquete con contenido "
            "ilegal, una denuncia inventada o la publicación de fotos."
        ),
        "tacticas": (
            "amenaza, plazo corto, exigencia de dinero o transferencia, prohibición "
            "de colgar o avisar, presión emocional, lenguaje soez o intimidante. "
            "No describas violencia gráfica ni datos de personas reales."
        ),
        "escenarios": (
            "supuesto familiar secuestrado o detenido; deuda inventada con un grupo "
            "criminal; paquete con contenido ilegal a nombre de la víctima; denuncia "
            "inventada o citatorio falso; publicación de fotos íntimas; amenaza a un "
            "negocio; 'te tenemos ubicado'; cobro de piso; supuesto accidente de un "
            "familiar; adeudo con una financiera que 'ya pasó a cobranza judicial'"
        ),
        "senales": "amenaza, urgencia, solicitud_datos, pago_anticipado",
    },
}

VARIANTES = [
    "SMS corto (menos de 160 caracteres)",
    "WhatsApp de 2 a 4 frases",
    "mensaje con enlace (usa dominios inventados como pago-seguro-mx.com o "
    "acortadores genéricos; nunca un dominio real)",
    "mensaje sin enlace",
    "mensaje con un monto en pesos mexicanos (por ejemplo $450, $1,850, $7,500)",
    "mensaje con plazo o fecha límite (hoy, 24 horas, antes de las 6 pm)",
    "mensaje con error ortográfico leve o mayúsculas inconsistentes",
    "mensaje formal que imita una notificación institucional",
    "mensaje con número de guía, folio o referencia inventados",
    "mensaje que pide llamar a un número (escribe el número como 55 0000 0000, nunca uno real)",
]

SISTEMA = """Eres un generador de datos de prueba para un proyecto académico \
mexicano de detección de fraude digital. Escribes mensajes ficticios en español \
mexicano, parecidos a los que circulan por SMS y WhatsApp. Reglas obligatorias:

1. Nunca incluyas datos personales reales ni verosímiles: ni teléfonos reales, \
ni correos reales, ni CLABE, tarjeta, CURP o RFC válidos. Usa 55 0000 0000 para \
teléfonos y dominios inventados (example.com o dominios claramente falsos).
2. No nombres personas reales. Puedes usar nombres comunes de pila.
3. Cada mensaje debe ser autosuficiente y distinguible por sus señales \
lingüísticas, no por un nombre propio inventado.
4. Varía longitud, canal, tono, montos, plazos y presencia de enlaces.
5. La salida debe ser un único objeto JSON, sin texto adicional."""


def construir_prompt(tipologia: str, cantidad: int, semilla: int) -> str:
    perfil = PERFILES[tipologia]
    rng = random.Random(semilla)
    variantes = rng.sample(VARIANTES, k=min(cantidad, len(VARIANTES)))
    escenarios = rng.sample(PERFILES[tipologia]["escenarios"].split("; "), k=min(cantidad, 5))
    lista = "\n".join(f"- {v}" for v in variantes)
    lista_escenarios = "\n".join(f"- {e}" for e in escenarios)
    return f"""Genera {cantidad} mensajes ficticios de la tipología "{tipologia}".

Pretexto: {perfil["pretexto"]}

Tácticas que puedes usar: {perfil["tacticas"]}

Señales que debe contener cada mensaje (elige 1 a 3 de esta lista cerrada): \
{perfil["senales"]}.

Escenarios de partida (usa uno distinto por mensaje):
{lista_escenarios}

Incluye al menos estas variantes, una por mensaje:
{lista}

No repitas la misma plantilla cambiando solo el monto. No uses el número \
55 0000 0000 en todos los mensajes: como máximo en uno de cada tres. Varía el \
remitente, el vocabulario y la estructura de las frases. Al menos un mensaje \
debe ser muy breve y otro debe tener tres o cuatro frases.

Devuelve exactamente este JSON:
{{
  "mensajes": [
    {{
      "mensaje": "texto del mensaje",
      "tipologia": "{tipologia}",
      "senales_alerta": ["urgencia"]
    }}
  ]
}}

No agregues explicaciones ni campos extra."""


def _cliente() -> Any:
    from openai import OpenAI

    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "Falta NVIDIA_API_KEY. Copia .env.example a .env y escribe la clave "
            "de https://build.nvidia.com (nunca la pongas en el código)."
        )
    base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    timeout = float(os.getenv("LLM_TIMEOUT_S", "60"))
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)


def _limpiar_senales(valor: Any) -> list[str]:
    from corpus_common import SENALES

    if not isinstance(valor, list):
        return []
    return [s for s in valor if isinstance(s, str) and s in SENALES][:3]


def _normalizar_item(item: dict[str, Any], tipologia_pedida: str) -> dict[str, Any] | None:
    texto = item.get("mensaje") or item.get("texto") or item.get("mensaje_texto")
    if not isinstance(texto, str):
        return None
    texto = normalizar_texto(texto)
    if not 15 <= len(texto) <= 800:
        return None
    borrador = item.get("tipologia")
    if borrador not in TIPOLOGIAS:
        borrador = tipologia_pedida
    return {
        "texto": texto,
        "tipologia_borrador": borrador,
        "senales_alerta": _limpiar_senales(item.get("senales_alerta")),
    }


def llamar_lote(
    cliente: Any,
    modelo: str,
    tipologia: str,
    cantidad: int,
    semilla: int,
    max_tokens: int,
    reasoning_effort: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prompt = construir_prompt(tipologia, cantidad, semilla)
    inicio = time.perf_counter()
    respuesta = con_reintentos(
        lambda: cliente.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": SISTEMA},
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
            top_p=0.95,
            max_tokens=max_tokens,
            extra_body={"reasoning_effort": reasoning_effort},
        ),
        descripcion=f"lote de corpus ({tipologia})",
    )
    latencia = round(time.perf_counter() - inicio, 2)
    contenido = respuesta.choices[0].message.content or ""
    datos = extraer_primer_json(contenido)
    crudos = datos.get("mensajes")
    if not isinstance(crudos, list):
        raise ValueError("La respuesta no contiene la lista 'mensajes'")
    items = [
        x
        for x in (_normalizar_item(i, tipologia) for i in crudos if isinstance(i, dict))
        if x
    ]
    meta = {
        "modelo": modelo,
        "latencia_s": latencia,
        "tokens_entrada": getattr(respuesta.usage, "prompt_tokens", None),
        "tokens_salida": getattr(respuesta.usage, "completion_tokens", None),
        "pedidos": cantidad,
        "recibidos": len(items),
    }
    return items, meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=60, help="sintéticos por clase")
    parser.add_argument("--batch-size", type=int, default=5, help="mensajes por llamada")
    parser.add_argument("--out", type=Path, default=SALIDA_DEFECTO)
    parser.add_argument("--log", type=Path, default=BITACORA_DEFECTO)
    parser.add_argument("--sleep", type=float, default=1.5, help="segundos entre llamadas (pacing)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2600,
        help="tope de salida por lote (el corpus no usa el del Nivel 2)",
    )
    parser.add_argument("--reasoning-effort", default=os.getenv("LLM_REASONING_EFFORT", "low"))
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_CORPUS_MODEL", "nvidia/nemotron-3.5-bolt-e4b"),
    )
    parser.add_argument("--saldo-maximo", type=int, default=400, help="tope de llamadas")
    parser.add_argument("--dry-run", action="store_true", help="solo muestra el plan")
    args = parser.parse_args(argv)

    clases = [t for t in TIPOLOGIAS if t != "legitimo"]
    existentes = leer_jsonl(args.out)
    por_clase = Counter(f.get("tipologia_borrador") for f in existentes)
    faltantes = {
        c: max(0, args.per_class - por_clase.get(c, 0))
        for c in clases
    }
    llamadas_previstas = sum(
        (n + args.batch_size - 1) // args.batch_size for n in faltantes.values()
    )
    print("Plan de generación")
    print(f"  modelo: {args.model}")
    print(f"  ya generados: {len(existentes)} ({dict(por_clase)})")
    print(f"  faltantes por clase: {faltantes}")
    print(f"  llamadas previstas: {llamadas_previstas} (tope {args.saldo_maximo})")
    if llamadas_previstas > args.saldo_maximo:
        print("ERROR: el plan excede el tope de llamadas; reduce --per-class.", file=sys.stderr)
        return 2
    if args.dry_run or llamadas_previstas == 0:
        return 0

    cliente = _cliente()
    rng = random.Random(args.seed)
    corrida = ahora_iso()
    # El contador continúa desde lo ya escrito para que los ids no se repitan
    # al reanudar una generación interrumpida.
    total_nuevos = len(existentes)
    llamadas = 0

    for tipologia in clases:
        faltan = args.per_class - sum(
            1 for f in existentes if f.get("tipologia_borrador") == tipologia
        )
        while faltan > 0:
            cantidad = min(args.batch_size, faltan)
            semilla = rng.randrange(1_000_000)
            meta: dict[str, Any] = {}
            items: list[dict[str, Any]] = []
            error = ""
            for intento in (1, 2):
                try:
                    items, meta = llamar_lote(
                        cliente,
                        args.model,
                        tipologia,
                        cantidad,
                        semilla,
                        args.max_tokens,
                        args.reasoning_effort,
                    )
                    error = ""
                    break
                except Exception as exc:  # noqa: BLE001 - se registra y se reintenta
                    error = f"{type(exc).__name__}: {exc}"
                    if intento == 1:
                        time.sleep(8)
            llamadas += 1
            entrada = {
                "corrida": corrida,
                "timestamp": ahora_iso(),
                "tipologia_pedida": tipologia,
                "cantidad": cantidad,
                "ok": not error,
                "error": error,
                **meta,
            }
            # Se guarda por lote: si la corrida se interrumpe, no se pierde la
            # trazabilidad de las llamadas ya realizadas.
            args.log.parent.mkdir(parents=True, exist_ok=True)
            with args.log.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(entrada, ensure_ascii=False) + "\n")
            if error:
                print(f"  ! {tipologia}: {error}", file=sys.stderr)
            nuevo = 0
            for item in items:
                total_nuevos += 1
                nuevo += 1
                registro = {
                    "id": f"syn-{total_nuevos:04d}",
                    "texto": item["texto"],
                    "tipologia": item["tipologia_borrador"],
                    "tipologia_borrador": item["tipologia_borrador"],
                    "senales_alerta": item["senales_alerta"],
                    "origen": "sintetico_llm",
                    "modelo": args.model,
                    "lote_semilla": semilla,
                    "revision_autor": "pendiente",
                    "creado": ahora_iso(),
                }
                existentes.append(registro)
            faltan -= nuevo
            print(f"  {tipologia}: +{nuevo} (faltan {max(0, faltan)})")
            escribir_jsonl(args.out, existentes)
            time.sleep(args.sleep)

    print(json.dumps(resumen(existentes), ensure_ascii=False, indent=2))
    print(f"Llamadas usadas: {llamadas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
