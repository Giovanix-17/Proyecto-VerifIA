"""Reconocedores de Presidio para los formatos mexicanos de la Fase 3.

Cada regla de formato es un ``PatternRecognizer`` con ``validate_result`` para
los dígitos de control (Luhn, CLABE) y la estructura (CURP, RFC, teléfono).
Los nombres de persona se detectan con el NER español de spaCy mediante el
``SpacyRecognizer`` de Presidio.

Fuente: VerifIA_memoria_proyecto.md §9 Fase 3 y skill ``verifia-sanitizacion``.
"""

from __future__ import annotations

import re

from presidio_analyzer import EntityRecognizer, Pattern, PatternRecognizer, RecognizerResult

from verifia.sanitizer.validators import (
    es_curp,
    es_rfc,
    es_telefono_mx,
    pasa_clabe,
    pasa_luhn,
    sin_acentos,
    solo_digitos,
)

# Entidades internas de Presidio. Se traducen a marcadores en engine.py.
ENTIDAD_TARJETA = "MX_TARJETA"
ENTIDAD_CLABE = "MX_CLABE"
ENTIDAD_CURP = "MX_CURP"
ENTIDAD_RFC = "MX_RFC"
ENTIDAD_CORREO = "EMAIL_ADDRESS"
ENTIDAD_TELEFONO = "MX_TELEFONO"
ENTIDAD_CODIGO = "MX_CODIGO"
ENTIDAD_NOMBRE = "PERSON"

ENTIDADES_NUMERICAS = (
    ENTIDAD_TARJETA,
    ENTIDAD_CLABE,
    ENTIDAD_CURP,
    ENTIDAD_RFC,
)

# Palabras que, cerca de un número de 4-8 dígitos, indican que se está
# solicitando un código (regla §7.1). Se comparan sin acentos y en minúsculas.
PALABRAS_SOLICITUD_CODIGO = (
    "codigo",
    "clave",
    "token",
    "otp",
    "pin",
    "nip",
    "cvv",
    "contrasena",
    "verificar",
    "verifica",
    "confirma",
    "confirmar",
    "numero de seguridad",
    "seguridad",
)

# Contextos que descartan un número como código: montos, folios, fechas, etc.
PATRON_CONTEXTO_NO_CODIGO = re.compile(
    r"\b(codigo postal|folio|pedido|orden|guia|referencia|factura|recibo|"
    r"fecha|hora|ano|porcentaje|pesos|mxn)\b|\bpor ciento\b|%"
)

PATRON_CONTEXTO_NO_TELEFONO = re.compile(
    r"\b(folio|pedido|orden|guia|referencia|factura|recibo|autorizacion|"
    r"pesos|mxn)\b|\bpor ciento\b|%"
)


def _normalizar_ventana(texto: str) -> str:
    return sin_acentos(texto)


_TRATAMIENTO_NOMBRE_RE = re.compile(
    r"\b(?i:lic|licenciado|licenciada|sr|sra|srta|señor|senor|señora|senora|"
    r"don|doña|dona|dr|dra|doctor|doctora|ing|ingeniero|ingeniera|profesor|"
    r"profesora|profe)\.?\s+"
    r"(?P<nombre>"
    r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|[A-ZÁÉÍÓÚÑ]{2,})"
    r"(?:\s+(?:(?i:de|del|la|las|los|y)\s+)?"
    r"(?:[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+|[A-ZÁÉÍÓÚÑ]{2,})){0,4}"
    r")"
)


