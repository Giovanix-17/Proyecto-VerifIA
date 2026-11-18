"""Validadores de formato para los reconocedores de datos personales.

Las reglas de formato viven en :mod:`verifia.sanitizer.recognizers` como
``PatternRecognizer`` de Presidio; este módulo solo concentra la lógica de
validación (dígitos de control, fechas y estructura) que esos reconocedores
invocan desde ``validate_result``.

Fuente: VerifIA_memoria_proyecto.md §9 Fase 3 y skill ``verifia-sanitizacion``.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------


def solo_digitos(texto: str) -> str:
    """Devuelve únicamente los dígitos de ``texto``."""
    return re.sub(r"\D", "", texto)


def sin_acentos(texto: str) -> str:
    """Normaliza a minúsculas sin acentos, para comparar palabras clave."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def _fecha_valida(aammdd: str) -> bool:
    """Valida una fecha ``YYMMDD`` sin fijar el siglo.

    Para el 29 de febrero se usa el siglo 2000 cuando el año es 00-29 y el
    siglo 1900 en el resto, que es la convención habitual en documentos
    mexicanos. Solo importa descartar meses y días imposibles.
    """
    if not re.fullmatch(r"\d{6}", aammdd):
        return False

    anio_corto = int(aammdd[0:2])
    mes = int(aammdd[2:4])
    dia = int(aammdd[4:6])
    anio = 2000 + anio_corto if anio_corto <= 29 else 1900 + anio_corto

    try:
        dt.date(anio, mes, dia)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Tarjetas y cuentas CLABE
# ---------------------------------------------------------------------------


def pasa_luhn(digitos: str) -> bool:
    """Comprueba el dígito de control de una tarjeta (algoritmo de Luhn)."""
    if not digitos.isdigit() or not (13 <= len(digitos) <= 19):
        return False

    suma = 0
    for posicion, caracter in enumerate(reversed(digitos)):
        valor = int(caracter)
        if posicion % 2 == 1:
            valor *= 2
            if valor > 9:
                valor -= 9
        suma += valor

    return suma % 10 == 0


_PESOS_CLABE = (3, 7, 1)


def pasa_clabe(digitos: str) -> bool:
    """Comprueba el dígito de control de una CLABE de 18 dígitos.

    A los primeros 17 dígitos se les aplica el ciclo de pesos 3, 7, 1; el
    dígito 18 debe completar la decena.
    """
    if not digitos.isdigit() or len(digitos) != 18:
        return False

    suma = sum(
        int(digito) * _PESOS_CLABE[posicion % 3]
        for posicion, digito in enumerate(digitos[:17])
    )
    esperado = (10 - suma % 10) % 10
    return esperado == int(digitos[17])


# ---------------------------------------------------------------------------
# CURP y RFC
# ---------------------------------------------------------------------------

# Claves oficiales de entidad federativa usadas en la CURP.
ENTIDADES_CURP = frozenset(
    {
        "AS",  # Aguascalientes
        "BC",  # Baja California
        "BS",  # Baja California Sur
        "CC",  # Campeche
        "CL",  # Coahuila
        "CM",  # Colima
        "CS",  # Chiapas
        "CH",  # Chihuahua
        "DF",  # Ciudad de México
        "DG",  # Durango
        "GT",  # Guanajuato
        "GR",  # Guerrero
        "HG",  # Hidalgo
        "JC",  # Jalisco
        "MC",  # Estado de México
        "MN",  # Michoacán
        "MS",  # Morelos
        "NT",  # Nayarit
        "NL",  # Nuevo León
        "OC",  # Oaxaca
        "PL",  # Puebla
        "QT",  # Querétaro
        "QR",  # Quintana Roo
        "SP",  # San Luis Potosí
        "SL",  # Sinaloa
        "SR",  # Sonora
        "TC",  # Tabasco
        "TS",  # Tamaulipas
        "TL",  # Tlaxcala
        "VZ",  # Veracruz
        "YN",  # Yucatán
        "ZS",  # Zacatecas
        "NE",  # Nacido en el extranjero
    }
)

_CURP_RE = re.compile(
    r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d$"
)
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}(\d{6})[A-Z0-9]{3}$")


def es_curp(texto: str) -> bool:
    """Valida estructura, entidad federativa y fecha de nacimiento de una CURP.

    No se valida el dígito de control: la memoria (§9 Fase 3) solo exige
    estructura y clave de entidad válida.
    """
    candidato = texto.strip().upper()
    if not _CURP_RE.fullmatch(candidato):
        return False
    if candidato[11:13] not in ENTIDADES_CURP:
        return False
    return _fecha_valida(candidato[4:10])


def es_rfc(texto: str) -> bool:
    """Valida la estructura y la fecha de un RFC (persona física o moral)."""
    candidato = texto.strip().upper()
    coincidencia = _RFC_RE.fullmatch(candidato)
    if not coincidencia:
        return False
    return _fecha_valida(coincidencia.group(1))


# ---------------------------------------------------------------------------
# Teléfonos
# ---------------------------------------------------------------------------


def es_telefono_mx(texto: str) -> bool:
    """Valida un teléfono mexicano: 10 dígitos, con ``+52`` opcional.

    Se aceptan las variantes ``+52`` + 10 dígitos y ``+52 1`` + 10 dígitos
    (formato anterior para móviles).
    """
    digitos = solo_digitos(texto)

    if len(digitos) == 10:
        return True

    if len(digitos) in (12, 13) and digitos.startswith("52"):
        resto = digitos[2:]
        if len(resto) == 11 and resto.startswith("1"):
            resto = resto[1:]
        return len(resto) == 10

    return False
