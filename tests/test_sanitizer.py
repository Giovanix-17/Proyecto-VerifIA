"""Pruebas del módulo de sanitización (Fase 3).

Cubren los casos límite obligatorios de la skill ``verifia-sanitizacion`` y la
comprobación de que ningún dato personal del conjunto anotado sobrevive.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verifia.sanitizer import RasgoEnlace, TextoSanitizado, sanitizar

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "pii_eval.jsonl"


def _marcadores(texto: str) -> str:
    return sanitizar(texto).texto


def test_contrato_de_salida() -> None:
    resultado = sanitizar("Mi teléfono es 55 1234 5678 y mi correo es ana@ejemplo.com")

    assert isinstance(resultado, TextoSanitizado)
    assert resultado.entidades == 2
    assert resultado.marcadores == {"[TELEFONO]": 1, "[CORREO]": 1}
    assert sum(resultado.marcadores.values()) == resultado.entidades
    assert isinstance(resultado.rasgos_enlace, list)


def test_texto_vacio_y_solo_espacios() -> None:
    assert sanitizar("").texto == ""
    assert sanitizar("   \n\t ").texto == "   \n\t "
    assert sanitizar("").entidades == 0


def test_solo_emojis() -> None:
    assert sanitizar("😀😀😀").texto == "😀😀😀"


def test_texto_de_10000_caracteres() -> None:
    texto = ("Mensaje de prueba con acentos: ñ á é í ó ú. " * 300)[:10000]
    resultado = sanitizar(texto)
    assert len(resultado.texto) > 0
    assert resultado.entidades == 0


def test_no_acepta_otros_tipos() -> None:
    with pytest.raises(TypeError):
        sanitizar(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Su código es 4821, no lo compartas.", "Su código es [CODIGO], no lo compartas."),
        ("Ingrese el OTP 736251 para continuar.", "Ingrese el OTP [CODIGO] para continuar."),
        ("Escribe la clave 7 3 6 2 5 1 en la app.", "Escribe la clave [CODIGO] en la app."),
        ("Tu contraseña temporal es 4412903.", "Tu contraseña temporal es [CODIGO]."),
        ("Su NIP es 4821.", "Su NIP es [CODIGO]."),
        ("Número de seguridad: 4821937", "Número de seguridad: [CODIGO]"),
        ("Para confirmar, dicta el código 45-31-22.", "Para confirmar, dicta el código [CODIGO]."),
    ],
)
def test_codigo_positivo(texto: str, esperado: str) -> None:
    assert _marcadores(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "El pedido 4821 llegó ayer.",
        "El código postal es 86000.",
        "Transfiera $5,000 hoy mismo.",
        "Transferencia de 5000 pesos.",
        "El descuento es del 15%.",
        "Folio 4821, guía 5512345678.",
        "Su CVV es 842.",
        "El código tiene 123456789 dígitos.",
    ],
)
def test_codigo_negativo(texto: str) -> None:
    assert "[CODIGO]" not in _marcadores(texto)


def test_tarjeta_valida_y_luhn_invalido() -> None:
    assert "[TARJETA]" in _marcadores("Su tarjeta 4111 1111 1111 1111 fue bloqueada.")
    assert "[TARJETA]" not in _marcadores("Su tarjeta 4111 1111 1111 1112 fue bloqueada.")


def test_clabe_valida_y_digito_de_control_invalido() -> None:
    assert "[CUENTA]" in _marcadores("Transfiera a la CLABE 002180001234567896.")
    assert "[CUENTA]" not in _marcadores("Transfiera a la CLABE 002180001234567897.")


def test_curp_y_rfc() -> None:
    texto = "CURP PEGJ850312HDFRRN07 y RFC PEGJ850312AB1."
    salida = _marcadores(texto)
    assert salida == "CURP [CURP] y RFC [RFC]."


def test_curp_con_entidad_invalida_no_se_enmascara() -> None:
    assert "[CURP]" not in _marcadores("CURP PEGJ850312HZZRRN07.")


@pytest.mark.parametrize(
    "texto",
    [
        "Marque al 55 1234 5678.",
        "Comuníquese al +52 55 1234 5678.",
        "WhatsApp 993-123-4567.",
        "Llame al +52 1 55 1234 5678.",
        "Marca al (993) 123 4567.",
        "Teléfono 5512345678.",
    ],
)
def test_telefonos_validos(texto: str) -> None:
    assert "[TELEFONO]" in _marcadores(texto)


def test_enlace_conserva_solo_dominio_y_borra_query() -> None:
    resultado = sanitizar("Entra a https://bit.ly/x7?d=5512345678 para verificar")
    assert resultado.texto == "Entra a [ENLACE:bit.ly] para verificar"
    assert "5512345678" not in resultado.texto
    assert resultado.rasgos_enlace[0].es_acortador is True
    assert resultado.rasgos_enlace[0].host == "bit.ly"


@pytest.mark.parametrize(
    ("texto", "host", "campo", "valor"),
    [
        ("Visita https://login.bbva.com.mx/acceso", "bbva.com.mx", "num_subdominios", 1),
        ("Visita www.bbva.com.mx", "bbva.com.mx", "num_subdominios", 0),
        ("Paga en http://192.168.10.25:8080/pago", "192.168.10.25", "ip_literal", True),
        ("Paga en http://192.168.10.25:8080/pago", "192.168.10.25", "tiene_puerto", True),
        (
            "Paga en https://pagos-seguros.xyz/verificar",
            "pagos-seguros.xyz",
            "tld_sospechoso",
            True,
        ),
        (
            "Paga en https://pagos-seguros.xyz/verificar",
            "pagos-seguros.xyz",
            "guiones_en_host",
            1,
        ),
    ],
)
def test_rasgos_de_enlace(texto: str, host: str, campo: str, valor: object) -> None:
    resultado = sanitizar(texto)
    assert resultado.rasgos_enlace
    rasgo: RasgoEnlace = resultado.rasgos_enlace[0]
    assert rasgo.host == host
    assert getattr(rasgo, campo) == valor


def test_correo_no_se_confunde_con_dominio() -> None:
    salida = _marcadores("Escribe a maria.lopez@ejemplo.com, no a www.ejemplo.com.")
    assert salida == "Escribe a [CORREO], no a [ENLACE:ejemplo.com]."


def test_nombre_no_traga_la_oracion() -> None:
    salida = _marcadores("Hola, soy Juan Pérez y mi teléfono es 55 1234 5678.")
    assert salida == "Hola, soy [NOMBRE] y mi teléfono es [TELEFONO]."


def test_nombre_con_particulas() -> None:
    assert _marcadores("María de la Cruz confirmó la dirección.") == (
        "[NOMBRE] confirmó la dirección."
    )


def test_nombre_con_tratamiento() -> None:
    salida = _marcadores("El Lic. Roberto Morales solicita que llames.")
    assert salida == "El Lic. [NOMBRE] solicita que llames."


def test_verbo_al_inicio_no_es_nombre() -> None:
    assert _marcadores("Rastrea tu paquete en paqueteria-express.net") == (
        "Rastrea tu paquete en [ENLACE:paqueteria-express.net]"
    )


@pytest.mark.parametrize(
    "texto",
    [
        "Hola, soy Juan Pérez y mi teléfono es 55 1234 5678.",
        "Entra a https://bit.ly/x7?d=5512345678",
        "CURP PEGJ850312HDFRRN07 y RFC PEGJ850312AB1",
        "Su código es 4821.",
        "El pedido 4821 llegó ayer.",
        "María de la Cruz, CLABE 002180001234567896.",
        "😀😀😀",
    ],
)
def test_idempotencia_y_estabilidad(texto: str) -> None:
    primera = sanitizar(texto)
    segunda = sanitizar(primera.texto)
    tercera = sanitizar(texto)

    assert segunda.texto == primera.texto
    assert tercera.texto == primera.texto
    # Los marcadores ya aplicados no se vuelven a enmascarar.
    for marcador in primera.marcadores:
        assert primera.texto.count(marcador) >= 1


def test_marcadores_previos_no_se_rompen() -> None:
    texto = "Su teléfono es [TELEFONO] y su código es [CODIGO]."
    resultado = sanitizar(texto)
    assert resultado.texto == texto
    assert resultado.entidades == 0


def test_todos_los_marcadores_del_catalogo() -> None:
    texto = (
        "Tel 55 1234 5678, correo ana@ejemplo.com, nombre Ana García, "
        "cuenta 002180001234567896, tarjeta 4111111111111111, código 4821, "
        "curp PEGJ850312HDFRRN07, rfc PEGJ850312AB1, enlace https://bit.ly/x7"
    )
    resultado = sanitizar(texto)
    for marcador in (
        "[TELEFONO]",
        "[CORREO]",
        "[NOMBRE]",
        "[CUENTA]",
        "[TARJETA]",
        "[CODIGO]",
        "[CURP]",
        "[RFC]",
        "[ENLACE:bit.ly]",
    ):
        assert marcador in resultado.texto
    assert resultado.entidades == 9


def test_conjunto_anotado_sin_supervivencias() -> None:
    """Sobre los 120 mensajes anotados, ningún valor esperado sobrevive."""
    with FIXTURE.open(encoding="utf-8") as archivo:
        casos = [json.loads(linea) for linea in archivo if linea.strip()]

    assert len(casos) >= 100

    fallos: list[str] = []
    for caso in casos:
        salida = sanitizar(caso["texto"]).texto
        for esperada in caso["esperado"]:
            if esperada["texto"] in salida:
                fallos.append(f"{caso['id']}: {esperada['entidad']} {esperada['texto']!r}")

    assert not fallos, "\n".join(fallos)


def test_corpus_sanitizado_sin_pii_detectable() -> None:
    """Escaneo independiente sobre los 500 mensajes del corpus.

    Se usa el detector simple de la Fase 2 (regex + Luhn + CLABE), que no
    comparte código con Presidio. Los códigos contextuales y los enlaces se
    excluyen porque no son PII por sí mismos y su revisión está en el conjunto
    anotado.
    """
    from corpus_common import detectar_pii

    corpus = Path(__file__).resolve().parents[1] / "data" / "annotated" / "corpus.jsonl"
    tipos_duros = {"correo", "curp", "rfc", "clabe", "tarjeta", "telefono"}
    fallos: list[str] = []

    with corpus.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            fila = json.loads(linea)
            salida = sanitizar(fila["texto"]).texto
            for hallazgo in detectar_pii(salida):
                if hallazgo["tipo"] in tipos_duros:
                    fallos.append(f"{fila['id']}: {hallazgo['tipo']} {hallazgo['valor']!r}")

    assert not fallos, "\n".join(fallos)


def test_metricas_del_conjunto_anotado() -> None:
    """Cobertura y precisión mínimas sobre el conjunto de ajuste."""
    import eval_sanitizer as evaluador

    casos = evaluador.evaluar()
    por_entidad, _ = evaluador.calcular_metricas(casos)

    esperadas = sum(m.esperadas for m in por_entidad.values())
    encontradas = sum(m.encontradas for m in por_entidad.values())
    producidas = sum(m.producidas for m in por_entidad.values())
    correctas = sum(m.correctas for m in por_entidad.values())

    assert encontradas / esperadas >= 0.95
    assert correctas / producidas >= 0.95
    assert not evaluador.sobrevivencias(casos)
