"""Posprocesamiento del texto OCR (Fase 4).

Une líneas del mismo globo, elimina marcas de hora y separadores de fecha, y
normaliza espacios. Las correcciones son conservadoras: no se reemplazan
palabras completas porque inventar texto altera la señal de fraude.
"""

from __future__ import annotations

import re
from dataclasses import replace

from verifia.ocr.extraccion import LineaOCR
from verifia.ocr.models import OpcionesOCR

_HORA = r"\d{1,2}:\d{2}(?:\s*[ap]\.?\s*m\.?)?"
_MARCA_TIEMPO = re.compile(rf"^\s*{_HORA}\s*$", re.IGNORECASE)
_HORA_AL_FINAL = re.compile(rf"\s+{_HORA}\s*$", re.IGNORECASE)
# En capturas pequeñas Tesseract pierde los dos puntos: «12:34» → «1234».
_HORA_SIN_SEPARADOR = re.compile(r"^\s*\d{1,2}[:.]?\d{2}\s*$")
_HORA_CON_LETRAS = re.compile(r"^\s*\d{1,2}\s*[ap]\.?\s*m\.?\s*$", re.IGNORECASE)
_SEPARADOR_FECHA = re.compile(
    r"^\s*(?:hoy|ayer|anteayer|lunes|martes|miércoles|miercoles|jueves|viernes|"
    r"sábado|sabado|domingo|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*$",
    re.IGNORECASE,
)
_CROMO_DE_APP = re.compile(
    r"^\s*(?:whatsapp|mensajes|sms|telegram|signal|chats|"
    r"escribe un mensaje|type a message)\s*$",
    re.IGNORECASE,
)
_ESPACIOS = re.compile(r"[ \t\u00a0]+")
_SALTOS = re.compile(r"\n{3,}")
# Confusión documentada de Tesseract con el paquete spa: «@» se reconoce como
# «Q» o «G» (a veces precedida de un paréntesis o un espacio espurio) dentro de
# un correo. Solo se corrige si hay una estructura de dominio clara; nunca se
# sustituyen letras sueltas.
_ARROBA_CON_PARENTESIS = re.compile(r"\([QG]+(?=[A-Za-z0-9-]+\.[A-Za-z]{2,}\b)")
_ARROBA_SEPARADA = re.compile(r"\s+[QG](?=[A-Za-z0-9-]+\.[A-Za-z]{2,}\b)")
_ARROBA_CONFUNDIDA = re.compile(
    r"(?<=[A-Za-z0-9._%+-])[QG](?=[A-Za-z0-9-]+\.[A-Za-z]{2,}\b)"
)


def _limpiar_linea(texto: str) -> str:
    limpio = _ESPACIOS.sub(" ", texto).strip()
    limpio = _HORA_AL_FINAL.sub("", limpio).strip()
    limpio = _ARROBA_CON_PARENTESIS.sub("@", limpio)
    limpio = _ARROBA_SEPARADA.sub("@", limpio)
    return _ARROBA_CONFUNDIDA.sub("@", limpio)


def _es_ruido(texto: str) -> bool:
    """Descarta líneas sin contenido (bordes de burbuja, iconos, emojis rotos)."""
    compacto = "".join(caracter for caracter in texto if not caracter.isspace())
    if not compacto:
        return True
    utiles = sum(1 for caracter in compacto if caracter.isalnum())
    if utiles == 0:
        return True
    return len(compacto) >= 3 and utiles / len(compacto) <= 0.4


def _es_ruido_de_borde(linea: LineaOCR, texto: str) -> bool:
    """Restos de hora o borde con baja confianza y sin letras."""
    if linea.confianza is None or linea.confianza >= 60 or len(texto) > 12:
        return False
    if any(caracter.isalpha() for caracter in texto):
        return False
    return any(not caracter.isalnum() and not caracter.isspace() for caracter in texto)


def _altura_letras(lineas: list[LineaOCR]) -> float | None:
    alturas = [
        linea.alto for linea in lineas if any(caracter.isalpha() for caracter in linea.texto)
    ]
    return max(alturas) if alturas else None


