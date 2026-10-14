"""Home e cabeçalho para quem já entrou (R15b).

O comportamento é provado no navegador (r15/prova/corrida.mjs e ux.mjs). Estes testes
guardam o contrato no código servido, para a regressão não voltar sem ninguém ver:
- o evento "reconecta:sessao" só sai depois do DOMContentLoaded (antes, se /auth/me
  respondesse antes de home.js/excedente.js executarem, a pessoa logada era tratada
  como visitante e recebia convites de cadastro e login);
- o estado vazio dos pedidos não manda ninguém logado para /cadastro;
- a seção chama "Pedidos das ONGs" e o topo tem "Doar" para quem entrou.
"""
import os
import re

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402

cliente = app.test_client()


def _js(nome):
    return cliente.get(f"/static/js/{nome}").get_data(as_text=True)


def test_evento_de_sessao_espera_os_scripts_da_pagina():
    layout = _js("layout.js")
    corpo = layout[layout.index("function consultarSessao"):layout.index("api.nomeTitulo")]
    assert "domPronto.then" in corpo
    assert corpo.index("domPronto.then") < corpo.index('dispatchEvent(new CustomEvent("reconecta:sessao"')
    assert 'addEventListener("DOMContentLoaded"' in layout and 'addEventListener("load"' in layout


def test_estado_vazio_dos_pedidos_nao_leva_quem_entrou_ao_cadastro():
    home = _js("home.js")
    vazio = home[home.index("function acoesVazio"):home.index("function montarFalha")]
    logado = vazio[vazio.index("} else if"):]  # ramos de quem já entrou
    assert "/cadastro" not in logado and "/entrar" not in logado
    assert "Doar o que sobrou" in vazio and "/painel#publicar-excedente" in vazio
    # as categorias são só informação: nenhum link
    lista = vazio[vazio.index('"categorias categorias--info"'):]
    assert 'el("a"' not in lista
    convites = home[home.index("function ajustarConvites"):home.index("var abriuPeloEndereco")]
    assert re.search(r"if \(!usuarioAtual\) \{[^}]*\"/cadastro\"", convites)  # /cadastro só para visitante


def test_pagina_e_cabecalho_nomeiam_e_oferecem_doar():
    html = cliente.get("/").get_data(as_text=True)
    assert 'id="doacoes-titulo">Pedidos das ONGs<' in html
    assert "Para ONGs retirarem" in html
    layout = _js("layout.js")
    assert '{ rotulo: "Pedidos das ONGs", href: "/#doacoes" }' in layout
    assert 'href: "/?assistente=1", classe: "btn btn--primario btn--pequeno cabecalho__doar" }, ["Doar"]' in layout
    excedente = _js("excedente.js")
    assert "Oferecido para ONGs retirarem" in excedente and "Doar o que sobrou" in excedente
