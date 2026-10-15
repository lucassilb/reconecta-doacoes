"""Entradas hostis nas fronteiras de log e de consulta externa."""

import io
import logging

import pytest

import cnpj_service
import geo
from Auth import registrar_auditoria
from app import app, erro_api_interno


def test_controles_do_usuario_nao_criam_linha_de_log():
    saida = io.StringIO()
    handler = logging.StreamHandler(saida)
    logger = logging.getLogger("reconecta.teste.controles")
    auditoria = logging.getLogger("reconecta.auditoria")
    alvos = (logger, app.logger, auditoria)
    for alvo in alvos:
        alvo.addHandler(handler)
    try:
        logger.warning("caminho %s", "/reconecta/erro\r\nFORJADO\t\x1b[31m")
        with app.test_request_context("/reconecta/%0D%0AFORJADO"):
            erro_api_interno(RuntimeError("erro controlado"))
        with app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.\r\nFORJADO.77"}):
            registrar_auditoria("login", "falha")
    finally:
        for alvo in alvos:
            alvo.removeHandler(handler)
    linhas = saida.getvalue().splitlines()
    assert len(linhas) == 4
    assert linhas[0] == "caminho /reconecta/erro  FORJADO  [31m"
    assert linhas[1] == "Falha em /reconecta/  FORJADO"
    assert linhas[2] == "RuntimeError: erro controlado"
    assert '"evento":"login"' in linhas[3]
    assert '"ip":null' in linhas[3]
    assert "FORJADO" not in linhas[3]
    assert all("\r" not in linha and "\x1b" not in linha for linha in linhas)


def test_cnpj_nao_consulta_host_fora_da_allowlist(monkeypatch):
    cnpj_service._cache.clear()
    monkeypatch.setattr(cnpj_service, "FONTES", ((
        "invalida", "https://169.254.169.254/{}/metadata", lambda resposta: resposta),))
    monkeypatch.setattr(cnpj_service.requests, "get", lambda *a, **k: pytest.fail("rede indevida"))
    with pytest.raises(cnpj_service.ConsultaCNPJError) as erro:
        cnpj_service.consultar_cnpj("47508411000156")
    assert erro.value.status == 503


@pytest.mark.parametrize("url", [
    "http://nominatim.openstreetmap.org/search",
    "https://nominatim.openstreetmap.org.evil.test/search",
    "https://brasilapi.com.br@169.254.169.254/api/cep/v2/13010001",
    "https://brasilapi.com.br/api/cep/v2/13010001/../../admin",
    "https://brasilapi.com.br/api/cep/v2/１２３４５６７８",
])
def test_geo_rejeita_url_fora_das_rotas_permitidas(monkeypatch, url):
    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: pytest.fail("rede indevida"))
    with pytest.raises(ValueError):
        geo._get_json(url)


def test_geo_nominatim_exige_parametros_da_consulta(monkeypatch):
    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: pytest.fail("rede indevida"))
    with pytest.raises(ValueError):
        geo._get_json(geo.NOMINATIM, {"q": "http://169.254.169.254"})
    assert geo._brasilapi("13010/../") is None
