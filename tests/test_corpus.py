"""Pruebas de la Fase 2: corpus, depuración y partición.

Se ejecutan con ``pytest`` desde la raíz del proyecto. La mayoría valida el
artefacto real (``data/annotated/corpus.jsonl`` y ``data/splits/``); las pruebas
unitarias cubren las piezas que se reutilizarán en fases posteriores.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from corpus_common import (
    ROOT,
    SENALES,
    TIPOLOGIAS,
    detectar_pii,
    escribir_jsonl,
    extraer_primer_json,
    leer_jsonl,
    normalizar_texto,
    sha256_archivo,
    validar_mensaje,
)

CORPUS = ROOT / "data" / "annotated" / "corpus.jsonl"
SPLITS = ROOT / "data" / "splits"
PII_BLOQUEANTE = {"correo", "telefono", "clabe", "tarjeta", "curp", "rfc"}


# --------------------------------------------------------------------------- #
# Unidades
# --------------------------------------------------------------------------- #
def test_normalizar_texto_conserva_senales_y_limpia_espacios() -> None:
    entrada = "  Hola\u00a0  mundo  \r\n\r\n\r\n  “cita” – guion  "
    assert normalizar_texto(entrada) == 'Hola mundo\n\n"cita" - guion'


def test_extraer_primer_json_ignora_razonamiento_y_bloques() -> None:
    respuesta = (
        "Pensando... el banco pide un código.\n```json\n"
        '{"mensajes": [{"mensaje": "Texto con } dentro", "tipologia": "extorsion"}]}\n```\n'
    )
    datos = extraer_primer_json(respuesta)
    assert datos["mensajes"][0]["mensaje"] == "Texto con } dentro"


def test_extraer_primer_json_falla_sin_objeto() -> None:
    with pytest.raises(ValueError):
        extraer_primer_json("No hay JSON aquí")


def test_validar_mensaje_detecta_tipologia_y_origen_invalidos() -> None:
    errores = validar_mensaje(
        {"id": "x", "texto": "hola", "tipologia": "otra", "origen": "inventado"}
    )
    assert any("tipologia" in e for e in errores)
    assert any("origen" in e for e in errores)


def test_validar_mensaje_rechaza_senales_fuera_del_catalogo() -> None:
    errores = validar_mensaje(
        {
            "id": "x",
            "texto": "hola",
            "tipologia": "legitimo",
            "origen": "manual",
            "senales_alerta": ["inventada"],
        }
    )
    assert any("señales desconocidas" in e for e in errores)


def test_detectar_pii_ignora_placeholders() -> None:
    texto = "Llama al 55 0000 0000 o escribe a ejemplo@example.com y visita example.com"
    tipos = {h["tipo"] for h in detectar_pii(texto)}
    assert not (tipos & PII_BLOQUEANTE)


def test_detectar_pii_encuentra_datos_verosimiles() -> None:
    # Números inventados pero con formato válido: la prueba verifica el detector,
    # no que existan en el corpus.
    texto = (
        "Escribe a juan.perez@gmail.com o llama al +52 55 1234 5678. "
        "Tarjeta 4111 1111 1111 1111."
    )
    tipos = {h["tipo"] for h in detectar_pii(texto)}
    assert "correo" in tipos
    assert "telefono" in tipos
    assert "tarjeta" in tipos


def test_particion_es_reproducible(tmp_path: Path) -> None:
    from corpus_build import particionar

    filas = []
    for tipologia in TIPOLOGIAS:
        for i in range(10):
            filas.append(
                {
                    "id": f"{tipologia}-{i:02d}",
                    "texto": f"texto {i}",
                    "tipologia": tipologia,
                    "origen": "manual",
                }
            )
    a = particionar(filas, seed=7)
    b = particionar(filas, seed=7)
    assert [[f["id"] for f in s] for s in a] == [[f["id"] for f in s] for s in b]


def test_escribir_jsonl_es_utf8(tmp_path: Path) -> None:
    ruta = tmp_path / "x.jsonl"
    escribir_jsonl(ruta, [{"id": "1", "texto": "canción"}])
    assert "canción" in ruta.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Artefacto de la Fase 2
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    if not CORPUS.exists():
        pytest.fail(f"Falta {CORPUS}; ejecuta scripts/corpus_build.py")
    return leer_jsonl(CORPUS)


@pytest.fixture(scope="module")
def splits() -> dict[str, list[dict]]:
    resultado = {}
    for nombre in ("train", "val", "test"):
        ruta = SPLITS / f"{nombre}.jsonl"
        if not ruta.exists():
            pytest.fail(f"Falta {ruta}; ejecuta scripts/corpus_build.py")
        resultado[nombre] = leer_jsonl(ruta)
    return resultado


def test_corpus_tiene_500_y_100_por_clase(corpus: list[dict]) -> None:
    assert len(corpus) == 500
    conteo = Counter(f["tipologia"] for f in corpus)
    assert conteo == {t: 100 for t in TIPOLOGIAS}


def test_ids_unicos_y_esquema_valido(corpus: list[dict]) -> None:
    ids = [f["id"] for f in corpus]
    assert len(ids) == len(set(ids))
    for fila in corpus:
        assert validar_mensaje(fila) == [], fila["id"]
        assert set(fila.get("senales_alerta") or []) <= set(SENALES)


def test_origenes_del_catalogo(corpus: list[dict]) -> None:
    assert {f["origen"] for f in corpus} <= {
        "publico",
        "plantilla_legitima",
        "manual",
        "sintetico_llm",
    }


def test_exclusion_revisada_y_reemplazo(corpus: list[dict]) -> None:
    ids = {f["id"] for f in corpus}
    assert "syn-0147" not in ids
    assert "syn-0216" in ids
    reemplazo = next(f for f in corpus if f["id"] == "syn-0216")
    assert reemplazo["tipologia"] == "oferta_laboral_fraudulenta"
    assert reemplazo["revision_autor"] == "confirmado"


def test_sin_sinteticos_en_val_y_test(splits: dict[str, list[dict]]) -> None:
    for nombre in ("val", "test"):
        assert all(f["origen"] != "sintetico_llm" for f in splits[nombre]), nombre


def test_particion_70_15_15(splits: dict[str, list[dict]]) -> None:
    assert len(splits["train"]) == 350
    assert len(splits["val"]) == 75
    assert len(splits["test"]) == 75
    for nombre, split in splits.items():
        conteo = Counter(f["tipologia"] for f in split)
        assert set(conteo) == set(TIPOLOGIAS), nombre
        assert all(n > 0 for n in conteo.values())


def test_ningun_id_se_repite_entre_splits(splits: dict[str, list[dict]]) -> None:
    ids = [f["id"] for split in splits.values() for f in split]
    assert len(ids) == len(set(ids)) == 500


def test_sin_pii_bloqueante(corpus: list[dict]) -> None:
    for fila in corpus:
        hallazgos = detectar_pii(fila["texto"])
        bloqueantes = [h for h in hallazgos if h["tipo"] in PII_BLOQUEANTE]
        assert not bloqueantes, (fila["id"], [h["tipo"] for h in bloqueantes])


def test_sin_casi_duplicados(corpus: list[dict]) -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    textos = [f["texto"] for f in corpus]
    matriz = TfidfVectorizer(analyzer="char_wb", ngram_range=(4, 4)).fit_transform(textos)
    similitudes = cosine_similarity(matriz)
    # Diagonal = 1; cualquier par distinto debe quedar por debajo del umbral.
    import numpy as np

    np.fill_diagonal(similitudes, 0)
    assert float(similitudes.max()) < 0.90


def test_manifiesto_coincide_con_los_archivos() -> None:
    ruta = SPLITS / "split_manifest.json"
    manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    assert manifiesto["semilla"] == 42
    assert [e["id"] for e in manifiesto["excluidos_revision"]] == ["syn-0147"]
    for nombre, hash_esperado in manifiesto["hashes_sha256"].items():
        archivo = CORPUS if nombre == "corpus.jsonl" else SPLITS / nombre
        assert sha256_archivo(archivo) == hash_esperado, nombre


def test_documentos_de_fase_existen() -> None:
    assert (ROOT / "docs" / "guia_anotacion.md").exists()
    assert (ROOT / "docs" / "reportes" / "cobertura_corpus.md").exists()
