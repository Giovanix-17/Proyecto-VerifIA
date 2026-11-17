"""Construcción del corpus anotado y de la partición 70/15/15.

Fase 2.3 de ``VerifIA_memoria_proyecto.md``. Orden de operaciones (importante):

1. Leer fuentes (``data/raw/*.jsonl`` + ``data/synthetic/generated.jsonl``).
2. Normalizar y validar el esquema de anotación.
3. Deduplicar exactos y casi duplicados (TF-IDF char 4-gramas, coseno ≥ 0.90)
   **antes** de particionar, para no inflar métricas por fuga entre splits.
4. Auditar PII real; se descarta cualquier mensaje con datos personales.
5. Completar cada clase hasta la cuota con sintéticos únicos (los sintéticos
   solo pueden ir a train, regla 9).
6. Partición estratificada 70/15/15 por tipología; val/test sin ``sintetico_llm``.
7. Escribir ``data/annotated/corpus.jsonl``, ``data/splits/*.jsonl`` y el
   manifiesto reproducible, además del reporte de cobertura.

Uso::

    docker run --rm -v "${PWD}:/app" -w /app verifia:0.1.0 \
        python scripts/corpus_build.py

El script falla con un mensaje claro si no hay suficientes ejemplos únicos:
en ese caso hay que generar más sintéticos con ``corpus_generate.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from corpus_common import (
    ROOT,
    TIPOLOGIAS,
    ahora_iso,
    contar_por,
    detectar_pii,
    escribir_jsonl,
    leer_jsonl,
    normalizar_texto,
    resumen,
    sha256_archivo,
    validar_mensaje,
)

RAW = ROOT / "data" / "raw"
SYNTHETIC = ROOT / "data" / "synthetic" / "generated.jsonl"
ANNOTATED = ROOT / "data" / "annotated" / "corpus.jsonl"
SPLITS = ROOT / "data" / "splits"
REPORTE = ROOT / "docs" / "reportes" / "cobertura_corpus.md"
CORRECCIONES = ROOT / "data" / "annotated" / "correcciones.csv"

PII_BLOQUEANTE = {"correo", "telefono", "clabe", "tarjeta", "curp", "rfc"}

# Decisiones de revisión que retiran un registro de las fuentes. Se declaran en
# código (y no borrando la línea de ``generated.jsonl``) para que la exclusión
# quede versionada y el build sea reproducible.
EXCLUIDOS_REVISION = {
    "syn-0147": (
        "etiqueta débil: oferta sin señales verificables; "
        "sustituido por syn-0216"
    ),
}

# Prioridad de conservación en el deduplicado: primero lo escrito a mano y las
# plantillas; al final lo sintético (es el material más fácil de regenerar).
PRIORIDAD = {"manual": 0, "plantilla_legitima": 1, "publico": 2, "sintetico_llm": 3}


def aplicar_correcciones(filas: list[dict[str, Any]]) -> int:
    """Aplica ``correcciones.csv`` (decisiones del autor) a los registros.

    Las correcciones se aplican antes de deduplicar y particionar para que la
    etiqueta definitiva sea la que se estratifica. Si un id ya no existe, se
    ignora y se informa: puede pasar tras regenerar el corpus.
    """
    if not CORRECCIONES.exists():
        return 0
    por_id = {f["id"]: f for f in filas}
    aplicadas = 0
    desconocidas: list[str] = []
    with CORRECCIONES.open("r", encoding="utf-8-sig", newline="") as fh:
        for fila in csv.DictReader(fh):
            identificador = (fila.get("id") or "").strip()
            registro = por_id.get(identificador)
            if registro is None:
                desconocidas.append(identificador)
                continue
            tipologia = (fila.get("tipologia") or "").strip()
            if tipologia in TIPOLOGIAS:
                registro["tipologia"] = tipologia
            senales = (fila.get("senales_alerta") or "").strip()
            if senales:
                registro["senales_alerta"] = [
                    s.strip() for s in senales.split(";") if s.strip()
                ]
            registro["revision_autor"] = "confirmado"
            nota = (fila.get("nota") or "").strip()
            if nota:
                registro["nota_revision"] = nota
            aplicadas += 1
    if desconocidas:
        print(
            f"Aviso: {len(desconocidas)} correcciones apuntan a ids que ya no existen "
            f"(p. ej. {desconocidas[:3]}).",
            file=sys.stderr,
        )
    return aplicadas


def cargar_fuentes() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Devuelve (registros válidos, incidencias)."""
    filas: list[dict[str, Any]] = []
    incidencias: list[dict[str, Any]] = []

    for ruta in sorted(RAW.glob("*.jsonl")):
        for fila in leer_jsonl(ruta):
            fila.setdefault("fuente_archivo", ruta.name)
            filas.append(fila)
    for fila in leer_jsonl(SYNTHETIC):
        fila.setdefault("fuente_archivo", "synthetic/generated.jsonl")
        filas.append(fila)

    aplicadas = aplicar_correcciones(filas)
    if aplicadas:
        print(f"Correcciones de revisión aplicadas: {aplicadas}")

    # Exclusiones manuales: se aplican después de las correcciones para que el
    # registro siga existiendo en las fuentes, pero no entre al corpus.
    restantes: list[dict[str, Any]] = []
    for fila in filas:
        detalle = EXCLUIDOS_REVISION.get(str(fila.get("id")))
        if detalle:
            incidencias.append(
                {
                    "id": fila.get("id"),
                    "motivo": "excluido_revision",
                    "detalle": detalle,
                }
            )
            continue
        restantes.append(fila)
    filas = restantes

    validas: list[dict[str, Any]] = []
    for fila in filas:
        texto = normalizar_texto(str(fila.get("texto", "")))
        fila["texto"] = texto
        errores = validar_mensaje(fila)
        if errores:
            incidencias.append({"id": fila.get("id"), "motivo": errores})
            continue
        validas.append(fila)

    # La tipología definitiva es la que declare el registro; en los sintéticos
    # se conserva aparte el borrador del LLM como evidencia.
    for fila in validas:
        if fila.get("origen") == "sintetico_llm":
            fila.setdefault("tipologia_borrador", fila.get("tipologia"))
        fila.setdefault("revision_autor", "pendiente")
    return validas, incidencias


