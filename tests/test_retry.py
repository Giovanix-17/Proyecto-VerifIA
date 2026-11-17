"""Pruebas del ayudante de reintentos para las llamadas al LLM (Fase 5)."""

from __future__ import annotations

import httpx
import pytest
from openai import APIStatusError, APITimeoutError

from verifia.classifier import retry

URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _error_http(estado: int) -> APIStatusError:
    peticion = httpx.Request("POST", URL)
    respuesta = httpx.Response(estado, request=peticion, json={"error": "fallo"})
    return APIStatusError("fallo simulado", response=respuesta, body=None)


def _error_timeout() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("POST", URL))


def _sin_espera(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    esperas: list[float] = []
    monkeypatch.setenv("LLM_RETRY_BASE_S", "0")
    monkeypatch.setattr(retry.time, "sleep", lambda segundos: esperas.append(segundos))
    return esperas


def test_es_reintentable_clasifica_estados_y_timeouts() -> None:
    assert retry.es_reintentable(_error_http(400))
    assert retry.es_reintentable(_error_http(429))
    assert retry.es_reintentable(_error_http(503))
    assert retry.es_reintentable(_error_timeout())
    assert not retry.es_reintentable(_error_http(401))
    assert not retry.es_reintentable(_error_http(404))
    assert not retry.es_reintentable(ValueError("JSON inválido"))


def test_reintenta_503_hasta_lograr_la_respuesta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "3")
    esperas = _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        if len(llamadas) < 3:
            raise _error_http(503)
        return "ok"

    assert retry.con_reintentos(llamar, descripcion="prueba") == "ok"
    assert len(llamadas) == 3
    assert len(esperas) == 2


def test_reintenta_400_transitorio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "2")
    _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise _error_http(400)
        return "ok"

    assert retry.con_reintentos(llamar) == "ok"
    assert len(llamadas) == 2


def test_reintenta_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "2")
    _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise _error_timeout()
        return "ok"

    assert retry.con_reintentos(llamar) == "ok"
    assert len(llamadas) == 2


def test_no_reintenta_errores_no_transitorios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "3")
    esperas = _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        raise _error_http(404)

    with pytest.raises(APIStatusError):
        retry.con_reintentos(llamar)
    assert len(llamadas) == 1
    assert esperas == []


def test_respeta_el_maximo_de_intentos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "3")
    esperas = _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        raise _error_http(503)

    with pytest.raises(APIStatusError):
        retry.con_reintentos(llamar)
    assert len(llamadas) == 3
    assert len(esperas) == 2


def test_un_solo_intento_desactiva_los_reintentos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MAX_REINTENTOS", "1")
    esperas = _sin_espera(monkeypatch)
    llamadas: list[int] = []

    def llamar() -> str:
        llamadas.append(1)
        raise _error_http(400)

    with pytest.raises(APIStatusError):
        retry.con_reintentos(llamar)
    assert len(llamadas) == 1
    assert esperas == []
