"""Revisión humana del corpus: exportar a CSV e importar correcciones.

La etiqueta definitiva la asigna el autor. Este script no decide etiquetas:
solo prepara una hoja de revisión y convierte las decisiones del autor en
``data/annotated/correcciones.csv``, que ``corpus_build.py`` aplica antes de
particionar.

Flujo::

    python scripts/corpus_review.py --export
    # abrir data/annotated/revision.csv, revisar y guardar
    python scripts/corpus_review.py --import
    python scripts/corpus_build.py

El CSV se escribe con BOM (``utf-8-sig``) para que Excel respete los acentos.
Columnas:

- ``confirmar``: ``si`` si la etiqueta actual es correcta.
- ``tipologia_corregida``: una de las 5 clases, si hay que cambiarla.
- ``senales_corregidas``: señales separadas por ``;`` (opcional).
- ``nota``: motivo de la corrección (obligatorio si se corrige).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

from corpus_common import (
    ROOT,
    SENALES,
    TIPOLOGIAS,
    leer_jsonl,
)

CORPUS = ROOT / "data" / "annotated" / "corpus.jsonl"
REVISION = ROOT / "data" / "annotated" / "revision.csv"
CORRECCIONES = ROOT / "data" / "annotated" / "correcciones.csv"

CAMPOS = [
    "id",
    "origen",
    "tipologia",
    "texto",
    "senales_alerta",
    "revision_autor",
    "confirmar",
    "tipologia_corregida",
    "senales_corregidas",
    "nota",
]

VERDADEROS = {"si", "sí", "s", "x", "1", "true", "confirmado"}


def _correcciones_previas() -> dict[str, dict[str, str]]:
    if not CORRECCIONES.exists():
        return {}
    with CORRECCIONES.open("r", encoding="utf-8-sig", newline="") as fh:
        return {fila["id"]: fila for fila in csv.DictReader(fh) if fila.get("id")}


def exportar(destino: Path = REVISION) -> int:
    corpus = leer_jsonl(CORPUS)
    if not corpus:
        raise SystemExit(f"No existe {CORPUS}. Ejecuta antes scripts/corpus_build.py.")
    previas = _correcciones_previas()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
        escritor.writeheader()
        for fila in corpus:
            previa = previas.get(fila["id"], {})
            escritor.writerow(
                {
                    "id": fila["id"],
                    "origen": fila.get("origen", ""),
                    "tipologia": fila.get("tipologia", ""),
                    "texto": fila.get("texto", ""),
                    "senales_alerta": ";".join(fila.get("senales_alerta") or []),
                    "revision_autor": fila.get("revision_autor", "pendiente"),
                    "confirmar": "si" if fila.get("revision_autor") == "confirmado" else "",
                    "tipologia_corregida": previa.get("tipologia", ""),
                    "senales_corregidas": previa.get("senales_alerta", ""),
                    "nota": previa.get("nota", ""),
                }
            )
    print(f"Exportado {len(corpus)} mensajes a {destino}")
    print("Revisa el CSV y ejecuta: python scripts/corpus_review.py --import")
    return 0


def _limpiar_senales(valor: str) -> list[str]:
    return [s.strip() for s in valor.replace(",", ";").split(";") if s.strip() in SENALES]


def importar(origen: Path = REVISION) -> int:
    if not origen.exists():
        raise SystemExit(f"No existe {origen}. Ejecuta primero --export.")
    corpus = {f["id"]: f for f in leer_jsonl(CORPUS)}
    correcciones: list[dict[str, Any]] = []
    errores: list[str] = []

    with origen.open("r", encoding="utf-8-sig", newline="") as fh:
        for numero, fila in enumerate(csv.DictReader(fh), start=2):
            identificador = (fila.get("id") or "").strip()
            if identificador not in corpus:
                errores.append(f"línea {numero}: id desconocido {identificador!r}")
                continue
            confirmar = (fila.get("confirmar") or "").strip().lower() in VERDADEROS
            corregida = (fila.get("tipologia_corregida") or "").strip()
            senales_txt = (fila.get("senales_corregidas") or "").strip()
            nota = (fila.get("nota") or "").strip()
            if corregida and corregida not in TIPOLOGIAS:
                errores.append(f"línea {numero}: tipología inválida {corregida!r}")
                continue
            if not (confirmar or corregida or senales_txt):
                continue
            if corregida and not nota:
                errores.append(
                    f"línea {numero}: falta 'nota' para la corrección de {identificador}"
                )
                continue
            registro = {
                "id": identificador,
                "tipologia": corregida or corpus[identificador]["tipologia"],
                "senales_alerta": (
                    _limpiar_senales(senales_txt)
                    if senales_txt
                    else (corpus[identificador].get("senales_alerta") or [])
                ),
                "nota": nota,
            }
            correcciones.append(registro)

    if errores:
        print("Errores en el CSV (no se escribió nada):", file=sys.stderr)
        for e in errores[:50]:
            print(f"  - {e}", file=sys.stderr)
        return 2

    CORRECCIONES.parent.mkdir(parents=True, exist_ok=True)
    with CORRECCIONES.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(
            fh, fieldnames=["id", "tipologia", "senales_alerta", "nota"]
        )
        escritor.writeheader()
        for fila in correcciones:
            escritor.writerow(
                {
                    "id": fila["id"],
                    "tipologia": fila["tipologia"],
                    "senales_alerta": ";".join(fila["senales_alerta"]),
                    "nota": fila["nota"],
                }
            )
    print(f"Importadas {len(correcciones)} revisiones en {CORRECCIONES}")
    print("Ahora ejecuta: python scripts/corpus_build.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--export", action="store_true", help="genera la hoja de revisión")
    grupo.add_argument(
        "--import", dest="importar", action="store_true", help="lee la hoja revisada"
    )
    args = parser.parse_args(argv)
    if args.export:
        return exportar()
    return importar()


if __name__ == "__main__":
    raise SystemExit(main())