def deduplicar(filas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deduplicado exacto + casi duplicados globales (coseno ≥ 0.90).

    Se conserva el primero según ``PRIORIDAD`` y el orden de lectura. Devuelve
    (conservados, pares_descartados) para poder auditar el proceso.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    ordenadas = sorted(
        enumerate(filas),
        key=lambda par: (PRIORIDAD.get(par[1].get("origen", ""), 9), par[0]),
    )

    vistos_exactos: dict[str, dict[str, Any]] = {}
    unicas: list[dict[str, Any]] = []
    descartes: list[dict[str, Any]] = []

    for _, fila in ordenadas:
        clave = fila["texto"].casefold()
        if clave in vistos_exactos:
            descartes.append(
                {
                    "id_descartado": fila.get("id"),
                    "id_conservado": vistos_exactos[clave].get("id"),
                    "motivo": "duplicado_exacto",
                    "similitud": 1.0,
                }
            )
            continue
        vistos_exactos[clave] = fila
        unicas.append(fila)

    if len(unicas) > 1:
        textos = [f["texto"] for f in unicas]
        vectorizador = TfidfVectorizer(analyzer="char_wb", ngram_range=(4, 4), lowercase=True)
        matriz = vectorizador.fit_transform(textos)
        similitudes = cosine_similarity(matriz)

        eliminados: set[int] = set()
        for i in range(len(unicas)):
            if i in eliminados:
                continue
            for j in range(i + 1, len(unicas)):
                if j in eliminados:
                    continue
                if similitudes[i, j] >= 0.90:
                    eliminados.add(j)
                    descartes.append(
                        {
                            "id_descartado": unicas[j].get("id"),
                            "id_conservado": unicas[i].get("id"),
                            "motivo": "casi_duplicado",
                            "similitud": round(float(similitudes[i, j]), 4),
                        }
                    )
        conservadas = [f for i, f in enumerate(unicas) if i not in eliminados]
    else:
        conservadas = unicas

    # Se devuelve en el orden original de lectura para que los ids sean estables.
    posicion = {id(f): i for i, f in enumerate(filas)}
    conservadas.sort(key=lambda f: posicion[id(f)])
    return conservadas, descartes


def auditar_pii(filas: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separa los mensajes con PII bloqueante de los que solo tienen enlaces."""
    limpias: list[dict[str, Any]] = []
    incidencias: list[dict[str, Any]] = []
    for fila in filas:
        hallazgos = detectar_pii(fila["texto"])
        bloqueantes = [h for h in hallazgos if h["tipo"] in PII_BLOQUEANTE]
        enlaces = [h for h in hallazgos if h["tipo"] == "enlace"]
        if enlaces:
            fila["tiene_enlace"] = True
            fila["dominios_mencionados"] = sorted(
                {
                    h["valor"].replace("https://", "").replace("http://", "").split("/")[0].lower()
                    for h in enlaces
                }
            )
        if bloqueantes:
            # Nunca se guarda el valor encontrado (regla 2), solo el tipo.
            incidencias.append(
                {
                    "id": fila.get("id"),
                    "motivo": "pii_bloqueante",
                    "tipos": sorted({h["tipo"] for h in bloqueantes}),
                }
            )
            continue
        limpias.append(fila)
    return limpias, incidencias


def seleccionar_por_clase(
    filas: list[dict[str, Any]],
    cuota: int,
    minimo_no_sinteticos: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """Selecciona hasta ``cuota`` por clase, sin sintéticos en val/test.

    Se usan primero los ejemplos no sintéticos (son los únicos que pueden ir a
    validación y prueba) y los sintéticos completan la cuota. Si una clase no
    llega a ``cuota`` tras deduplicar, se detiene con un mensaje que indica
    cuántos ejemplos faltan.
    """
    por_clase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fila in filas:
        por_clase[fila["tipologia"]].append(fila)

    seleccion: list[dict[str, Any]] = []
    detalle: dict[str, dict[str, int]] = {}
    for tipologia in TIPOLOGIAS:
        disponibles = por_clase.get(tipologia, [])
        no_sint = [f for f in disponibles if f.get("origen") != "sintetico_llm"]
        sint = [f for f in disponibles if f.get("origen") == "sintetico_llm"]
        detalle[tipologia] = {
            "disponibles_no_sinteticos": len(no_sint),
            "disponibles_sinteticos": len(sint),
        }
        if len(no_sint) < minimo_no_sinteticos:
            raise SystemExit(
                f"Clase {tipologia}: solo {len(no_sint)} ejemplos no sintéticos; "
                f"se necesitan al menos {minimo_no_sinteticos} para llenar val/test."
            )
        elegidos = no_sint[:cuota]
        if len(elegidos) < cuota:
            elegidos += sint[: cuota - len(elegidos)]
        if len(elegidos) < cuota:
            raise SystemExit(
                f"Clase {tipologia}: solo hay {len(elegidos)} ejemplos únicos tras "
                f"deduplicar y se requieren {cuota} (faltan {cuota - len(elegidos)}). "
                "Genera más sintéticos con scripts/corpus_generate.py o añade "
                "ejemplos manuales."
            )
        detalle[tipologia]["seleccionados"] = len(elegidos)
        detalle[tipologia]["seleccionados_sinteticos"] = sum(
            1 for f in elegidos if f.get("origen") == "sintetico_llm"
        )
        seleccion.extend(elegidos)
    return seleccion, detalle


def particionar(
    filas: list[dict[str, Any]], seed: int, fraccion_val: float = 0.15, fraccion_test: float = 0.15
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Partición estratificada; los sintéticos van *solo* a train (regla 9)."""
    rng = random.Random(seed)
    por_clase: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fila in filas:
        por_clase[fila["tipologia"]].append(fila)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []

    for tipologia in TIPOLOGIAS:
        grupo = por_clase[tipologia]
        sinteticos = [f for f in grupo if f.get("origen") == "sintetico_llm"]
        no_sinteticos = [f for f in grupo if f.get("origen") != "sintetico_llm"]
        rng.shuffle(no_sinteticos)
        n = len(grupo)
        n_test = max(1, round(n * fraccion_test))
        n_val = max(1, round(n * fraccion_val))
        if len(no_sinteticos) < n_test + n_val:
            raise SystemExit(
                f"Clase {tipologia}: {len(no_sinteticos)} no sintéticos no alcanzan "
                f"para val ({n_val}) + test ({n_test})."
            )
        test.extend(no_sinteticos[:n_test])
        val.extend(no_sinteticos[n_test : n_test + n_val])
        train.extend(no_sinteticos[n_test + n_val :] + sinteticos)

    # Orden estable dentro de cada split (por id) para que el manifiesto sea reproducible.
    for lista in (train, val, test):
        lista.sort(key=lambda f: f["id"])
    return train, val, test


def validar_particion(
    train: list[dict[str, Any]],
    val: list[dict[str, Any]],
    test: list[dict[str, Any]],
) -> None:
    if any(f.get("origen") == "sintetico_llm" for f in val + test):
        raise SystemExit("Regla 9 violada: hay ejemplos sintéticos en validación o prueba.")
    ids = [f["id"] for f in train + val + test]
    if len(ids) != len(set(ids)):
        raise SystemExit("Hay ids duplicados entre splits.")
    faltantes = set(TIPOLOGIAS) - {f["tipologia"] for f in train}
    if faltantes:
        raise SystemExit(f"Clases ausentes en train: {sorted(faltantes)}")
    for nombre, split in (("train", train), ("val", val), ("test", test)):
        for tipologia in TIPOLOGIAS:
            n = sum(1 for f in split if f["tipologia"] == tipologia)
            if n == 0:
                raise SystemExit(f"{nombre} sin ejemplos de {tipologia}")


def escribir_reporte(
    corpus: list[dict[str, Any]],
    train: list[dict[str, Any]],
    val: list[dict[str, Any]],
    test: list[dict[str, Any]],
    descartes: list[dict[str, Any]],
    incidencias: list[dict[str, Any]],
    detalle: dict[str, dict[str, int]],
    ruta: Path,
    seed: int,
) -> None:
    def tabla_por_clase(split: list[dict[str, Any]]) -> str:
        conteo = Counter(f["tipologia"] for f in split)
        lineas = ["| Clase | Ejemplos |", "|---|---:|"]
        for t in TIPOLOGIAS:
            lineas.append(f"| `{t}` | {conteo.get(t, 0)} |")
        lineas.append(f"| **Total** | **{len(split)}** |")
        return "\n".join(lineas)

    filas_origen = [
        "| Clase | " + " | ".join(["manual", "plantilla_legitima", "sintetico_llm"]) + " |"
    ]
    filas_origen.append("|---|" + "---:|" * 3)
    for t in TIPOLOGIAS:
        sub = [f for f in corpus if f["tipologia"] == t]
        c = Counter(f["origen"] for f in sub)
        filas_origen.append(
            f"| `{t}` | {c.get('manual', 0)} | {c.get('plantilla_legitima', 0)} "
            f"| {c.get('sintetico_llm', 0)} |"
        )

    motivos = Counter(d["motivo"] for d in descartes)
    pii = [i for i in incidencias if i.get("motivo") == "pii_bloqueante"]
    excluidos = [i for i in incidencias if i.get("motivo") == "excluido_revision"]
    errores = [
        i
        for i in incidencias
        if i.get("motivo") not in ("pii_bloqueante", "excluido_revision")
    ]
    confirmados = sum(1 for f in corpus if f.get("revision_autor") == "confirmado")
    pendientes = len(corpus) - confirmados
    estado_etiquetas = (
        f"fue confirmada por el autor para los {len(corpus)} mensajes."
        if pendientes == 0
        else (
            f"está confirmada en {confirmados} de {len(corpus)} mensajes; "
            f"quedan {pendientes} pendientes."
        )
    )
    con_borrador = [f for f in corpus if f.get("tipologia_borrador")]
    coincidencias_borrador = sum(
        1 for f in con_borrador if f["tipologia_borrador"] == f["tipologia"]
    )
    acuerdo_pct = (
        round(100 * coincidencias_borrador / len(con_borrador), 1)
        if con_borrador
        else 0.0
    )
    nota_excluidos = ""
    if excluidos:
        detalle_excluidos = "; ".join(
            f"`{i.get('id')}` — {i.get('detalle', '')}" for i in excluidos
        )
        nota_excluidos = f"- Exclusiones de revisión manual: {detalle_excluidos}.\n"

    filas_detalle = []
    for t in TIPOLOGIAS:
        d = detalle[t]
        filas_detalle.append(
            f"| `{t}` | {d['disponibles_no_sinteticos']} | {d['disponibles_sinteticos']} "
            f"| {d['seleccionados']} | {d['seleccionados_sinteticos']} |"
        )

    contenido = f"""# Cobertura del corpus — VerifIA (Fase 2)

Generado automáticamente por `scripts/corpus_build.py`.
Fecha: {ahora_iso()} · Semilla: `{seed}`.

## Totales

- Mensajes en el corpus: **{len(corpus)}**
- Reparto: **{len(train)} train / {len(val)} val / {len(test)} test**
- Balance: {json.dumps(contar_por(corpus, "tipologia"), ensure_ascii=False)}
- Orígenes: {json.dumps(contar_por(corpus, "origen"), ensure_ascii=False)}

## Cobertura por clase

### Train

{tabla_por_clase(train)}

### Validación

{tabla_por_clase(val)}

### Prueba (reservada)

{tabla_por_clase(test)}

## Origen por clase

{chr(10).join(filas_origen)}

## Acuerdo borrador ↔ etiqueta humana

- Mensajes con `tipologia_borrador`: **{len(con_borrador)}**
- Coincidencias con la etiqueta final: **{coincidencias_borrador}** ({acuerdo_pct} %)
- Discrepancias corregidas por el autor: **{len(con_borrador) - coincidencias_borrador}**

Es evidencia adicional de calidad; **no** sustituye el kappa del §8.7.

## Depuración

| Concepto | Cantidad |
|---|---:|
| Duplicados exactos eliminados | {motivos.get('duplicado_exacto', 0)} |
| Casi duplicados eliminados (coseno ≥ 0.90) | {motivos.get('casi_duplicado', 0)} |
| Mensajes descartados por PII bloqueante | {len(pii)} |
| Mensajes excluidos por revisión manual | {len(excluidos)} |
| Registros con errores de esquema | {len(errores)} |

Los pares descartados y sus similitudes están en `data/annotated/descartes_dedupe.json`.
No se guarda el valor de ningún dato personal detectado (regla 2); solo el tipo.

## Disponibilidad antes de seleccionar

| Clase | No sintéticos | Sintéticos | Seleccionados | Sintéticos usados |
|---|---:|---:|---:|---:|
""" + "\n".join(
        filas_detalle
    ) + f"""

## Verificación de reglas

- [x] 500 mensajes, 100 por clase.
- [x] Sin duplicados exactos ni casi duplicados (coseno < 0.90).
- [x] Sin PII real detectada por el chequeo de la Fase 2.
- [x] `sintetico_llm` solo en `train`.
- [x] Conjunto de prueba reservado (no usar para umbrales ni prompts).
- [{'x' if pendientes == 0 else ' '}] Revisión humana de etiquetas: {confirmados} confirmadas,
  {pendientes} pendientes (`revision_autor`; ver `docs/guia_anotacion.md`).

## Limitaciones y notas

- El corpus no contiene una colección `publico` verbatim. Los boletines y notas
  revisados (Condusef, Guardia Nacional CERT-MX, SSPC, prensa) describen las
  modalidades, pero no publican los mensajes completos; citarlos como ejemplos
  habría exigido inventar el texto. Se documenta como limitación y el esquema
  queda listo para incorporar capturas propias del autor.
- La etiqueta de los mensajes sintéticos se conserva en `tipologia_borrador`.
  La etiqueta final (`tipologia`) {estado_etiquetas}
- La verificación de PII de esta fase es un chequeo de regex + Luhn/CLABE.
  La Fase 3 la repetirá con Presidio sobre el corpus completo.
- Los enlaces usan dominios inventados (no reservados) y no se verificó que
  existan. La Fase 3 los reduce a `[ENLACE:dominio.tld]`; aquí se conservan como
  señal textual.
{nota_excluidos}"""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cuota", type=int, default=100, help="mensajes por clase")
    parser.add_argument("--min-no-sinteticos", type=int, default=30, help="mínimo por clase")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--annotated", type=Path, default=ANNOTATED)
    args = parser.parse_args(argv)

    filas, incidencias = cargar_fuentes()
    print(f"Fuentes leídas: {len(filas)} registros válidos, {len(incidencias)} incidencias")

    limpias, pii = auditar_pii(filas)
    incidencias.extend(pii)
    print(f"Tras auditoría de PII: {len(limpias)} (descartados {len(pii)})")

    unicas, descartes = deduplicar(limpias)
    print(f"Tras deduplicar: {len(unicas)} (descartados {len(descartes)})")

    corpus, detalle = seleccionar_por_clase(
        unicas, args.cuota, args.min_no_sinteticos
    )
    corpus.sort(key=lambda f: (TIPOLOGIAS.index(f["tipologia"]), f["id"]))

    train, val, test = particionar(corpus, args.seed)
    validar_particion(train, val, test)

    # Metadatos de construcción (sin texto ni PII).
    for fila in corpus:
        fila["version_corpus"] = "2.0"

    escribir_jsonl(args.annotated, corpus)
    SPLITS.mkdir(parents=True, exist_ok=True)
    escribir_jsonl(SPLITS / "train.jsonl", train)
    escribir_jsonl(SPLITS / "val.jsonl", val)
    escribir_jsonl(SPLITS / "test.jsonl", test)
    (ROOT / "data" / "annotated" / "descartes_dedupe.json").write_text(
        json.dumps(descartes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    manifiesto = {
        "version": "2.0",
        "fecha": ahora_iso(),
        "semilla": args.seed,
        "cuota_por_clase": args.cuota,
        "script": "scripts/corpus_build.py",
        "excluidos_revision": [
            {"id": i.get("id"), "detalle": i.get("detalle", "")}
            for i in incidencias
            if i.get("motivo") == "excluido_revision"
        ],
        "conteos": {
            "total": len(corpus),
            "train": len(train),
            "val": len(val),
            "test": len(test),
            "por_tipologia": contar_por(corpus, "tipologia"),
            "por_origen": contar_por(corpus, "origen"),
        },
        "conteos_por_split": {
            "train": {
                "por_tipologia": contar_por(train, "tipologia"),
                "por_origen": contar_por(train, "origen"),
            },
            "val": {
                "por_tipologia": contar_por(val, "tipologia"),
                "por_origen": contar_por(val, "origen"),
            },
            "test": {
                "por_tipologia": contar_por(test, "tipologia"),
                "por_origen": contar_por(test, "origen"),
            },
        },
        "hashes_sha256": {
            "corpus.jsonl": sha256_archivo(args.annotated),
            "train.jsonl": sha256_archivo(SPLITS / "train.jsonl"),
            "val.jsonl": sha256_archivo(SPLITS / "val.jsonl"),
            "test.jsonl": sha256_archivo(SPLITS / "test.jsonl"),
        },
        "descartes": {
            "duplicados_exactos": sum(1 for d in descartes if d["motivo"] == "duplicado_exacto"),
            "casi_duplicados": sum(1 for d in descartes if d["motivo"] == "casi_duplicado"),
            "pii_bloqueante": len(pii),
        },
    }
    (SPLITS / "split_manifest.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    escribir_reporte(corpus, train, val, test, descartes, incidencias, detalle, REPORTE, args.seed)

    print(json.dumps(resumen(corpus), ensure_ascii=False, indent=2))
    print(f"Train {len(train)} / Val {len(val)} / Test {len(test)}")
    print(f"Escrito: {args.annotated}")
    print(f"Reporte: {REPORTE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