class NombreTratamientoRecognizer(EntityRecognizer):
    """Respaldo del NER para nombres precedidos por un tratamiento.

    spaCy a veces etiqueta ``Lic. Roberto Morales`` como organización. Esta
    regla recupera el nombre que sigue al tratamiento; el filtro de categoría
    gramatical de :mod:`verifia.sanitizer.engine` evita falsos positivos.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entities=[ENTIDAD_NOMBRE],
            supported_language="es",
            name="NombreTratamientoRecognizer",
            version="1.0.0",
        )

    def load(self) -> None:
        """No requiere recursos externos."""

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts=None,  # noqa: ANN001
    ) -> list[RecognizerResult]:
        if ENTIDAD_NOMBRE not in entities:
            return []

        resultados: list[RecognizerResult] = []
        for coincidencia in _TRATAMIENTO_NOMBRE_RE.finditer(text):
            inicio, fin = coincidencia.span("nombre")
            resultados.append(
                RecognizerResult(
                    entity_type=ENTIDAD_NOMBRE,
                    start=inicio,
                    end=fin,
                    score=0.7,
                )
            )
        return resultados


class TarjetaRecognizer(PatternRecognizer):
    """Tarjeta de 13-19 dígitos que pasa el algoritmo de Luhn.

    Rechaza las CLABE válidas de 18 dígitos para que las reclame
    ``ClabeRecognizer`` y no se confundan ambas entidades.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_TARJETA,
            supported_language="es",
            patterns=[
                Pattern(
                    name="tarjeta_luhn",
                    regex=r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])",
                    score=0.85,
                )
            ],
            context=["tarjeta", "terminacion", "debito", "credito", "banco"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        digitos = solo_digitos(pattern_text)
        if len(digitos) == 18 and pasa_clabe(digitos):
            return False
        # Un teléfono con +52 y 13 dígitos también puede pasar Luhn por azar;
        # en ese caso gana el reconocedor de teléfono.
        if len(digitos) in (12, 13) and es_telefono_mx(pattern_text):
            return False
        return pasa_luhn(digitos)


class ClabeRecognizer(PatternRecognizer):
    """Cuenta CLABE de 18 dígitos con dígito de control válido."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_CLABE,
            supported_language="es",
            patterns=[
                Pattern(
                    name="clabe_18_digitos",
                    regex=r"(?<!\d)(?:\d[ -]?){17}\d(?!\d)",
                    score=0.85,
                )
            ],
            context=["clabe", "cuenta", "banco", "transferencia", "deposito"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        return pasa_clabe(solo_digitos(pattern_text))


class CurpRecognizer(PatternRecognizer):
    """CURP de 18 caracteres con estructura y entidad federativa válidas."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_CURP,
            supported_language="es",
            patterns=[
                Pattern(
                    name="curp_mx",
                    regex=(
                        r"\b[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{2}"
                        r"[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d\b"
                    ),
                    score=0.85,
                )
            ],
            context=["curp", "identificacion", "clave unica"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        return es_curp(pattern_text)


class RfcRecognizer(PatternRecognizer):
    """RFC de persona física (13) o moral (12) con fecha válida."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_RFC,
            supported_language="es",
            patterns=[
                Pattern(
                    name="rfc_mx",
                    regex=r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b",
                    score=0.85,
                )
            ],
            context=["rfc", "factura", "sat", "contribuyente"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        return es_rfc(pattern_text)


class CorreoRecognizer(PatternRecognizer):
    """Correo electrónico con una simplificación de RFC 5322."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_CORREO,
            supported_language="es",
            patterns=[
                Pattern(
                    name="correo_electronico",
                    regex=(
                        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
                        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                        r"(?:\.[A-Za-z]{2,24})+"
                    ),
                    score=0.85,
                )
            ],
            context=["correo", "email", "escribe", "contacto"],
        )


class TelefonoRecognizer(PatternRecognizer):
    """Teléfono mexicano de 10 dígitos, con separadores y ``+52`` opcional.

    También acepta 10 dígitos contiguos; el contexto permite descartar folios
    y montos en :mod:`verifia.sanitizer.engine`.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_TELEFONO,
            supported_language="es",
            patterns=[
                Pattern(
                    name="telefono_con_separadores",
                    regex=(
                        r"(?<!\d)(?:\+\s?52[\s.-]?(?:1[\s.-])?)?"
                        r"(?:\(\d{2,4}\)[\s.-]?|\d{2,4}[\s.-])"
                        r"(?:\d{2,4}[\s.-]){0,2}\d{2,4}(?!\d)"
                    ),
                    score=0.8,
                ),
                Pattern(
                    name="telefono_contiguo",
                    regex=r"(?<!\d)\d{10}(?!\d)",
                    score=0.6,
                ),
            ],
            context=["telefono", "llamar", "llama", "marcar", "whatsapp", "celular"],
        )

    def validate_result(self, pattern_text: str) -> bool:
        return es_telefono_mx(pattern_text)


class CodigoRecognizer(PatternRecognizer):
    """Número de 4-8 dígitos; el contexto de solicitud se valida en engine.

    El patrón es deliberadamente laxo (incluye separadores tipo ``4-5-3-1``)
    y el filtro de §7.1 se aplica después, cuando ya se conoce el texto
    completo y no solo el fragmento detectado por Presidio.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity=ENTIDAD_CODIGO,
            supported_language="es",
            patterns=[
                Pattern(
                    name="codigo_4_a_8_digitos",
                    regex=r"(?<!\d)(?:\d[\s.-]?){3,7}\d(?!\d)",
                    score=0.6,
                )
            ],
            context=list(PALABRAS_SOLICITUD_CODIGO),
        )


