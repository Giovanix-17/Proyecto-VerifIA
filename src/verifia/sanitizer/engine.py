"""Motor de sanitización: orquesta Presidio, los enlaces y el enmascarado.

Principios aplicados (memoria §7):

* Se enmascara antes de que cualquier clasificador vea el texto.
* Los marcadores conservan la señal, no el dato.
* Los enlaces se reducen a su dominio registrable.
* La resolución de solapamientos es determinista: primero lo específico
  (tarjeta, CLABE, CURP, RFC), al final los nombres.

El módulo **no decide riesgo**: solo enmascara y devuelve rasgos.
"""

from __future__ import annotations

import re
import threading
from collections import Counter
from dataclasses import dataclass

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import SpacyRecognizer

from verifia.sanitizer.links import EnlaceDetectado, extraer_enlaces, spans_correo
from verifia.sanitizer.models import RasgoEnlace, TextoSanitizado
from verifia.sanitizer.recognizers import (
    ENTIDAD_CLABE,
    ENTIDAD_CODIGO,
    ENTIDAD_CORREO,
    ENTIDAD_CURP,
    ENTIDAD_NOMBRE,
    ENTIDAD_RFC,
    ENTIDAD_TARJETA,
    ENTIDAD_TELEFONO,
    codigo_con_contexto,
    construir_reconocedores,
    telefono_con_contexto,
)
from verifia.sanitizer.validators import sin_acentos

MODELO_SPACY = "es_core_news_md"

# Entidad de Presidio -> marcador del catálogo cerrado (regla 3).
ENTIDAD_A_MARCADOR: dict[str, str] = {
    ENTIDAD_TARJETA: "[TARJETA]",
    ENTIDAD_CLABE: "[CUENTA]",
    ENTIDAD_CURP: "[CURP]",
    ENTIDAD_RFC: "[RFC]",
    ENTIDAD_CORREO: "[CORREO]",
    ENTIDAD_TELEFONO: "[TELEFONO]",
    ENTIDAD_CODIGO: "[CODIGO]",
    ENTIDAD_NOMBRE: "[NOMBRE]",
}

# Orden de especificidad para resolver solapamientos (skill, "Orden de aplicación").
PRIORIDAD_ENTIDAD: dict[str, int] = {
    ENTIDAD_TARJETA: 0,
    ENTIDAD_CLABE: 1,
    ENTIDAD_CURP: 2,
    ENTIDAD_RFC: 3,
    ENTIDAD_CORREO: 4,
    ENTIDAD_TELEFONO: 5,
    ENTIDAD_CODIGO: 6,
    "ENLACE": 7,
    ENTIDAD_NOMBRE: 8,
}

# Umbral mínimo por entidad. Presidio ya aplica el umbral de cada reconocedor;
# este filtro es la última barrera antes del enmascarado.
UMBRAL_MINIMO: dict[str, float] = {
    ENTIDAD_TARJETA: 0.5,
    ENTIDAD_CLABE: 0.5,
    ENTIDAD_CURP: 0.5,
    ENTIDAD_RFC: 0.5,
    ENTIDAD_CORREO: 0.5,
    ENTIDAD_TELEFONO: 0.5,
    ENTIDAD_CODIGO: 0.5,
    ENTIDAD_NOMBRE: 0.5,
}

# Marcadores ya aplicados: se ocultan antes de volver a analizar para que la
# sanitización sea idempotente y no se enmascare dentro de un marcador.
_MARCADOR_RE = re.compile(
    r"\[(?:TELEFONO|CORREO|NOMBRE|CUENTA|TARJETA|CODIGO|CURP|RFC|"
    r"ENLACE:[^\]\s]+)\]"
)

# Palabras que el NER puede incluir al inicio de un nombre y que no forman parte
# de él (tratamientos y saludos).
_PALABRAS_NO_NOMBRE = frozenset(
    {
        "hola",
        "buenas",
        "buenos",
        "dias",
        "tardes",
        "noches",
        "estimado",
        "estimada",
        "atentamente",
        "saludos",
        "sr",
        "sra",
        "srta",
        "senor",
        "senora",
        "don",
        "dona",
        "lic",
        "licenciado",
        "licenciada",
        "doctor",
        "doctora",
        "dra",
        "dr",
        "ingeniero",
        "ingeniera",
        "ing",
        "profesor",
        "profesora",
        "profe",
    }
)

