"""Servicio HTTP de VerifIA.

Esqueleto de la Fase 1: solo expone la comprobación de vida que usan Docker y
las pruebas. En la Fase 7 se añaden los endpoints de análisis
(`/api/analizar/texto` e `/api/analizar/imagen`) y el frontend estático de `web/`.
"""

from fastapi import FastAPI

from verifia import __version__

app = FastAPI(
    title="VerifIA",
    description="Detección orientativa de fraude y extorsión digital en mensajes en español.",
    version=__version__,
)


@app.get("/health", tags=["sistema"])
def health() -> dict[str, str]:
    """Comprobación de vida usada por el healthcheck de Docker y por pytest."""
    return {"status": "ok", "version": __version__}