def _es_marca_de_hora(linea: LineaOCR, altura_letras: float | None) -> bool:
    texto = _limpiar_linea(linea.texto)
    if _MARCA_TIEMPO.match(texto) or _HORA_CON_LETRAS.match(texto):
        return True
    # Sin dos puntos, solo se descarta si la línea es más baja que el texto:
    # así no se confunden códigos de 4 dígitos escritos en el cuerpo.
    return bool(
        altura_letras
        and linea.alto <= 0.7 * altura_letras
        and _HORA_SIN_SEPARADOR.match(texto)
    )


def _es_linea_pequena(linea: LineaOCR, altura_letras: float | None) -> bool:
    """Descarta etiquetas cortas en cuerpo menor: fechas y horas mal leídas."""
    if not altura_letras:
        return False
    texto = _limpiar_linea(linea.texto)
    return linea.alto <= 0.55 * altura_letras and len(texto) <= 8


def _descartar(linea: LineaOCR, altura_letras: float | None) -> bool:
    texto = _limpiar_linea(linea.texto)
    if not texto:
        return True
    if _es_marca_de_hora(linea, altura_letras) or _es_linea_pequena(linea, altura_letras):
        return True
    if _SEPARADOR_FECHA.match(texto) or _CROMO_DE_APP.match(texto):
        return True
    if _es_ruido_de_borde(linea, texto):
        return True
    return _es_ruido(texto)


def _mismo_globo(anterior: LineaOCR, actual: LineaOCR) -> bool:
    """Heurística conservadora: poco espacio vertical y columnas que se solapan."""
    altura = max(anterior.alto, actual.alto, 1)
    separacion = actual.arriba - anterior.abajo
    if separacion > 0.7 * altura:
        return False

    solape = min(anterior.derecha, actual.derecha) - max(anterior.izquierda, actual.izquierda)
    ancho_anterior = anterior.derecha - anterior.izquierda
    ancho_actual = actual.derecha - actual.izquierda
    ancho_menor = max(1, min(ancho_anterior, ancho_actual))
    return solape >= 0.2 * ancho_menor


def _unir(anterior: LineaOCR, actual: LineaOCR) -> LineaOCR:
    texto_anterior = _limpiar_linea(anterior.texto)
    texto_actual = _limpiar_linea(actual.texto)
    confianzas = [
        (anterior.confianza, len(texto_anterior)),
        (actual.confianza, len(texto_actual)),
    ]
    confianzas = [(conf, largo) for conf, largo in confianzas if conf is not None and largo]
    peso = sum(largo for _, largo in confianzas)
    confianza = sum(conf * largo for conf, largo in confianzas) / peso if peso else None

    return LineaOCR(
        texto=f"{texto_anterior} {texto_actual}".strip(),
        izquierda=min(anterior.izquierda, actual.izquierda),
        arriba=min(anterior.arriba, actual.arriba),
        derecha=max(anterior.derecha, actual.derecha),
        abajo=max(anterior.abajo, actual.abajo),
        confianza=confianza,
    )


def unir_lineas(lineas: list[LineaOCR]) -> list[LineaOCR]:
    """Agrupa líneas del mismo globo (párrafo) sin cruzar burbujas."""
    resultado: list[LineaOCR] = []
    for linea in lineas:
        if resultado and _mismo_globo(resultado[-1], linea):
            resultado[-1] = _unir(resultado[-1], linea)
        else:
            resultado.append(replace(linea, texto=_limpiar_linea(linea.texto)))
    return [linea for linea in resultado if linea.texto]


def posprocesar(lineas: list[LineaOCR], opciones: OpcionesOCR) -> str:
    """Devuelve el texto final, con párrafos separados por saltos de línea."""
    altura_letras = _altura_letras(lineas)
    utiles = [linea for linea in lineas if not _descartar(linea, altura_letras)]
    if opciones.unir_lineas:
        utiles = unir_lineas(utiles)
    else:
        utiles = [replace(linea, texto=_limpiar_linea(linea.texto)) for linea in utiles]
        utiles = [linea for linea in utiles if linea.texto]

    texto = "\n".join(linea.texto for linea in utiles)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = _SALTOS.sub("\n\n", texto)
    return texto.strip()
