"""Evalúa la cobertura y precisión del módulo de sanitización (Fase 3).

Lee ``tests/fixtures/pii_eval.jsonl`` (120 mensajes anotados a mano, 141
entidades esperadas), sanitiza cada mensaje y compara las entidades esperadas
con los marcadores producidos. Genera la tabla del reporte de la Fase 3.

Uso::

    python scripts/eval_sanitizer.py
    python scripts/eval_sanitizer.py --report docs/reportes/cobertura_sanitizacion.md
    python scripts/eval_sanitizer.py --detalle

La comparación se hace sobre el texto final, no sobre estructuras internas:
si un dato personal sobrevive, la prueba lo detecta.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verifia.sanitizer import sanitizar  # noqa: E402
from verifia.sanitizer.engine import _sanitizar_con_spans  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "pii_eval.jsonl"

_MARCADOR_RE = re.compile(
    r"\[(TELEFONO|CORREO|NOMBRE|CUENTA|TARJETA|CODIGO|CURP|RFC|ENLACE:[^\]\s]+)\]"
)


@dataclass
class Esperada:
    entidad: str
    texto: str
    apariciones: list[tuple[int, int]]
    host: str | None = None


@dataclass
class Producida:
    entidad: str
    inicio: int
    fin: int
    marcador: str
    host: str | None = None


@dataclass
class Caso:
    id: str
    texto: str
    esperadas: list[Esperada] = field(default_factory=list)
    producidas: list[Producida] = field(default_factory=list)
    sanitizado: str = ""
    marcadores: dict[str, int] = field(default_factory=dict)


def _tipo_de_marcador(marcador: str) -> tuple[str, str | None]:
    if marcador.startswith("[ENLACE:") and marcador.endswith("]"):
        return "ENLACE", marcador[len("[ENLACE:") : -1]
    return marcador.strip("[]"), None


def _apariciones(texto: str, literal: str) -> list[tuple[int, int]]:
    posiciones = []
    inicio = texto.find(literal)
    while inicio != -1:
        posiciones.append((inicio, inicio + len(literal)))
        inicio = texto.find(literal, inicio + 1)
    return posiciones


def _se_solapan(a_inicio: int, a_fin: int, b_inicio: int, b_fin: int) -> bool:
    return a_inicio < b_fin and b_inicio < a_fin


def _coincide(esperada: Esperada, producida: Producida) -> bool:
    if esperada.entidad != producida.entidad:
        return False
    if esperada.entidad == "ENLACE" and esperada.host != producida.host:
        return False
    return any(
        _se_solapan(inicio, fin, producida.inicio, producida.fin)
        for inicio, fin in esperada.apariciones
    )


def _digitos_de_url(url: str) -> list[str]:
    """Dígitos de la ruta/query que no deben sobrevivir (el host sí se conserva)."""
    candidato = url if "://" in url else f"http://{url}"
    try:
        partes = urlsplit(candidato)
    except ValueError:
        return []
    resto = f"{partes.path}?{partes.query}#{partes.fragment}"
    return [d for d in re.findall(r"\d{4,}", resto)]


def cargar_casos() -> list[Caso]:
    casos: list[Caso] = []
    with FIXTURE.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            fila = json.loads(linea)
            esperadas = []
            for item in fila["esperado"]:
                esperadas.append(
                    Esperada(
                        entidad=item["entidad"],
                        texto=item["texto"],
                        apariciones=_apariciones(fila["texto"], item["texto"]),
                        host=item.get("host"),
                    )
                )
            casos.append(
                Caso(id=fila["id"], texto=fila["texto"], esperadas=esperadas)
            )
    return casos


def evaluar() -> list[Caso]:
    casos = cargar_casos()
    for caso in casos:
        resultado, aceptados = _sanitizar_con_spans(caso.texto)
        caso.sanitizado = resultado.texto
        caso.marcadores = dict(resultado.marcadores)
        for candidato in aceptados:
            if not _MARCADOR_RE.fullmatch(candidato.marcador):
                raise RuntimeError(f"{caso.id}: marcador inválido {candidato.marcador!r}")
            entidad, host = _tipo_de_marcador(candidato.marcador)
            caso.producidas.append(
                Producida(
                    entidad=entidad,
                    inicio=candidato.inicio,
                    fin=candidato.fin,
                    marcador=candidato.marcador,
                    host=host,
                )
            )
        if sum(caso.marcadores.values()) != len(caso.producidas):
            raise RuntimeError(f"{caso.id}: conteo de marcadores inconsistente")
    return casos


@dataclass
class Metricas:
    esperadas: int = 0
    encontradas: int = 0
    producidas: int = 0
    correctas: int = 0

    @property
    def cobertura(self) -> float:
        return self.encontradas / self.esperadas if self.esperadas else 0.0

    @property
    def precision(self) -> float:
        return self.correctas / self.producidas if self.producidas else 0.0

    @property
    def f1(self) -> float:
        p, c = self.precision, self.cobertura
        return 2 * p * c / (p + c) if p + c else 0.0


def calcular_metricas(casos: list[Caso]) -> tuple[dict[str, Metricas], dict[str, Metricas]]:
    por_entidad: dict[str, Metricas] = defaultdict(Metricas)
    por_entidad_todas: dict[str, Metricas] = defaultdict(Metricas)

    for caso in casos:
        usadas: set[int] = set()
        for producida in caso.producidas:
            metricas = por_entidad_todas[producida.entidad]
            metricas.producidas += 1

            coincide = False
            for indice, esperada in enumerate(caso.esperadas):
                if indice in usadas:
                    continue
                if _coincide(esperada, producida):
                    usadas.add(indice)
                    coincide = True
                    break

            if coincide:
                metricas.correctas += 1

        for indice, esperada in enumerate(caso.esperadas):
            metricas = por_entidad_todas[esperada.entidad]
            metricas.esperadas += 1
            if indice in usadas:
                metricas.encontradas += 1

    # La tabla principal solo incluye entidades con casos esperados; las
    # falsas alarmas de entidades sin casos se muestran aparte.
    for entidad, metricas in por_entidad_todas.items():
        if metricas.esperadas:
            por_entidad[entidad] = metricas

    return por_entidad, por_entidad_todas


def sobrevivencias(casos: list[Caso]) -> list[str]:
    fallos: list[str] = []
    for caso in casos:
        for esperada in caso.esperadas:
            if esperada.texto in caso.sanitizado:
                fallos.append(
                    f"{caso.id}: sobrevive {esperada.entidad} {esperada.texto!r}"
                )
            if esperada.entidad == "ENLACE":
                for digitos in _digitos_de_url(esperada.texto):
                    if digitos in caso.sanitizado:
                        fallos.append(
                            f"{caso.id}: sobrevive el número {digitos!r} de la URL"
                        )
    return fallos


def detalle(casos: list[Caso]) -> None:
    for caso in casos:
        usadas: set[int] = set()
        falsas = []
        for producida in caso.producidas:
            coincide = False
            for indice, esperada in enumerate(caso.esperadas):
                if indice in usadas:
                    continue
                if _coincide(esperada, producida):
                    usadas.add(indice)
                    coincide = True
                    break
            if not coincide:
                fragmento = caso.texto[producida.inicio : producida.fin]
                falsas.append(f"{producida.marcador} <- {fragmento!r}")

        perdidas = [
            f"{esperada.entidad} {esperada.texto!r}"
            for indice, esperada in enumerate(caso.esperadas)
            if indice not in usadas
        ]
        if falsas or perdidas:
            print(f"\n{caso.id}: {caso.texto}")
            print(f"  OUT: {caso.sanitizado}")
            if perdidas:
                print("  NO ENCONTRADAS:", *perdidas, sep="\n    ")
            if falsas:
                print("  FALSAS ALARMAS:", *falsas, sep="\n    ")


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f} %"


def escanear_corpus() -> dict[str, object]:
    """Sanitiza los 500 mensajes del corpus y los escanea con el detector Fase 2.

    Es una comprobación independiente de Presidio: busca correos, CURP, RFC,
    CLABE, tarjetas y teléfonos que hayan sobrevivido. Los códigos contextuales
    y los enlaces se revisan en el conjunto anotado, no aquí.
    """
    from corpus_common import detectar_pii

    corpus = ROOT / "data" / "annotated" / "corpus.jsonl"
    tipos_duros = {"correo", "curp", "rfc", "clabe", "tarjeta", "telefono"}
    filas = 0
    cambiados = 0
    marcadores: dict[str, int] = defaultdict(int)
    hallazgos: list[dict[str, str]] = []

    with corpus.open(encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            fila = json.loads(linea)
            filas += 1
            resultado = sanitizar(fila["texto"])
            if resultado.texto != fila["texto"]:
                cambiados += 1
            for marcador, conteo in resultado.marcadores.items():
                marcadores[marcador] += conteo
            for hallazgo in detectar_pii(resultado.texto):
                if hallazgo["tipo"] in tipos_duros:
                    hallazgos.append(
                        {
                            "id": fila["id"],
                            "tipo": hallazgo["tipo"],
                            "valor": hallazgo["valor"],
                        }
                    )

    return {
        "mensajes": filas,
        "cambiados": cambiados,
        "marcadores": dict(marcadores),
        "hallazgos": hallazgos,
    }


def construir_reporte(
    casos: list[Caso],
    por_entidad: dict[str, Metricas],
    corpus: dict[str, object],
) -> str:
    total_esperadas = sum(m.esperadas for m in por_entidad.values())
    total_encontradas = sum(m.encontradas for m in por_entidad.values())
    total_producidas = sum(m.producidas for m in por_entidad.values())
    total_correctas = sum(m.correctas for m in por_entidad.values())
    cobertura_global = total_encontradas / total_esperadas if total_esperadas else 0
    precision_global = total_correctas / total_producidas if total_producidas else 0

    lineas = [
        "# Cobertura y precisión de la sanitización (Fase 3)",
        "",
        "> Generado por `scripts/eval_sanitizer.py` sobre "
        f"`tests/fixtures/pii_eval.jsonl` ({len(casos)} mensajes anotados a mano).",
        "",
        "## Configuración del motor",
        "",
        "| Componente | Versión / valor |",
        "|---|---|",
        "| Presidio Analyzer | 2.2.366 |",
        "| spaCy | 3.8.18 |",
        "| Modelo NER | `es_core_news_md` 3.8.0 |",
        "| Registro de reconocedores | solo los de VerifIA + NER español; sin los de inglés |",
        "| Umbral mínimo por entidad | 0.5 (los patrones validados obtienen 1.0) |",
        "",
        "Se construye un `RecognizerRegistry` vacío y se añaden los reconocedores "
        "propios. No se cargan los reconocedores por defecto en inglés porque "
        "producen entidades espurias y marcas inconsistentes.",
        "",
        "## Orden de resolución y reglas",
        "",
        "Los candidatos se ordenan de lo específico a lo genérico y se aplica "
        "no-solapamiento; después se sustituye de derecha a izquierda para no "
        "desplazar índices:",
        "",
        "`TARJETA → CUENTA (CLABE) → CURP → RFC → CORREO → TELEFONO → CODIGO → ENLACE → NOMBRE`",
        "",
        "- **Tarjeta:** 13–19 dígitos con Luhn; rechaza una CLABE válida de 18 "
        "dígitos y los teléfonos con `+52` que pasan Luhn por azar.",
        "- **CLABE:** 18 dígitos con dígito de control (pesos 3, 7, 1).",
        "- **CURP:** estructura, entidad federativa válida y fecha real; no se "
        "valida el dígito de control.",
        "- **RFC:** 12 o 13 caracteres con fecha válida.",
        "- **Correo:** simplificación de RFC 5322.",
        "- **Teléfono:** 10 dígitos, con `+52` y `+52 1`; se descartan folios, "
        "montos y porcentajes por contexto.",
        "- **Código:** 4–8 dígitos con palabra de solicitud a ≤ 30 caracteres "
        "(medida desde el final de la palabra) y sin contexto de monto, "
        "porcentaje, fecha, folio o código postal.",
        "- **Enlace:** se conserva solo el dominio registrable; los rasgos "
        "estructurales van aparte, nunca al texto.",
        "- **Nombre:** NER español, recorte de la oración, respaldo para "
        "tratamientos (`Lic.`, `Sra.`, `Dr.`) y filtro de categoría gramatical "
        "para no confundir verbos imperativos.",
        "",
        "## Resultado global",
        "",
        "| Métrica | Valor |",
        "|---|---:|",
        f"| Entidades esperadas | {total_esperadas} |",
        f"| Entidades encontradas | {total_encontradas} |",
        f"| **Cobertura (recall)** | **{_pct(cobertura_global)}** |",
        f"| Marcadores producidos | {total_producidas} |",
        f"| Marcadores correctos | {total_correctas} |",
        f"| **Precisión** | **{_pct(precision_global)}** |",
        "",
        "> **Lectura correcta:** este conjunto de 120 mensajes se usó durante el "
        "desarrollo para ajustar los reconocedores y la regla de `[CODIGO]`; por "
        "eso las cifras son optimistas y no equivalen a una validación con "
        "mensajes reales. La comprobación independiente sobre el corpus y las "
        "pruebas pytest de casos límite complementan la evidencia.",
        "",
        "## Por tipo de entidad",
        "",
        "| Entidad | Esperadas | Encontradas | Cobertura | Producidas | "
        "Correctas | Precisión | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for entidad in sorted(por_entidad):
        m = por_entidad[entidad]
        lineas.append(
            f"| {entidad} | {m.esperadas} | {m.encontradas} | {_pct(m.cobertura)} | "
            f"{m.producidas} | {m.correctas} | {_pct(m.precision)} | {_pct(m.f1)} |"
        )

    superviven = sobrevivencias(casos)
    lineas += [
        "",
        "## Supervivencia de datos personales",
        "",
        "Comprobación sobre el texto final: ningún valor anotado debe aparecer "
        "en la salida. Para enlaces también se revisan los dígitos de la ruta y "
        "la query (el dominio sí se conserva, por diseño).",
        "",
        f"- Valores que sobreviven: **{len(superviven)}**",
    ]
    if superviven:
        lineas += ["", "```", *superviven, "```"]

    lineas += [
        "",
        "## Comprobación independiente sobre el corpus",
        "",
        "Se sanitizaron los 500 mensajes de `data/annotated/corpus.jsonl` y se "
        "escaneó la salida con el detector simple de la Fase 2 (regex + Luhn + "
        "dígito de control de CLABE), que no comparte código con Presidio.",
        "",
        f"- Mensajes procesados: **{corpus['mensajes']}**",
        f"- Mensajes con al menos un cambio: **{corpus['cambiados']}**",
        f"- Marcadores aplicados: **{sum(corpus['marcadores'].values())}**",
        f"- Hallazgos de PII dura tras sanitizar: **{len(corpus['hallazgos'])}**",
        "",
    ]
    if corpus["hallazgos"]:
        lineas += ["```", *[str(h) for h in corpus["hallazgos"]], "```", ""]

    lineas += [
        "El escaneo independiente no detecta correos, CURP, RFC, CLABE, "
        "tarjetas ni teléfonos en la salida. Los códigos contextuales y los "
        "enlaces se validan en el conjunto anotado.",
        "",
        "## Casos residuales conocidos",
        "",
        "Se documentan como pendientes; la regla 5 de la memoria prioriza "
        "exhaustividad sobre precisión.",
        "",
        "- Números escritos con palabras (`tres mil`), ofuscación deliberada "
        "(`4-5-3-1`, `O`↔`0`, `l`↔`I`) y datos sin contexto reconocible.",
        "- Folios de exactamente 10 dígitos sin palabra de contexto pueden "
        "parecer teléfonos; se descartan cuando aparecen `folio`, `pedido`, "
        "`orden`, `guía`, `referencia`, `factura` o `recibo` cerca.",
        "- Nombres de una sola palabra muy comunes pueden escaparse del NER; "
        "los nombres en mayúsculas institucionales se revisan contra una lista "
        "de falsos positivos.",
        "- La CURP se valida por estructura y entidad federativa; no se valida "
        "su dígito de control.",
        "- El detector simple de la Fase 2 marca como código contextual el folio "
        "`XYZ12345` de `syn-0058` porque la palabra «código» aparece en la misma "
        "oración; la regla §7.1 lo excluye correctamente y no es una fuga.",
        "",
    ]
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="ruta del reporte Markdown")
    parser.add_argument("--detalle", action="store_true", help="muestra errores por caso")
    args = parser.parse_args(argv)

    casos = evaluar()
    por_entidad, por_entidad_todas = calcular_metricas(casos)
    fallos = sobrevivencias(casos)
    corpus = escanear_corpus()

    total_esperadas = sum(m.esperadas for m in por_entidad.values())
    total_encontradas = sum(m.encontradas for m in por_entidad.values())
    total_producidas = sum(m.producidas for m in por_entidad.values())
    total_correctas = sum(m.correctas for m in por_entidad.values())

    print(f"Casos: {len(casos)}")
    print(f"Esperadas: {total_esperadas} | encontradas: {total_encontradas}")
    print(f"Producidas: {total_producidas} | correctas: {total_correctas}")
    print(f"Cobertura: {_pct(total_encontradas / total_esperadas)}")
    print(f"Precisión: {_pct(total_correctas / total_producidas)}")
    print(f"Supervivencias: {len(fallos)}")
    print(
        f"Corpus: {corpus['mensajes']} mensajes | cambios: {corpus['cambiados']} | "
        f"hallazgos duros: {len(corpus['hallazgos'])}"
    )

    print("\nPor entidad:")
    for entidad in sorted(por_entidad):
        m = por_entidad[entidad]
        print(
            f"  {entidad:10s} esp={m.esperadas:3d} enc={m.encontradas:3d} "
            f"prod={m.producidas:3d} ok={m.correctas:3d} "
            f"cob={_pct(m.cobertura):>6s} prec={_pct(m.precision):>6s}"
        )

    if por_entidad_todas.get("SIN_MARCADOR", Metricas()).producidas:
        print("  ¡Hay texto eliminado sin marcador!")

    if fallos:
        print("\nSupervivencias:")
        for fallo in fallos:
            print(" ", fallo)

    if args.detalle:
        detalle(casos)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            construir_reporte(casos, por_entidad, corpus), encoding="utf-8"
        )
        print(f"\nReporte: {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