# Conectores que pueden aparecer dentro de un nombre compuesto.
_CONECTORES_NOMBRE = frozenset(
    {
        "de",
        "del",
        "la",
        "las",
        "los",
        "y",
        "e",
        "da",
        "das",
        "do",
        "dos",
        "van",
        "von",
        "di",
        "der",
        "al",
    }
)

# Nombres de instituciones que, si el NER los confunde con personas, no deben
# enmascararse como nombre propio.
_NO_SON_NOMBRES = frozenset(
    {
        "banco",
        "gobierno",
        "fiscalia",
        "policia",
        "sat",
        "imss",
        "infonavit",
        "profeco",
        "condusef",
        "bbva",
        "banorte",
        "banamex",
        "santander",
        "hsbc",
        "mercado libre",
        "amazon",
        "whatsapp",
        "facebook",
        "correo",
        "telcel",
        "telmex",
        "att",
        # Verbos en imperativo frecuentes al inicio de un mensaje; spaCy los
        # etiqueta como PROPN cuando abren la oración.
        "rastrea",
        "verifica",
        "confirma",
        "ingresa",
        "accede",
        "paga",
        "llama",
        "marca",
        "escribe",
        "comunicate",
        "deposita",
        "transfiere",
        "revisa",
        "consulta",
        "compra",
        "actualiza",
        "descarga",
        "envia",
        "recibe",
        "gana",
        "reclama",
        "responde",
        "comparte",
        "abre",
        "solicita",
        "espera",
        "contesta",
        "visita",
        "haz",
    }
)

_analizador: AnalyzerEngine | None = None
_candado = threading.Lock()


class ErrorSanitizacion(RuntimeError):
    """Falla del motor de sanitización.

    Se propaga para que el llamador **no clasifique texto sin sanitizar**.
    """


@dataclass
class _Candidato:
    inicio: int
    fin: int
    entidad: str
    marcador: str
    score: float
    rasgos: RasgoEnlace | None = None


def _construir_analizador() -> AnalyzerEngine:
    """Crea el ``AnalyzerEngine`` con el NER español y solo los reconocedores MX.

    Se construye un registro vacío para no cargar los reconocedores por defecto
    en inglés, que producirían entidades espurias (skill, "Configuración del
    motor").
    """
    proveedor = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "es", "model_name": MODELO_SPACY}],
        }
    )
    motor_nlp = proveedor.create_engine()

    registro = RecognizerRegistry(supported_languages=["es"])
    registro.add_recognizer(
        SpacyRecognizer(supported_language="es", supported_entities=[ENTIDAD_NOMBRE])
    )
    for reconocedor in construir_reconocedores():
        registro.add_recognizer(reconocedor)

    return AnalyzerEngine(
        nlp_engine=motor_nlp,
        registry=registro,
        supported_languages=["es"],
    )


def obtener_analizador() -> AnalyzerEngine:
    """Devuelve el analizador compartido, cargándolo la primera vez.

    La carga de spaCy tarda unos segundos; se hace una sola vez por proceso.
    """
    global _analizador
    if _analizador is None:
        with _candado:
            if _analizador is None:
                try:
                    _analizador = _construir_analizador()
                except Exception as exc:  # pragma: no cover - depende del entorno
                    raise ErrorSanitizacion(
                        "No se pudo cargar el motor de sanitización (Presidio + spaCy es)."
                    ) from exc
    return _analizador


def _ocultar_rangos(texto: str, rangos: list[tuple[int, int]]) -> str:
    """Sustituye cada rango por espacios, conservando índices y saltos de línea."""
    if not rangos:
        return texto
    caracteres = list(texto)
    for inicio, fin in rangos:
        for posicion in range(max(0, inicio), min(len(caracteres), fin)):
            if caracteres[posicion] not in "\r\n":
                caracteres[posicion] = " "
    return "".join(caracteres)


