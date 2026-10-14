"""A exceção do Swagger UI não altera a CSP das páginas e da API."""

import os
import re

os.environ["DATABASE_URL"] = "sqlite://"

from app import _CSP, app  # noqa: E402


def test_swagger_recebe_nonce_apenas_no_script_de_inicializacao():
    cliente = app.test_client()
    resposta = cliente.get("/swagger")
    assert resposta.status_code == 200
    html = resposta.get_data(as_text=True)
    nonces = re.findall(r'<script type="text/javascript" nonce="([^"]+)">', html)
    assert len(nonces) == 1
    assert "SwaggerUIBundle" in html
    nonce = nonces[0]
    csp = resposta.headers["Content-Security-Policy"]
    assert csp == _CSP.replace("script-src 'self' https://cdn.jsdelivr.net;",
                               f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}';")
    assert "'unsafe-inline'" not in csp.split("style-src", 1)[0]
    assert nonce not in cliente.get("/swagger").get_data(as_text=True)


def test_demais_rotas_conservam_csp_estrita():
    cliente = app.test_client()
    for caminho in ("/", "/dashboard", "/swagger.json", "/reconecta/saude"):
        resposta = cliente.get(caminho)
        assert resposta.headers["Content-Security-Policy"] == _CSP
        assert "nonce-" not in resposta.headers["Content-Security-Policy"]
        assert "'unsafe-inline'" not in resposta.headers["Content-Security-Policy"].split(
            "style-src", 1)[0]
