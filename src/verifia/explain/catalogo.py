"""Catálogo predefinido de recomendaciones y consecuencias (Fase 6).

Regla 6 de la memoria: las recomendaciones **no** las genera el LLM. Salen de
este catálogo cerrado, escrito a mano y revisado, para que el sistema no pueda
inventar teléfonos, enlaces, trámites ni nombres de instituciones.

Las únicas cifras permitidas son las de emergencia (911), declaradas como
constante con su fuente. El resto del catálogo no contiene URL, correos ni
números de teléfono.
"""

from __future__ import annotations

from verifia.schemas import TIPOLOGIAS

#: Número único de emergencias en México. Fuente: Secretariado Ejecutivo del
#: Sistema Nacional de Seguridad Pública (https://www.gob.mx/sesnsp). Se deja
#: como constante para que ninguna recomendación lo escriba como texto libre.
NUMERO_EMERGENCIAS = "911"

#: Dos recomendaciones que acompañan siempre al dictamen.
GENERALES: tuple[str, ...] = (
    "Conservar el mensaje como evidencia (captura de pantalla) antes de borrarlo.",
    "Ante cualquier duda, verificar por un canal oficial que usted consiga por su cuenta.",
)

#: Tres o cuatro acciones concretas por tipología.
POR_TIPOLOGIA: dict[str, tuple[str, ...]] = {
    "legitimo": (
        "Verificar por el canal oficial si algo le parece raro.",
        "No compartir datos si usted no inició el trámite.",
    ),
    "suplantacion_bancaria": (
        "No compartir códigos, NIP, token ni contraseñas.",
        "No entrar al enlace del mensaje.",
        "Llamar al número del reverso de su tarjeta.",
        "Revisar movimientos en la app oficial del banco.",
    ),
    "paqueteria_retenida": (
        "Rastrear el envío solo en el sitio oficial de la paquetería.",
        "No pagar ajustes ni liberaciones por un enlace del mensaje.",
        "Confirmar el pedido con quien lo envió.",
    ),
    "oferta_laboral_fraudulenta": (
        "No pagar anticipos, capacitación ni equipo.",
        "No entregar INE, CURP ni datos bancarios antes de un contrato.",
        "Verificar la empresa en su sitio oficial.",
    ),
    "extorsion": (
        "No responder ni negociar.",
        "No pagar.",
        "Conservar el mensaje como evidencia.",
        f"Denunciar al {NUMERO_EMERGENCIAS} o en la Fiscalía y buscar apoyo.",
    ),
}

#: Consecuencia de actuar conforme al mensaje, en una frase corta.
CONSECUENCIAS: dict[str, str] = {
    "legitimo": "Aun así, verifique por un canal oficial si algo le parece extraño.",
    "suplantacion_bancaria": (
        "Si comparte el código, otra persona podría autorizar cargos en su cuenta."
    ),
    "paqueteria_retenida": (
        "Si paga o da sus datos en ese enlace, el cobro o el robo de datos puede "
        "ocurrir de inmediato."
    ),
    "oferta_laboral_fraudulenta": (
        "Si adelanta dinero o entrega documentos, es muy probable que no recupere el pago."
    ),
    "extorsion": "Responder o pagar suele aumentar la presión y las exigencias.",
}

#: Nombre llano de cada tipología, sin tecnicismos.
TIPOLOGIA_LLANA: dict[str, str] = {
    "legitimo": "un mensaje legítimo",
    "suplantacion_bancaria": "una suplantación bancaria",
    "paqueteria_retenida": "un aviso de paquetería con un paquete retenido",
    "oferta_laboral_fraudulenta": "una oferta de trabajo fraudulenta",
    "extorsion": "una extorsión",
}

#: Aviso obligatorio en todo resultado (regla 13).
AVISO = (
    "Resultado orientativo: no sustituye su criterio ni la denuncia formal "
    "ante las autoridades."
)

#: Aviso visible cuando el Nivel 2 no pudo completar el análisis (regla 8).
ADVERTENCIA_PARCIAL = "análisis parcial: el modelo avanzado no estuvo disponible."


def recomendaciones(tipologia: str) -> list[str]:
    """Devuelve las recomendaciones generales + las de la tipología.

    Si llega una etiqueta desconocida se usa el catálogo de ``legitimo`` como
    red de seguridad; el esquema Pydantic ya impide etiquetas fuera del
    catálogo cerrado.
    """
    especificas = POR_TIPOLOGIA.get(tipologia, POR_TIPOLOGIA["legitimo"])
    vistas: set[str] = set()
    salida: list[str] = []
    for texto in (*GENERALES, *especificas):
        if texto not in vistas:
            vistas.add(texto)
            salida.append(texto)
    return salida


def tipologia_llana(tipologia: str) -> str:
    """Nombre comprensible de la tipología para el resumen."""
    return TIPOLOGIA_LLANA.get(tipologia, "un mensaje sospechoso")


def consecuencia(tipologia: str) -> str:
    """Consecuencia de actuar conforme al mensaje."""
    return CONSECUENCIAS.get(tipologia, CONSECUENCIAS["legitimo"])


# Comprobación de importación: el catálogo debe cubrir las cinco clases.
assert set(POR_TIPOLOGIA) == set(TIPOLOGIAS)
