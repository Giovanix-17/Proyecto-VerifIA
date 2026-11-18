"""Evalúa el CER y WER del pipeline OCR (Fase 4).

Lee las capturas sintéticas de ``data/ocr_test`` y su transcripción de
referencia, ejecuta el pipeline con la caja de conversación de cada captura y
calcula CER/WER globales y desagregados por modo, resolución y app.

Uso::

    python scripts/eval_ocr.py
    python scripts/eval_ocr.py --report docs/reportes/ocr_cer_wer.md
    python scripts/eval_ocr.py --detalle
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import jiwer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from verifia.ocr import ErrorOCR, OpcionesOCR, disponibilidad, extraer_texto  # noqa: E402

MANIFIESTO = ROOT / "data" / "ocr_test" / "referencias.jsonl"
META_CER = 0.15
_ESPACIOS = re.compile(r"\s+")


@dataclass
class Caso:
    id: str
    modo: str
    resolucion: str
    app: str
    referencia: str
    hipotesis: str = ""
    error: str | None = None
    cer: float = 1.0
    wer: float = 1.0


@dataclass
class Grupo:
    nombre: str
    casos: list[Caso]

    @property
    def cer_macro(self) -> float:
        return statistics.fmean(caso.cer for caso in self.casos)

    @property
    def wer_macro(self) -> float:
        return statistics.fmean(caso.wer for caso in self.casos)

    @property
    def cer_micro(self) -> float:
        referencia = " ".join(caso.referencia for caso in self.casos)
        hipotesis = " ".join(caso.hipotesis for caso in self.casos)
        return jiwer.cer(referencia, hipotesis) if referencia else 0.0

    @property
    def exactos(self) -> int:
        return sum(1 for caso in self.casos if caso.cer == 0.0 and caso.error is None)

    @property
    def sobre_meta(self) -> int:
        return sum(1 for caso in self.casos if caso.cer > META_CER)


def _normalizar(texto: str) -> str:
    return _ESPACIOS.sub(" ", texto).strip()


def _percentil(valores: list[float], proporcion: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = round((len(ordenados) - 1) * proporcion)
    return ordenados[min(len(ordenados) - 1, max(0, indice))]


def evaluar(manifiesto: Path) -> list[Caso]:
    registros = [
        json.loads(linea)
        for linea in manifiesto.read_text(encoding="utf-8").splitlines()
        if linea.strip()
    ]
    base = manifiesto.parent
    casos: list[Caso] = []

    for registro in registros:
        caso = Caso(
            id=registro["id"],
            modo=registro["modo"],
            resolucion=registro["resolucion"],
            app=registro["app"],
            referencia=_normalizar(registro["texto"]),
        )
        try:
            resultado = extraer_texto(
                base / registro["archivo"],
                OpcionesOCR(recorte=tuple(registro["recorte"])),
            )
            caso.hipotesis = _normalizar(resultado.texto)
        except ErrorOCR as exc:
            caso.error = f"{type(exc).__name__}: {exc}"
            caso.hipotesis = ""

        if caso.referencia:
            caso.cer = jiwer.cer(caso.referencia, caso.hipotesis)
            caso.wer = jiwer.wer(caso.referencia, caso.hipotesis)
        casos.append(caso)

    return casos


def _agrupar(casos: list[Caso], campo: str) -> list[Grupo]:
    grupos: dict[str, list[Caso]] = defaultdict(list)
    for caso in casos:
        grupos[getattr(caso, campo)].append(caso)
    return [Grupo(nombre, miembros) for nombre, miembros in sorted(grupos.items())]


def _fila(nombre: str, grupo: Grupo) -> str:
    return (
        f"| {nombre} | {len(grupo.casos)} | {grupo.cer_macro:.1%} | "
        f"{grupo.cer_micro:.1%} | {grupo.wer_macro:.1%} | "
        f"{grupo.exactos}/{len(grupo.casos)} | {grupo.sobre_meta} |"
    )


def construir_reporte(casos: list[Caso], info: dict[str, str | bool]) -> str:
    total = Grupo("global", casos)
    lineas = [
        "# CER y WER del OCR (Fase 4)",
        "",
        "> Generado por `scripts/eval_ocr.py` sobre 60 capturas sintéticas de "
        "`data/ocr_test` con transcripción de referencia.",
        "",
        "## Configuración",
        "",
        "| Componente | Valor |",
        "|---|---|",
        f"| Tesseract | {info.get('version', 'desconocida')} |",
        f"| Binario | `{info.get('binario', '')}` |",
        "| Idioma | `spa` (`spa.traineddata`, tessdata_best) |",
        "| Segmentación | `--oem 3 --psm 6`, `preserve_interword_spaces=1` |",
        "| Preprocesamiento | gris → recorte → ampliación 2× si alto < 800 px → "
        "inversión en modo oscuro → denoise → normalización de fondo → Otsu |",
        "| Recorte | caja relativa por captura: excluye barra de estado, "
        "encabezado y campo de escritura |",
        "",
        "## Conjunto de evaluación",
        "",
        "- 60 capturas sintéticas, 2 mensajes cada una (120 mensajes en total).",
        "- 30 en modo claro y 30 en modo oscuro; 15 por cada resolución "
        "(720×1280, 1080×1920, 480×800 y 360×640).",
        "- 30 imitando WhatsApp y 30 imitando la app de SMS.",
        "- Solo mensajes de prueba; no se usaron datos personales reales.",
        "- La referencia es el texto original de cada burbuja; se normalizan "
        "los espacios para que los saltos de línea no cuenten como error.",
        "",
        "## Resultado global",
        "",
        f"- Capturas evaluadas: **{len(casos)}**",
        f"- Fallas del pipeline: **{sum(1 for caso in casos if caso.error)}**",
        f"- **CER macro: {total.cer_macro:.2%}** (meta de referencia ≤ {META_CER:.0%})",
        f"- **WER macro: {total.wer_macro:.2%}**",
        f"- CER micro (texto concatenado): **{total.cer_micro:.2%}**",
        f"- CER mediana: **{_percentil([caso.cer for caso in casos], 0.5):.2%}** · "
        f"p90: **{_percentil([caso.cer for caso in casos], 0.9):.2%}**",
        f"- Capturas con CER ≤ {META_CER:.0%}: "
        f"**{len(casos) - total.sobre_meta}/{len(casos)}**",
        "",
        "> **Lectura correcta:** las capturas son sintéticas y limpias (fuente "
        "digital, sin compresión de cámara ni fondos complejos). El CER real en "
        "capturas de teléfono será mayor; estas cifras miden el pipeline y "
        "sirven de línea base reproducible, no de garantía en campo.",
        "",
        "## Por modo",
        "",
        "| Modo | Capturas | CER macro | CER micro | WER macro | Exactas | CER > 15 % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lineas.extend(_fila(grupo.nombre, grupo) for grupo in _agrupar(casos, "modo"))

    lineas.extend(
        [
            "",
            "## Por resolución",
            "",
            "| Resolución | Capturas | CER macro | CER micro | WER macro | Exactas | "
            "CER > 15 % |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lineas.extend(_fila(grupo.nombre, grupo) for grupo in _agrupar(casos, "resolucion"))

    lineas.extend(
        [
            "",
            "## Por tipo de app",
            "",
            "| App | Capturas | CER macro | CER micro | WER macro | Exactas | CER > 15 % |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    lineas.extend(_fila(grupo.nombre, grupo) for grupo in _agrupar(casos, "app"))

    peores = sorted(casos, key=lambda caso: caso.cer, reverse=True)[:5]
    lineas.extend(
        [
            "",
            "## Peores capturas",
            "",
            "| Captura | Condición | CER | WER | Referencia → hipótesis |",
            "|---|---|---:|---:|---|",
        ]
    )
    for caso in peores:
        referencia = caso.referencia.replace("|", "/")[:70]
        hipotesis = caso.hipotesis.replace("|", "/")[:70]
        condicion = f"{caso.modo}, {caso.resolucion}, {caso.app}"
        lineas.append(
            f"| {caso.id} | {condicion} | {caso.cer:.1%} | {caso.wer:.1%} | "
            f"{referencia} → {hipotesis} |"
        )

    errores = [caso for caso in casos if caso.error]
    if errores:
        lineas.extend(["", "## Fallas del pipeline", ""])
        for caso in errores:
            lineas.append(f"- `{caso.id}`: {caso.error}")

    lineas.extend(
        [
            "",
            "## Decisiones y límites",
            "",
            "- Se probó binarización adaptativa; en modo oscuro generaba ruido en "
            "los bordes de las burbujas. La normalización de fondo + Otsu dio "
            "mejor CER y se usa como método principal; el adaptativo queda como "
            "respaldo si Otsu satura.",
            "- La corrección `Q`/`G` → `@` solo se aplica dentro de una estructura de "
            "correo, porque Tesseract con `spa` confunde la arroba. Sin ella, un "
            "correo podría llegar sin enmascarar a la clasificación.",
            "- Una captura con burbujas de polaridad mixta (texto claro sobre "
            "fondo oscuro dentro de una pantalla clara) no se resuelve con la "
            "inversión global; se documenta como caso residual.",
            "- El recorte de encabezado es configurable y se desactiva si el "
            "usuario necesita el texto completo. La interfaz siempre muestra el "
            "borrador para corrección antes del análisis.",
            "",
        ]
    )
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evalúa CER/WER del OCR de VerifIA.")
    parser.add_argument("--manifiesto", type=Path, default=MANIFIESTO)
    parser.add_argument("--report", type=Path, help="ruta del reporte Markdown")
    parser.add_argument("--detalle", action="store_true", help="muestra cada captura")
    argumentos = parser.parse_args(argv)

    if not argumentos.manifiesto.is_file():
        print(f"No existe el manifiesto: {argumentos.manifiesto}")
        print("Genera las capturas con: python scripts/generar_capturas_ocr.py")
        return 2

    info = disponibilidad()
    if not info.get("disponible"):
        print(f"OCR no disponible: {info.get('detalle')}")
        return 2

    casos = evaluar(argumentos.manifiesto)
    total = Grupo("global", casos)
    print(f"Capturas: {len(casos)}")
    print(f"CER macro: {total.cer_macro:.2%}  WER macro: {total.wer_macro:.2%}")
    print(f"CER micro: {total.cer_micro:.2%}")
    print(f"Exactas: {total.exactos}/{len(casos)}")

    if argumentos.detalle:
        for caso in casos:
            estado = caso.error or "ok"
            print(f"{caso.id}  CER {caso.cer:.1%}  WER {caso.wer:.1%}  {estado}")

    if argumentos.report:
        argumentos.report.parent.mkdir(parents=True, exist_ok=True)
        argumentos.report.write_text(
            construir_reporte(casos, info),
            encoding="utf-8",
            newline="\n",
        )
        print(f"\nReporte: {argumentos.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
