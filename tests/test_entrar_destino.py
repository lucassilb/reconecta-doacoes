"""?proximo= pós-login só navega dentro do próprio site (CodeQL js/xss e
js/client-side-unvalidated-url-redirection, alertas 10-13 da rodada 26).

O regex anterior aceitava "/\t/evil.com": o navegador remove a tabulação ao
interpretar a URL e o caminho virava "//evil.com" — redirecionamento aberto.
A prova é no navegador de verdade (a normalização é dele, não da nossa regex),
com sessão real: cadastro e login acontecem pela própria API local.
"""
import os
import socket
import threading
import time
import urllib.parse
import urllib.request
import json

import pytest

os.environ["DATABASE_URL"] = "sqlite://"
from app import app  # noqa: E402


def _porta_livre():
    with socket.socket() as soquete:
        soquete.bind(("127.0.0.1", 0))
        return soquete.getsockname()[1]


@pytest.fixture(scope="module")
def servidor():
    """Servidor Flask real numa porta aleatória, no processo de teste."""
    porta = _porta_livre()
    fio = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=porta,
                               threaded=True, use_reloader=False),
        daemon=True)
    fio.start()
    base = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/reconecta/saude", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    else:
        pytest.fail("servidor de teste não subiu")
    return base


def _post(base, caminho, corpo):
    req = urllib.request.Request(base + caminho, data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=10)


@pytest.fixture(scope="module")
def sessao(servidor):
    """Doador cadastrado pela API e o valor do cookie de sessão do login."""
    _post(servidor, "/reconecta/cadastro/doador", {
        "nome": "Navegador Teste", "cpf": "52998224725",
        "email": "navegador@exemplo.invalid", "telefone": "11999996666",
        "senha": "Segredo123", "aceite_privacidade": True})
    resposta = _post(servidor, "/reconecta/auth/login", {
        "identificador": "navegador@exemplo.invalid", "senha": "Segredo123"})
    cookie = resposta.headers["Set-Cookie"].split(";", 1)[0]
    return cookie.split("=", 1)[1]


@pytest.fixture(scope="module")
def navegador():
    sync = pytest.importorskip("playwright.sync_api")
    try:
        with sync.sync_playwright() as playwright:
            try:
                instancia = playwright.chromium.launch(channel="chrome", headless=True)
            except Exception:
                instancia = playwright.chromium.launch(headless=True)
            yield instancia
            instancia.close()
    except Exception as exc:
        pytest.skip(f"sem navegador headless nesta máquina: {exc}")


def _aguardar_saida(pagina, timeout=8):
    pagina.wait_for_url(lambda url: "/entrar" not in url, timeout=timeout * 1000)
    return pagina.url


# valor cru de ?proximo= (será percentual-codificado na URL da página) → destino esperado
CASOS = [
    ("/doacoes/5", "/doacoes/5"),                    # caminho interno legítimo
    ("/?assistente=1", "/?assistente=1"),
    ("", "/painel"),
    ("//evil.example/", "/painel"),                  # protocol-relative
    ("https://evil.example/x", "/painel"),           # origem estranha
    ("javascript:alert(1)", "/painel"),              # esquema de script (XSS)
    ("data:text/html,<b>x</b>", "/painel"),
    ("/\\evil.example", "/painel"),                  # contrabarra vira "/" em http(s)
    ("/\t/evil.example", "/painel"),                 # tab removida pelo parser → //evil
    ("/\r\n/evil.example", "/painel"),
    ("/<img src=x onerror=alert(1)>", "/painel"),  # espaço/caractere de controle barrado
]


def test_proximo_so_navega_na_mesma_origem(servidor, sessao, navegador):
    contexto = navegador.new_context()
    # o SSE do layout segura uma conexão HTTP/1.1 por página; sem abortá-lo as
    # próximas navegações esgotam o pool do navegador e o fetch da sessão trava
    contexto.route("**/reconecta/tempo-real*", lambda rota: rota.abort())
    contexto.add_cookies([{"name": "session", "value": sessao, "url": servidor}])
    pagina = contexto.new_page()
    for valor, esperado in CASOS:
        alvo = servidor + "/entrar?proximo=" + urllib.parse.quote(valor, safe="")
        pagina.goto(alvo, wait_until="load", timeout=15000)
        url_final = _aguardar_saida(pagina)
        assert url_final == servidor + esperado, (valor, url_final)
        # nada de javascript: executado nem navegação para fora do site
        assert url_final.startswith(servidor), (valor, url_final)
    contexto.close()


def test_submit_com_proximo_estranho_volta_ao_painel(servidor, sessao, navegador):
    """Caminho da linha 191: login pelo formulário com ?proximo= maligno."""
    contexto = navegador.new_context()
    contexto.route("**/reconecta/tempo-real*", lambda rota: rota.abort())
    pagina = contexto.new_page()
    pagina.goto(servidor + "/entrar?proximo=" +
                urllib.parse.quote("/\t/evil.example", safe=""),
                wait_until="load", timeout=15000)
    pagina.fill("#identificador", "navegador@exemplo.invalid")
    pagina.fill("#senha", "Segredo123")
    pagina.click("#btn-entrar")
    pagina.wait_for_url("**/painel", timeout=8000)
    assert pagina.url == servidor + "/painel", pagina.url
    contexto.close()
