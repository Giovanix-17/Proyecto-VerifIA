"""Detección de enlaces y cálculo de sus rasgos estructurales.

De los enlaces se conserva **solo el dominio registrable** (regla 4 de la
memoria). La ruta, los parámetros, el fragmento y las credenciales desaparecen;
las características del enlace se devuelven aparte para el Nivel 1.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import tldextract

from verifia.sanitizer.models import RasgoEnlace

# Extractores de TLD sin acceso a red: usa la instantánea incluida en el paquete.
_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

# Dominios de acortadores usados con frecuencia en smishing.
ACORTADORES = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "goo.gl",
        "t.co",
        "ow.ly",
        "is.gd",
        "cutt.ly",
        "rebrand.ly",
        "shorturl.at",
        "bit.do",
        "tiny.cc",
        "lnkd.in",
        "rb.gy",
        "s.id",
        "cutt.us",
        "adf.ly",
        "bl.ink",
        "t.ly",
        "shorturl.gg",
        "trib.al",
        "buff.ly",
        "deck.ly",
    }
)

# TLD o sufijos que se consideran habituales. El resto se marca como dudoso.
TLD_COMUNES = frozenset(
    {
        "com",
        "mx",
        "org",
        "net",
        "gob",
        "edu",
        "info",
        "io",
        "app",
        "dev",
        "me",
        "tv",
        "co",
        "es",
        "us",
        "bz",
        "com.mx",
        "org.mx",
        "gob.mx",
        "edu.mx",
        "net.mx",
        "mil.mx",
    }
)

# Correo: se usa para evitar que la rama de "dominio suelto" recorte un correo.
_CORREO_RE = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z]{2,24})+"
)

_URL_RE = re.compile(
    r"""
    (?:
        (?:https?://|ftp://|www\.)[^\s<>"'`]+
      |
        \b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}
        (?:[/?#][^\s<>"'`]*)?
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class EnlaceDetectado:
    """Enlace localizado en el texto, con su reemplazo y sus rasgos."""

    inicio: int
    fin: int
    marcador: str
    rasgos: RasgoEnlace


def spans_correo(texto: str) -> list[tuple[int, int]]:
    """Devuelve los rangos ocupados por correos electrónicos."""
    return [(m.start(), m.end()) for m in _CORREO_RE.finditer(texto)]


def _limpiar_url(bruto: str) -> str:
    """Quita puntuación final que pertenece a la oración, no a la URL."""
    limpio = bruto.strip()
    while limpio and limpio[-1] in ".,;:!?»\"'":
        limpio = limpio[:-1]
    for abre, cierra in (("(", ")"), ("[", "]"), ("{", "}")):
        while limpio.endswith(cierra) and limpio.count(cierra) > limpio.count(abre):
            limpio = limpio[:-1]
    return limpio


def _separar_host(url: str) -> tuple[str, int | None] | None:
    """Extrae el host (sin credenciales ni puerto) y el puerto si existe."""
    candidato = url.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", candidato, re.IGNORECASE):
        candidato = f"http://{candidato}"
    try:
        partes = urlsplit(candidato)
        host = (partes.hostname or "").strip(".").lower()
        puerto = partes.port
    except ValueError:
        return None
    if not host:
        return None
    return host, puerto


def _es_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def rasgos_de_enlace(url: str) -> RasgoEnlace | None:
    """Calcula el marcador y los rasgos de un enlace, sin conservar la URL."""
    separado = _separar_host(url)
    if separado is None:
        return None
    host, puerto = separado

    es_ip = _es_ip(host)
    if es_ip:
        registrado = host
        subdominios = 0
        sufijo = ""
    else:
        extraido = _EXTRACTOR(host)
        registrado = getattr(extraido, "top_domain_under_public_suffix", "") or host
        subdominios = len([p for p in extraido.subdomain.split(".") if p and p != "www"])
        sufijo = extraido.suffix

    rasgos = RasgoEnlace(
        host=registrado,
        es_acortador=registrado in ACORTADORES,
        ip_literal=es_ip,
        num_subdominios=subdominios,
        tld_sospechoso=bool(sufijo) and sufijo.lower() not in TLD_COMUNES,
        guiones_en_host=host.count("-"),
        longitud_host=len(host),
        tiene_puerto=puerto is not None,
    )
    return rasgos


def extraer_enlaces(
    texto: str, spans_excluidos: list[tuple[int, int]] | None = None
) -> list[EnlaceDetectado]:
    """Localiza enlaces y descarta los que se solapan con ``spans_excluidos``.

    ``spans_excluidos`` sirve para que un correo electrónico no se interprete
    como un dominio suelto.
    """
    excluidos = spans_excluidos or []
    enlaces: list[EnlaceDetectado] = []

    for coincidencia in _URL_RE.finditer(texto):
        url = _limpiar_url(coincidencia.group(0))
        if not url:
            continue

        inicio = coincidencia.start()
        fin = inicio + len(url)

        if any(inicio < f and i < fin for i, f in excluidos):
            continue

        rasgos = rasgos_de_enlace(url)
        if rasgos is None:
            continue

        enlaces.append(
            EnlaceDetectado(
                inicio=inicio,
                fin=fin,
                marcador=f"[ENLACE:{rasgos.host}]",
                rasgos=rasgos,
            )
        )

    return enlaces