def _limpiar_token(token: str) -> str:
    return token.strip(".,;:()[]{}<>\"'¿?¡!«»")


def _recortar_nombre(texto: str, inicio: int, fin: int) -> tuple[int, int] | None:
    """Recorta un span ``PERSON`` para que no trague palabras de la oración.

    El modelo español a veces extiende la entidad más allá del nombre
    ("Juan Pérez y mi teléfono"). Se conservan las palabras capitalizadas y los
    conectores internos, y se corta en la primera palabra que no lo sea.
    """
    fragmento = texto[inicio:fin]
    tokens: list[tuple[str, int, int]] = []
    for coincidencia in re.finditer(r"\S+", fragmento):
        limpio = _limpiar_token(coincidencia.group(0))
        if not limpio:
            continue
        tokens.append((limpio, coincidencia.start(), coincidencia.end()))

    if not tokens:
        return None

    # Quita tratamientos y saludos del inicio.
    while tokens and sin_acentos(tokens[0][0]) in _PALABRAS_NO_NOMBRE:
        tokens.pop(0)
    if not tokens:
        return None

    conservados: list[tuple[str, int, int]] = []
    for token, rel_inicio, rel_fin in tokens:
        normalizado = sin_acentos(token)
        capitalizado = token[0].isupper() or token.isupper()
        if capitalizado:
            conservados.append((token, rel_inicio, rel_fin))
        elif normalizado in _CONECTORES_NOMBRE and conservados:
            conservados.append((token, rel_inicio, rel_fin))
        else:
            break

    # Un conector al final no forma parte del nombre.
    while conservados and sin_acentos(conservados[-1][0]) in _CONECTORES_NOMBRE:
        conservados.pop()
    if not conservados:
        return None

    nombre = " ".join(token for token, _, _ in conservados)
    if sin_acentos(nombre) in _NO_SON_NOMBRES:
        return None
    if len(conservados) == 1 and sin_acentos(conservados[0][0]) in _NO_SON_NOMBRES:
        return None

    return inicio + conservados[0][1], inicio + conservados[-1][2]


def _resolver(candidatos: list[_Candidato]) -> list[_Candidato]:
    """Elige spans no solapados por especificidad, longitud y score."""
    ordenados = sorted(
        candidatos,
        key=lambda c: (
            PRIORIDAD_ENTIDAD.get(c.entidad, 99),
            -(c.fin - c.inicio),
            -c.score,
            c.inicio,
        ),
    )

    aceptados: list[_Candidato] = []
    for candidato in ordenados:
        if candidato.fin <= candidato.inicio:
            continue
        solapa = any(
            candidato.inicio < aceptado.fin and aceptado.inicio < candidato.fin
            for aceptado in aceptados
        )
        if not solapa:
            aceptados.append(candidato)

    return sorted(aceptados, key=lambda c: c.inicio)


def _aplicar(texto: str, aceptados: list[_Candidato]) -> str:
    """Sustituye los spans de derecha a izquierda para no desplazar índices."""
    partes: list[str] = []
    cursor = len(texto)

    for candidato in sorted(aceptados, key=lambda c: c.inicio, reverse=True):
        partes.append(texto[candidato.fin : cursor])
        partes.append(candidato.marcador)
        cursor = candidato.inicio

    partes.append(texto[:cursor])
    return "".join(reversed(partes))


def _nombre_con_propn(artefactos, inicio: int, fin: int) -> bool:  # noqa: ANN001
    """Exige que el span de nombre contenga al menos un nombre propio.

    Evita falsos positivos del NER con verbos en imperativo al inicio de la
    oración (por ejemplo, "Rastrea" en "Rastrea tu paquete").
    """
    doc = getattr(artefactos, "tokens", None)
    if doc is None or not hasattr(doc, "char_span"):
        return True
    span = doc.char_span(inicio, fin, alignment_mode="expand")
    if span is None:
        return True
    return any(token.pos_ == "PROPN" for token in span)


def sanitizar(texto: str) -> TextoSanitizado:
    """Enmascara los datos personales de ``texto`` y devuelve el contrato.

    Es determinista e idempotente en el texto: aplicar dos veces produce el
    mismo resultado. No guarda ni registra el texto original.
    """
    resultado, _ = _sanitizar_con_spans(texto)
    return resultado


