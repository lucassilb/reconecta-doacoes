"""Correção dos alertas ZAP de isolamento de origem sem relaxar a CSP."""

import os

os.environ["DATABASE_URL"] = "sqlite://"

from app import _CSP, app  # noqa: E402


def test_cabecalhos_de_origem_nas_paginas_e_api():
    cliente = app.test_client()
    for rota in ("/", "/reconecta/saude", "/swagger"):
        resposta = cliente.get(rota)
        assert resposta.status_code == 200
        assert resposta.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert resposta.headers["Cross-Origin-Resource-Policy"] == "same-origin"
        if rota != "/swagger":
            assert resposta.headers["Content-Security-Policy"] == _CSP
        if rota == "/reconecta/saude":
            assert "no-store" in resposta.headers["Cache-Control"]


def test_dados_da_sessao_nao_sao_cacheaveis():
    resposta = app.test_client().get("/reconecta/auth/me")
    assert resposta.status_code == 401
    assert "no-store" in resposta.headers["Cache-Control"]
