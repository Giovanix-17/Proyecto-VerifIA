"""Prueba de humo del andamiaje (Fase 1).

Comprueba que el paquete se importa y que el servicio arranca y responde.
No valida lógica de negocio: eso empieza en la Fase 3.
"""

from fastapi.testclient import TestClient

import verifia
from verifia.api.main import app


def test_version() -> None:
    assert verifia.__version__ == "0.1.0"


def test_health() -> None:
    cliente = TestClient(app)
    respuesta = cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "version": verifia.__version__}
