"""Utilidades compartidas de la Fase 2 (corpus).

Reúne lo que usan tanto la generación sintética como la construcción del corpus:

- catálogo cerrado de tipologías, orígenes y señales (§8.1 y §8.2);
- normalización de texto y lectura/escritura de JSONL;
- extracción del primer objeto JSON balanceado (misma idea que usará el Nivel 2);
- verificación de PII real (regex + Luhn + dígito de control de CLABE);
- validación del esquema de anotación.

No depende de ``src/verifia`` a propósito: la Fase 3 construirá el sanitizador
con Presidio y volverá a pasar el corpus por él. Aquí se usa un chequeo simple
para no almacenar datos personales desde el primer momento (regla 2).

Uso: se importa desde los otros scripts (``sys.path`` incluye ``scripts/``).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

TIPOLOGIAS = (
    "legitimo",
    "suplantacion_bancaria",
    "paqueteria_retenida",
    "oferta_laboral_fraudulenta",
    "extorsion",
)

ORIGENES = ("publico", "plantilla_legitima", "manual", "sintetico_llm")

SENALES = (
    "urgencia",
    "amenaza",
    "suplantacion",
    "solicitud_datos",
    "solicitud_codigo",
    "enlace_sospechoso",
    "pago_anticipado",
    "premio_falso",
    "error_ortografico",
)

MAX_TEXTO = 10_000

# Dominios reservados que no se reportan como enlace: no son señal.
# El corpus puede usar dominios inventados (como en la guía); se reportan para
# revisión y la Fase 3 los reduce a ``[ENLACE:dominio.tld]``.
DOMINIOS_FICTICIOS = ("example.com", "example.org", "example.net", "invalid")


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
def normalizar_texto(texto: str) -> str:
    """Normaliza sin destruir la señal lingüística.

    - NFC (evita dos formas del mismo carácter);
    - comillas tipográficas y guiones largos a ASCII;
    - saltos de línea uniformes y sin espacios sobrantes por línea;
    - espacios múltiples colapsados; sin espacios al inicio/fin.
    """
    t = unicodedata.normalize("NFC", texto)
    t = (
        t.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
    )
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    lineas = [re.sub(r"[ \t]+", " ", linea).strip() for linea in t.split("\n")]
    t = "\n".join(lineas)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def leer_jsonl(ruta: Path) -> list[dict[str, Any]]:
    """Lee un JSONL ignorando líneas vacías; falla con la línea exacta si hay error."""
    filas: list[dict[str, Any]] = []
    if not ruta.exists():
        return filas
    with ruta.open("r", encoding="utf-8") as fh:
        for numero, linea in enumerate(fh, start=1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                filas.append(json.loads(linea))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{ruta}:{numero}: JSON inválido: {exc}") from exc
    return filas


def escribir_jsonl(ruta: Path, filas: Iterable[dict[str, Any]]) -> int:
    """Escribe JSONL en UTF-8 (sin escapar acentos) y devuelve el número de filas."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with ruta.open("w", encoding="utf-8", newline="\n") as fh:
        for fila in filas:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            n += 1
    return n


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def ahora_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# JSON del LLM
# --------------------------------------------------------------------------- #
def extraer_primer_json(texto: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON balanceado de una respuesta de LLM.

    El modelo puede devolver razonamiento, texto o bloques ```json``` antes del
    objeto útil; por eso no se hace ``json.loads`` de toda la respuesta. Las
    llaves dentro de cadenas se respetan.
    """
    inicio = texto.find("{")
    while inicio != -1:
        profundidad = 0
        en_cadena = False
        escape = False
        for i in range(inicio, len(texto)):
            ch = texto[i]
            if en_cadena:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    en_cadena = False
                continue
            if ch == '"':
                en_cadena = True
            elif ch == "{":
                profundidad += 1
            elif ch == "}":
                profundidad -= 1
                if profundidad == 0:
                    candidato = texto[inicio : i + 1]
                    try:
                        datos = json.loads(candidato)
                    except json.JSONDecodeError:
                        break
                    if isinstance(datos, dict):
                        return datos
                    break
        inicio = texto.find("{", inicio + 1)
    raise ValueError("No se encontró un objeto JSON válido en la respuesta")


# --------------------------------------------------------------------------- #
# PII (chequeo simple de la Fase 2; la Fase 3 usa Presidio)
# --------------------------------------------------------------------------- #
_RE_EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+(?:\.[\w-]+)+)\b", re.IGNORECASE)
_RE_CURP = re.compile(r"\b[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b")
_RE_RFC = re.compile(r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b")
_RE_TELEFONO = re.compile(
    r"(?<!\d)(?:\+?52[\s-]?)?(?:1[\s-]?)?(?:\(?\d{2,3}\)?[\s.-]?)?\d{3,4}[\s.-]\d{4}(?!\d)"
)
_RE_TARJETA = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_RE_CLABE = re.compile(r"(?<!\d)\d{18}(?!\d)")
_RE_URL = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)

_PALABRAS_CLAVE_CODIGO = re.compile(
    r"\b(c[oó]digo|clave|token|otp|pin|nip|cvv|contrase[nñ]a|verificar|confirma|"
    r"n[uú]mero de seguridad)\b",
    re.IGNORECASE,
)


def _luhn(numero: str) -> bool:
    digitos = [int(c) for c in re.sub(r"\D", "", numero)]
    if len(digitos) < 13:
        return False
    if len(set(digitos)) == 1:  # 0000..., 9999... son relleno, no tarjetas
        return False
    suma = 0
    for i, d in enumerate(reversed(digitos)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        suma += d
    return suma % 10 == 0


def _clabe_valida(numero: str) -> bool:
    if len(numero) != 18 or not numero.isdigit():
        return False
    if len(set(numero)) <= 2:  # cuentas de relleno del corpus
        return False
    pesos = (3, 7, 1) * 6
    suma = sum(int(d) * p for d, p in zip(numero[:17], pesos, strict=True))
    return (10 - suma % 10) % 10 == int(numero[17])


def _telefono_placeholder(numero: str) -> bool:
    """Ignora números evidentemente de relleno (0000, 1234, secuencias)."""
    digitos = re.sub(r"\D", "", numero)
    if not 10 <= len(digitos) <= 13:
        return False
    cuerpo = digitos[-10:]
    if len(set(cuerpo)) <= 2:
        return True
    if cuerpo in {"1234567890", "0123456789", "1234567891"}:
        return True
    return False


def detectar_pii(texto: str) -> list[dict[str, str]]:
    """Devuelve hallazgos que *podrían* ser PII real.

    Es deliberadamente conservador (falso positivo aceptable): la Fase 2 debe
    demostrar que el corpus está limpio antes de que exista el sanitizador.
    Los dominios ``example.*``/``invalid`` y los teléfonos de relleno no cuentan.
    """
    hallazgos: list[dict[str, str]] = []

    for m in _RE_EMAIL.finditer(texto):
        dominio = m.group(1).lower()
        if not any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_FICTICIOS):
            hallazgos.append({"tipo": "correo", "valor": m.group(0)})

    for m in _RE_URL.finditer(texto):
        url = m.group(0).rstrip(".,;:)")
        dominio = re.sub(r"^https?://", "", url, flags=re.IGNORECASE).split("/")[0].lower()
        dominio = dominio.removeprefix("www.")
        if not any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS_FICTICIOS):
            # Un enlace real no es PII por sí mismo, pero sí es señal y dominio
            # verificable. Se reporta aparte para revisión, no se elimina.
            hallazgos.append({"tipo": "enlace", "valor": url})

    for m in _RE_CURP.finditer(texto):
        hallazgos.append({"tipo": "curp", "valor": m.group(0)})

    for m in _RE_RFC.finditer(texto):
        if not _RE_CURP.fullmatch(m.group(0)):
            hallazgos.append({"tipo": "rfc", "valor": m.group(0)})

    # Los trozos de una tarjeta o CLABE pueden parecer teléfonos; se excluyen.
    spans_numeros_largos = [(m.start(), m.end()) for m in _RE_TARJETA.finditer(texto)] + [
        (m.start(), m.end()) for m in _RE_CLABE.finditer(texto)
    ]

    for m in _RE_CLABE.finditer(texto):
        if _clabe_valida(m.group(0)):
            hallazgos.append({"tipo": "clabe", "valor": m.group(0)})

    for m in _RE_TARJETA.finditer(texto):
        candidato = m.group(0).strip()
        if _luhn(candidato):
            hallazgos.append({"tipo": "tarjeta", "valor": candidato})

    for m in _RE_TELEFONO.finditer(texto):
        dentro_de_numero_largo = any(
            m.start() >= inicio and m.end() <= fin for inicio, fin in spans_numeros_largos
        )
        if not dentro_de_numero_largo and not _telefono_placeholder(m.group(0)):
            # Solo cuenta como PII si hay contexto de contacto o el formato es
            # claramente telefónico (+52, paréntesis, guiones).
            ventana = texto[max(0, m.start() - 40) : m.end() + 40].lower()
            parece_contacto = bool(
                re.search(r"\+52|\(\d{2,3}\)|marcar|llama|comunicate|whatsapp|tel[eé]fono", ventana)
            )
            if parece_contacto:
                hallazgos.append({"tipo": "telefono", "valor": m.group(0)})

    # Códigos: no son PII por sí mismos; se reportan solo si hay contexto.
    for m in re.finditer(r"(?<!\d)\d{4,8}(?!\d)", texto):
        ventana = texto[max(0, m.start() - 30) : m.end() + 30]
        if _PALABRAS_CLAVE_CODIGO.search(ventana):
            hallazgos.append({"tipo": "codigo_contexto", "valor": m.group(0)})

    return hallazgos


# --------------------------------------------------------------------------- #
# Validación del esquema
# --------------------------------------------------------------------------- #
def validar_mensaje(fila: dict[str, Any]) -> list[str]:
    """Devuelve la lista de problemas del registro (vacía = válido)."""
    errores: list[str] = []
    for campo in ("id", "texto", "tipologia", "origen"):
        if not str(fila.get(campo, "")).strip():
            errores.append(f"campo obligatorio vacío: {campo}")
    if fila.get("tipologia") not in TIPOLOGIAS:
        errores.append(f"tipologia inválida: {fila.get('tipologia')!r}")
    if fila.get("origen") not in ORIGENES:
        errores.append(f"origen inválido: {fila.get('origen')!r}")
    texto = fila.get("texto", "")
    if len(texto) > MAX_TEXTO:
        errores.append(f"texto demasiado largo: {len(texto)} > {MAX_TEXTO}")
    senales = fila.get("senales_alerta") or []
    if not isinstance(senales, list):
        errores.append("senales_alerta debe ser lista")
    else:
        desconocidas = sorted(set(senales) - set(SENALES))
        if desconocidas:
            errores.append(f"señales desconocidas: {desconocidas}")
    return errores


def contar_por(filas: Iterable[dict[str, Any]], campo: str) -> dict[str, int]:
    return dict(sorted(Counter(f.get(campo, "") for f in filas).items()))


def resumen(filas: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(filas),
        "por_tipologia": contar_por(filas, "tipologia"),
        "por_origen": contar_por(filas, "origen"),
    }
