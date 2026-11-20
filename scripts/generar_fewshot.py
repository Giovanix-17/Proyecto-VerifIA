"""Hornea el few-shot del Nivel 2 para la API (Fase 7).

La cascada del servicio usa pocos ejemplos de **train** en el prompt del
Nivel 2 (regla 10: nunca val/test). Para que el contenedor no necesite
``data/``, este script selecciona los mismos ejemplos deterministas de la
Fase 5 (misma función y semilla que ``elegir_few_shot``) y los guarda en
``models/fewshot_nivel2.json``.

Los textos ya están sanitizados (regla 1) y provienen del corpus, que no
contiene datos personales reales (§8.2). Solo hay que volver a ejecutarlo si
cambia el corpus de train::

    python scripts/generar_fewshot.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_common import ROOT  # noqa: E402
from fase5_common import cargar_split, elegir_few_shot  # noqa: E402

DESTINO = ROOT / "models" / "fewshot_nivel2.json"


def main() -> int:
    ejemplos = elegir_few_shot(cargar_split("train"), por_clase=2, semilla=42)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(ejemplos, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Few-shot guardado en {DESTINO} ({len(ejemplos)} ejemplos).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
