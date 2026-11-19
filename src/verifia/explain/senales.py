"""Señales de alerta sobre el texto sanitizado (Fase 6).

Dos orígenes, ambos trazables:

* **Nivel 2** — el LLM ya devolvió ``frase`` + ``motivo`` y su contrato exige
  que la frase exista literalmente en el texto. Aquí solo se localiza el span
  para que la interfaz pueda resaltarla.
* **Nivel 1** — se usan los términos con mayor contribución del modelo para
  la clase predicha. El modelo final es Naive Bayes calibrado, así que la
  contribución se calcula con la diferencia de log-probabilidades entre la
  clase y el promedio de las demás ( equivalente a ``coef·x`` en un modelo
  lineal). Solo se usan las palabras del TF-IDF, no los n-gramas de carácter:
  son más legibles para el ciudadano.

Los marcadores tipificados (``[CODIGO]``, ``[ENLACE:...]``) se conservan: son
señal legítima, no ruido. Nunca se resalta texto que no exista en el mensaje.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from verifia.schemas import CategoriaSenal, Senal, SenalResaltada

MAX_SENALES = 5

#: Palabras funcionales que no explican nada al usuario. Los nombres de
#: características de scikit-learn ya vienen sin acentos y en minúsculas.
STOPWORDS: frozenset[str] = frozenset(
    """
    de la que el en y a los del se las por un para con no una su al lo como mas
    pero sus le ya o este si porque esta entre cuando muy sin sobre tambien me
    hasta hay donde quien desde todo nos durante todos uno les ni contra otros
    ese eso ante ellos e esto mi antes algunos unos yo otro otras otra tanto esa
    estos mucho quienes nada muchos cual poco ella estar estas algunas algo
    nosotros mis tu te ti tus ellas nosotras vosotros vosotras os mio mia mios
    mias tuyo tuya tuyos tuyas suyo suya suyos suyas nuestro nuestra nuestros
    nuestras vuestro vuestra vuestros vuestras esos esas estoy estas estamos
    estan este estes estemos esteis esten ser soy eres es somos sois son sea
    seas seamos seais sean sera seran seria serian fue fueron era eran sido
    tener tengo tienes tiene tenemos teneis tienen tenia tenian tuve tuvieron
    haber he has ha hemos habeis han habia habian hube hubo hacer hago haces
    hace hacemos haceis hacen hacia hicieron hizo puedo puedes puede podemos
    podeis pueden podria podrian debe deben deberia deberian voy vas va vamos
    vais van ir fui tan cada solo message mensaje mensajes hola gracias favor
    buenas tardes dias estimado estimada cliente senor senora sr sra atentamente
    saludos informacion numero telefono correo nombre
    """.split()
)

#: Palabras demasiado generales para ser una señal útil.
GENERICAS: frozenset[str] = frozenset(
    {
        "mensaje",
        "mensajes",
        "hola",
        "gracias",
        "favor",
        "buenas",
        "tardes",
        "dias",
        "estimado",
        "estimada",
        "cliente",
        "senor",
        "senora",
        "atentamente",
        "saludos",
        "informacion",
    }
)

#: Catálogo de categorías por palabras clave. El orden importa: la primera
#: categoría que coincide gana. Las palabras van sin acentos.
REGLAS_CATEGORIA: tuple[tuple[CategoriaSenal, tuple[str, ...]], ...] = (
    (
        "solicitud_codigo",
        (
            "codigo",
            "nip",
            "token",
            "otp",
            "pin",
            "contrasena",
            "cvv",
            "clave",
            "seguridad",
            "[codigo]",
        ),
    ),
    (
        "enlace_sospechoso",
        (
            "enlace",
            "link",
            "http",
            "www",
            "bit.ly",
            "clic",
            "haz clic",
            "dominio",
            "url",
            "[enlace:",
        ),
    ),
    (
        "amenaza",
        (
            "bloque",
            "cancel",
            "suspende",
            "demanda",
            "multa",
            "embargo",
            "legal",
            "policia",
            "fiscalia",
            "denuncia",
            "detencion",
            "arresto",
            "matar",
            "secuestro",
            "dano",
            "publicar",
            "fotos",
            "consecuencia",
            "ubica",
            "mandamos",
            "familia",
        ),
    ),
    (
        "pago_anticipado",
        (
            "pago",
            "paga",
            "pagar",
            "deposita",
            "deposito",
            "transferencia",
            "anticipo",
            "capacitacion",
            "ajuste",
            "liberacion",
            "derecho",
            "cobro",
            "monto",
            "pesos",
        ),
    ),
    (
        "premio_falso",
        (
            "premio",
            "ganador",
            "felicidades",
            "reembolso",
            "bono",
            "sorteo",
            "beneficio",
        ),
    ),
    (
        "oferta_laboral",
        (
            "trabajo",
            "trabajar",
            "empleo",
            "vacante",
            "sueldo",
            "diario",
            "experiencia",
            "casa",
            "whatsapp",
            "contrato",
            "puesto",
            "contratamos",
        ),
    ),
    (
        "solicitud_datos",
        (
            "datos",
            "cuenta",
            "tarjeta",
            "clabe",
            "curp",
            "rfc",
            "ine",
            "direccion",
            "domicilio",
            "nombre",
            "telefono",
            "correo",
            "comparte",
            "compartir",
        ),
    ),
    (
        "suplantacion",
        (
            "banco",
            "bbva",
            "banorte",
            "santander",
            "hsbc",
            "banamex",
            "citibanamex",
            "bancoppel",
            "sat",
            "paqueteria",
            "dhl",
            "fedex",
            "estafeta",
            "amazon",
            "mercado libre",
            "institucion",
            "autoridad",
            "gobierno",
            "secretaria",
            "hacienda",
            "imss",
            "infonavit",
        ),
    ),
    (
        "urgencia",
        (
            "urgent",
            "urgencia",
            "hoy",
            "ahora",
            "inmediato",
            "24",
            "horas",
            "ultimo",
            "aviso",
            "plazo",
            "vence",
            "rapido",
        ),
    ),
)

MOTIVOS: dict[CategoriaSenal, str] = {
    "urgencia": "mete prisa con un plazo muy corto",
    "amenaza": "advierte una consecuencia negativa si no responde",
    "suplantacion": "se atribuye la identidad de una institución o marca",
    "solicitud_datos": "menciona datos personales o bancarios que conviene proteger",
    "solicitud_codigo": "pide o menciona un código que conviene no compartir",
    "enlace_sospechoso": "incluye un enlace que conviene verificar antes de abrirlo",
    "pago_anticipado": "menciona un pago que conviene no adelantar",
    "premio_falso": "ofrece un premio o beneficio condicionado",
    "oferta_laboral": "ofrece un empleo con condiciones atractivas y poco realistas",
    "otro": "es un término asociado con mensajes de fraude",
}

#: Orden de relevancia para el resumen y la interfaz. Las señales más
#: específicas van primero; ``otro`` queda al final.
PRIORIDAD: dict[CategoriaSenal, int] = {
    "solicitud_codigo": 0,
    "amenaza": 1,
    "suplantacion": 2,
    "enlace_sospechoso": 3,
    "pago_anticipado": 4,
    "premio_falso": 5,
    "oferta_laboral": 6,
    "solicitud_datos": 7,
    "urgencia": 8,
    "otro": 9,
}

PATRON_MARCADOR = re.compile(
    r"\[(?:TELEFONO|CORREO|NOMBRE|CUENTA|TARJETA|CODIGO|CURP|RFC)\]"
    r"|\[ENLACE:[^\]]+\]"
)


# --------------------------------------------------------------------------- #
# Normalización y localización de spans
# --------------------------------------------------------------------------- #
def normalizar_simple(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar palabras clave."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _normalizar_para_busqueda(texto: str) -> tuple[str, list[int]]:
    """Normaliza y conserva el mapa de offsets hacia el texto original.

    Se colapsan los espacios consecutivos para que una frase del LLM con
    saltos de línea distintos siga siendo localizable.
    """
    piezas: list[str] = []
    mapa: list[int] = []
    espacio_previo = False
    for i, caracter in enumerate(texto):
        if caracter.isspace():
            if piezas and not espacio_previo:
                piezas.append(" ")
                mapa.append(i)
            espacio_previo = True
            continue
        espacio_previo = False
        for base in unicodedata.normalize("NFD", caracter):
            if unicodedata.combining(base):
                continue
            for letra in base.lower():
                piezas.append(letra)
                mapa.append(i)
    return "".join(piezas), mapa


def _limites(pajar: str, inicio: int, fin: int) -> bool:
    """Comprueba que la coincidencia no caiga dentro de una palabra."""
    antes = pajar[inicio - 1] if inicio > 0 else ""
    despues = pajar[fin] if fin < len(pajar) else ""
    return not (antes.isalnum() or despues.isalnum())


def _expandir_marcador(texto: str, inicio: int, fin: int) -> tuple[int, int]:
    """Si el span cae dentro de ``[...]``, devuelve el marcador completo."""
    izquierda = texto.rfind("[", 0, inicio + 1)
    if izquierda == -1:
        return inicio, fin
    derecha = texto.find("]", fin)
    if derecha == -1:
        return inicio, fin
    if "]" in texto[izquierda:inicio] or "[" in texto[fin:derecha]:
        return inicio, fin
    return izquierda, derecha + 1


def localizar_frase(texto: str, frase: str) -> tuple[int, int] | None:
    """Devuelve ``(inicio, fin)`` sobre el texto original, o ``None``.

    La búsqueda ignora mayúsculas, acentos y diferencias de espacios. Si la
    frase cae dentro de un marcador, se devuelve el marcador completo para no
    resaltar media etiqueta.
    """
    if not frase or not frase.strip():
        return None
    aguja, _ = _normalizar_para_busqueda(frase.strip())
    pajar, mapa = _normalizar_para_busqueda(texto)
    if not aguja or not pajar:
        return None
    posicion = pajar.find(aguja)
    while posicion != -1:
        fin_normalizado = posicion + len(aguja)
        if _limites(pajar, posicion, fin_normalizado):
            inicio = mapa[posicion]
            fin = mapa[fin_normalizado - 1] + 1
            return _expandir_marcador(texto, inicio, fin)
        posicion = pajar.find(aguja, posicion + 1)
    return None


# --------------------------------------------------------------------------- #
# Categorías
# --------------------------------------------------------------------------- #
def _contiene(texto_normalizado: str, palabra: str) -> bool:
    if len(palabra) <= 3 or palabra.isdigit():
        return re.search(rf"\b{re.escape(palabra)}\b", texto_normalizado) is not None
    return palabra in texto_normalizado


def categoria_de(texto: str) -> CategoriaSenal:
    """Traduce un término o motivo a una categoría comprensible."""
    normalizado = normalizar_simple(texto)
    for categoria, palabras in REGLAS_CATEGORIA:
        if any(_contiene(normalizado, palabra) for palabra in palabras):
            return categoria
    return "otro"


def motivo_categoria(categoria: CategoriaSenal) -> str:
    """Motivo breve y no técnico para una categoría."""
    return MOTIVOS.get(categoria, MOTIVOS["otro"])


def ordenar_por_relevancia(
    senales: Iterable[SenalResaltada],
) -> list[SenalResaltada]:
    """Ordena por categoría relevante y conserva el orden de llegada.

    Así el resumen destaca una solicitud de código o una amenaza antes que una
    mención genérica a datos personales, sin depender del orden en que el
    modelo produjo los términos.
    """
    return sorted(senales, key=lambda senal: PRIORIDAD.get(senal.categoria, 9))


# --------------------------------------------------------------------------- #
# Señales desde marcadores y términos
# --------------------------------------------------------------------------- #
def _senal_marcador(marcador: str, inicio: int, fin: int) -> SenalResaltada | None:
    if marcador.startswith("[ENLACE:"):
        return SenalResaltada(
            frase=marcador,
            motivo=motivo_categoria("enlace_sospechoso"),
            categoria="enlace_sospechoso",
            origen="nivel_1",
            inicio=inicio,
            fin=fin,
        )
    if marcador == "[CODIGO]":
        return SenalResaltada(
            frase=marcador,
            motivo=motivo_categoria("solicitud_codigo"),
            categoria="solicitud_codigo",
            origen="nivel_1",
            inicio=inicio,
            fin=fin,
        )
    if marcador in {"[CUENTA]", "[TARJETA]", "[CURP]", "[RFC]"}:
        return SenalResaltada(
            frase=marcador,
            motivo=motivo_categoria("solicitud_datos"),
            categoria="solicitud_datos",
            origen="nivel_1",
            inicio=inicio,
            fin=fin,
        )
    # [TELEFONO], [CORREO] y [NOMBRE] no son sospechosos por sí mismos.
    return None


def senales_desde_marcadores(texto: str) -> list[SenalResaltada]:
    """Convierte los marcadores tipificados en señales de alerta.

    No se resaltan teléfono, correo ni nombre: aparecer en una firma o en un
    aviso legítimo es normal. Sí se resaltan el código, los datos bancarios y
    los enlaces, que son las señales que el ciudadano necesita ver.
    """
    senales: list[SenalResaltada] = []
    for coincidencia in PATRON_MARCADOR.finditer(texto):
        senal = _senal_marcador(
            coincidencia.group(0), coincidencia.start(), coincidencia.end()
        )
        if senal is not None:
            senales.append(senal)
        if len(senales) >= MAX_SENALES:
            break
    return senales


def _agregar_senal(
    texto: str,
    termino: str,
    usados: list[tuple[int, int]],
    senales: list[SenalResaltada],
) -> None:
    if len(senales) >= MAX_SENALES:
        return
    span = localizar_frase(texto, termino)
    if span is None:
        return
    inicio, fin = span
    if any(not (fin <= a or inicio >= b) for a, b in usados):
        return
    frase = texto[inicio:fin]
    categoria = categoria_de(termino)
    if categoria == "otro":
        categoria = categoria_de(frase)
    if categoria == "otro":
        return
    senales.append(
        SenalResaltada(
            frase=frase,
            motivo=motivo_categoria(categoria),
            categoria=categoria,
            origen="nivel_1",
            inicio=inicio,
            fin=fin,
        )
    )
    usados.append((inicio, fin))


def senales_desde_terminos(
    texto: str, terminos: Iterable[str]
) -> list[SenalResaltada]:
    """Resalta términos del modelo que existan literalmente en el mensaje."""
    senales: list[SenalResaltada] = []
    usados: list[tuple[int, int]] = []
    for termino in terminos:
        _agregar_senal(texto, termino, usados, senales)
    return senales


def senales_nivel1(
    texto: str,
    modelo: Any | None,
    tipologia: str,
    puntuacion: int,
) -> list[SenalResaltada]:
    """Señales del filtro local, con marcadores y términos del modelo.

    En riesgo bajo no se muestran señales: el mensaje no tiene por qué
    inquietar al usuario. Si la tipología es legítima, solo se conservan los
    marcadores objetivos (código, datos, enlace), nunca términos del modelo
    que explicarían una clase de fraude que no se predijo.
    """
    if puntuacion <= 33:
        return []
    senales = senales_desde_marcadores(texto)
    usados = [
        (senal.inicio, senal.fin)
        for senal in senales
        if senal.inicio is not None and senal.fin is not None
    ]
    if tipologia != "legitimo" and modelo is not None:
        for termino in extraer_terminos(modelo, texto, tipologia):
            _agregar_senal(texto, termino, usados, senales)
            if len(senales) >= MAX_SENALES:
                break
    return ordenar_por_relevancia(senales)[:MAX_SENALES]


def senales_nivel2(texto: str, senales_llm: Sequence[Senal]) -> list[SenalResaltada]:
    """Localiza las señales ya verificadas que devolvió el Nivel 2.

    Se descarta la señal cuya frase no se pueda localizar: no se resalta nada
    inventado (skill ``verifia-explicabilidad``).
    """
    senales: list[SenalResaltada] = []
    usados: list[tuple[int, int]] = []
    for senal in senales_llm:
        if len(senales) >= MAX_SENALES:
            break
        span = localizar_frase(texto, senal.frase)
        if span is None:
            continue
        inicio, fin = span
        if any(not (fin <= a or inicio >= b) for a, b in usados):
            continue
        frase = texto[inicio:fin]
        categoria = categoria_de(f"{senal.motivo} {frase}")
        if categoria == "otro":
            categoria = categoria_de(frase)
        senales.append(
            SenalResaltada(
                frase=frase,
                motivo=senal.motivo,
                categoria=categoria,
                origen="nivel_2",
                inicio=inicio,
                fin=fin,
            )
        )
        usados.append((inicio, fin))
    return ordenar_por_relevancia(senales)[:MAX_SENALES]


# --------------------------------------------------------------------------- #
# Contribución de términos del Nivel 1
# --------------------------------------------------------------------------- #
def _estimadores_base(modelo: Any) -> list[Any]:
    """Devuelve los pipelines internos de un modelo (calibrado o directo)."""
    calibrados = getattr(modelo, "calibrated_classifiers_", None)
    if calibrados:
        return [
            calibrador.estimator
            for calibrador in calibrados
            if hasattr(calibrador, "estimator")
        ]
    if hasattr(modelo, "named_steps"):
        return [modelo]
    return []


def _bloques_caracteristicas(pipeline: Any) -> list[tuple[str, Any, int]]:
    """Describe los bloques del ``FeatureUnion`` en su orden de concatenación.

    El modelo incluye palabras, caracteres y rasgos estructurales; solo el
    primero es legible para el ciudadano. Los tamaños permiten recortar el
    vector de coeficientes sin depender de índices mágicos.
    """
    pasos = getattr(pipeline, "named_steps", {})
    caracteristicas = pasos.get("caracteristicas")
    if caracteristicas is None:
        return []
    bloques: list[tuple[str, Any, int]] = []
    for nombre, transformador in getattr(caracteristicas, "transformer_list", []):
        interno = getattr(transformador, "named_steps", {})
        if nombre in {"palabras", "caracteres"}:
            vectorizador = interno.get("tfidf")
        elif nombre == "estructurales":
            vectorizador = interno.get("dict")
        else:
            return []
        if vectorizador is None:
            return []
        try:
            tamano = len(vectorizador.get_feature_names_out())
        except AttributeError:
            return []
        bloques.append((nombre, vectorizador, tamano))
    return bloques


def _pesos_estimador(estimador: Any, clase: str, n_caracteristicas: int) -> np.ndarray | None:
    """Contribución de cada característica a favor de ``clase``.

    Para Naive Bayes: ``log P(x|clase) − promedio(log P(x|otras))``.
    Para modelos lineales: ``coef[clase] − promedio(coef[otras])``.
    """
    clases = [str(c) for c in getattr(estimador, "classes_", [])]
    if clase not in clases:
        return None
    indice = clases.index(clase)
    otras = [i for i in range(len(clases)) if i != indice]
    if not otras:
        return None

    if hasattr(estimador, "feature_log_prob_"):
        log_prob = np.asarray(estimador.feature_log_prob_, dtype=float)
        if log_prob.ndim != 2 or log_prob.shape[1] != n_caracteristicas:
            return None
        return log_prob[indice] - log_prob[otras].mean(axis=0)

    if hasattr(estimador, "coef_"):
        coeficientes = np.asarray(estimador.coef_, dtype=float)
        if coeficientes.ndim == 1:
            coeficientes = coeficientes.reshape(1, -1)
        if coeficientes.shape[1] != n_caracteristicas:
            return None
        if coeficientes.shape[0] == 1:
            if len(clases) == 2:
                return coeficientes[0] if indice == 1 else -coeficientes[0]
            return coeficientes[0]
        return coeficientes[indice] - coeficientes[otras].mean(axis=0)

    return None


def _termino_util(termino: str) -> bool:
    """Filtra n-gramas ruidosos o palabras funcionales.

    Solo se conservan unigramas: los bigramas del TF-IDF suelen arrastrar
    palabras funcionales ("su cuenta") y explican peor al ciudadano.
    """
    limpio = termino.strip().lower()
    if " " in limpio:
        return False
    if len(limpio) < 3 or not any(c.isalpha() for c in limpio):
        return False
    if limpio in STOPWORDS or limpio in GENERICAS:
        return False
    partes = re.findall(r"[a-z]+", normalizar_simple(limpio))
    if not partes:
        return False
    return not all(parte in STOPWORDS or parte in GENERICAS for parte in partes)


def extraer_terminos(
    modelo: Any,
    texto: str,
    clase: str,
    k: int = 8,
) -> list[str]:
    """Términos con mayor contribución del Nivel 1 para ``clase``.

    Es una explicación **aproximada y local**: indica qué palabras del propio
    mensaje empujan la predicción hacia esa clase. No es una relación causal
    ni una explicación SHAP. Si el modelo no expone coeficientes o
    log-probabilidades, devuelve una lista vacía y la explicación se apoya en
    los marcadores y en el resumen genérico.
    """
    puntajes: dict[str, float] = {}
    estimadores = _estimadores_base(modelo)
    if not estimadores:
        return []

    for pipeline in estimadores:
        bloques = _bloques_caracteristicas(pipeline)
        estimador = getattr(pipeline, "named_steps", {}).get("modelo")
        if not bloques or estimador is None:
            continue
        total = sum(tamano for _, _, tamano in bloques)
        pesos = _pesos_estimador(estimador, clase, total)
        if pesos is None:
            continue
        inicio = 0
        for nombre, vectorizador, tamano in bloques:
            pesos_bloque = pesos[inicio : inicio + tamano]
            inicio += tamano
            if nombre != "palabras":
                continue
            try:
                matriz = vectorizador.transform([texto])
                nombres = vectorizador.get_feature_names_out()
            except (ValueError, AttributeError):
                continue
            contribuciones = (
                np.asarray(matriz.toarray()[0], dtype=float) * pesos_bloque
            )
            for indice in np.flatnonzero(contribuciones > 0):
                termino = str(nombres[indice])
                puntajes[termino] = puntajes.get(termino, 0.0) + float(
                    contribuciones[indice]
                )

    candidatos = [
        (termino, puntaje)
        for termino, puntaje in puntajes.items()
        if _termino_util(termino)
    ]
    candidatos.sort(key=lambda par: (-par[1], par[0]))
    return [termino for termino, _ in candidatos[:k]]