def construir_reconocedores() -> list[EntityRecognizer]:
    """Crea una instancia nueva de cada reconocedor de formato."""
    return [
        TarjetaRecognizer(),
        ClabeRecognizer(),
        CurpRecognizer(),
        RfcRecognizer(),
        CorreoRecognizer(),
        TelefonoRecognizer(),
        CodigoRecognizer(),
        NombreTratamientoRecognizer(),
    ]


# ---------------------------------------------------------------------------
# Filtros de contexto que necesitan el texto completo
# ---------------------------------------------------------------------------


def _hay_palabra_de_solicitud(texto_normalizado: str, inicio: int, fin: int) -> bool:
    """Busca una palabra clave de solicitud a ≤ 30 caracteres del número.

    Se mide desde el final de la palabra si está antes del número, y desde el
    inicio si está después. Así ``código ... es 12345678`` no se pierde por un
    corte de ventana en la primera letra.
    """
    for palabra in PALABRAS_SOLICITUD_CODIGO:
        patron = re.compile(rf"\b{re.escape(palabra)}\b")
        for coincidencia in patron.finditer(texto_normalizado):
            if coincidencia.end() <= inicio:
                if inicio - coincidencia.end() <= 30:
                    return True
            elif coincidencia.start() >= fin:
                if coincidencia.start() - fin <= 30:
                    return True
            else:
                return True
    return False


def codigo_con_contexto(texto: str, inicio: int, fin: int) -> bool:
    """Aplica la regla de ``[CODIGO]`` de la memoria §7.1.

    Se enmascara solo si hay una palabra clave de solicitud a ≤ 30 caracteres
    y el número no está en un contexto de monto, porcentaje, fecha o folio.
    """
    fragmento = texto[inicio:fin]
    digitos = solo_digitos(fragmento)
    if not (4 <= len(digitos) <= 8):
        return False

    texto_normalizado = _normalizar_ventana(texto)

    # "código postal" es un uso legítimo y muy frecuente en México.
    if "codigo postal" in texto_normalizado[max(0, inicio - 30) : fin + 30]:
        return False

    if not _hay_palabra_de_solicitud(texto_normalizado, inicio, fin):
        return False

    # Montos: $ pegado, o moneda/porcentaje justo después.
    if "$" in texto[max(0, inicio - 3) : inicio]:
        return False
    antes_negativo = texto_normalizado[max(0, inicio - 20) : inicio]
    despues_negativo = texto_normalizado[fin : fin + 20]
    if PATRON_CONTEXTO_NO_CODIGO.search(antes_negativo):
        return False
    if PATRON_CONTEXTO_NO_CODIGO.search(despues_negativo):
        return False

    return True


def telefono_con_contexto(texto: str, inicio: int, fin: int) -> bool:
    """Descarta teléfonos que en realidad son folios, montos o porcentajes."""
    antes = _normalizar_ventana(texto[max(0, inicio - 15) : inicio])
    despues = _normalizar_ventana(texto[fin : fin + 15])

    if "$" in texto[max(0, inicio - 3) : inicio]:
        return False
    if PATRON_CONTEXTO_NO_TELEFONO.search(antes):
        return False
    if PATRON_CONTEXTO_NO_TELEFONO.search(despues):
        return False

    return True