def _sanitizar_con_spans(texto: str) -> tuple[TextoSanitizado, list[_Candidato]]:
    """Implementación compartida; devuelve también los spans para evaluación.

    Los spans solo viven en memoria y no contienen el valor original: son
    posiciones y marcadores. La API pública no los expone.
    """
    if not isinstance(texto, str):
        raise TypeError("El texto a sanitizar debe ser una cadena.")

    if not texto.strip():
        return TextoSanitizado(texto=texto), []

    # 1. Ocultar marcadores ya presentes (idempotencia).
    base = _MARCADOR_RE.sub(lambda m: " " * len(m.group(0)), texto)

    # 2. Localizar enlaces sin confundir correos con dominios sueltos.
    correos = spans_correo(base)
    enlaces: list[EnlaceDetectado] = extraer_enlaces(base, correos)

    # 3. Ocultar los enlaces antes de Presidio: ni el teléfono de la query ni
    #    la ruta deben detectarse como PII independiente.
    trabajo = _ocultar_rangos(base, [(e.inicio, e.fin) for e in enlaces])

    # 4. Presidio: formatos mexicanos + NER español para nombres.
    try:
        analizador = obtener_analizador()
        artefactos = analizador.nlp_engine.process_text(trabajo, "es")
        resultados = analizador.analyze(
            text=trabajo,
            language="es",
            entities=[
                ENTIDAD_TARJETA,
                ENTIDAD_CLABE,
                ENTIDAD_CURP,
                ENTIDAD_RFC,
                ENTIDAD_CORREO,
                ENTIDAD_TELEFONO,
                ENTIDAD_CODIGO,
                ENTIDAD_NOMBRE,
            ],
            nlp_artifacts=artefactos,
        )
    except ErrorSanitizacion:
        raise
    except Exception as exc:  # pragma: no cover - depende del entorno
        raise ErrorSanitizacion("Falló el análisis de datos personales.") from exc

    # 5. Convertir resultados en candidatos, aplicando los filtros de contexto.
    candidatos: list[_Candidato] = []
    for resultado in resultados:
        entidad = resultado.entity_type
        marcador = ENTIDAD_A_MARCADOR.get(entidad)
        if marcador is None:
            continue
        if resultado.score < UMBRAL_MINIMO.get(entidad, 0.5):
            continue

        if entidad == ENTIDAD_CODIGO and not codigo_con_contexto(
            trabajo, resultado.start, resultado.end
        ):
            continue
        if entidad == ENTIDAD_TELEFONO and not telefono_con_contexto(
            trabajo, resultado.start, resultado.end
        ):
            continue

        inicio, fin = resultado.start, resultado.end
        if entidad == ENTIDAD_NOMBRE:
            recorte = _recortar_nombre(trabajo, inicio, fin)
            if recorte is None:
                continue
            inicio, fin = recorte
            if not _nombre_con_propn(artefactos, inicio, fin):
                continue

        candidatos.append(
            _Candidato(
                inicio=inicio,
                fin=fin,
                entidad=entidad,
                marcador=marcador,
                score=resultado.score,
            )
        )

    # 6. Los enlaces compiten con prioridad baja, pero conservan su dominio.
    for enlace in enlaces:
        candidatos.append(
            _Candidato(
                inicio=enlace.inicio,
                fin=enlace.fin,
                entidad="ENLACE",
                marcador=enlace.marcador,
                score=1.0,
                rasgos=enlace.rasgos,
            )
        )

    # 7. Resolver solapamientos y sustituir.
    aceptados = _resolver(candidatos)
    salida = _aplicar(texto, aceptados)

    conteo = Counter(candidato.marcador for candidato in aceptados)
    rasgos = [
        candidato.rasgos
        for candidato in aceptados
        if candidato.entidad == "ENLACE" and candidato.rasgos is not None
    ]

    return (
        TextoSanitizado(
            texto=salida,
            marcadores=dict(conteo),
            rasgos_enlace=rasgos,
            entidades=len(aceptados),
        ),
        aceptados,
    )
