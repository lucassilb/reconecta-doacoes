"""Home, cabeçalho e página do alimento doado para quem já entrou (R15b e R16).

O comportamento é provado no navegador (r15/prova/corrida.mjs, r16/home-prova/telas.mjs).
Estes testes guardam o contrato no código servido, para a regressão não voltar sem ninguém ver:
- o evento "reconecta:sessao" só sai depois do DOMContentLoaded (antes, se /auth/me
  respondesse antes de home.js/excedente.js executarem, a pessoa logada era tratada
  como visitante e recebia convites de cadastro e login);
- a Home tem o bloco "Agora na rede" com três abas e o filtro por categoria não leva a
  cadastro; o estado vazio só manda o visitante ao cadastro;
- os nomes são fixos: "Pedidos das ONGs" e "Alimentos doados"; "Sua doação" para quem doou.
"""
import os

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


def test_home_tem_tres_abas_e_filtro_sem_cadastro():
    html = cliente.get("/").get_data(as_text=True)
    for aba in ("aba-pedidos", "aba-doados", "aba-ongs"):
        assert f'id="{aba}" aria-controls="rede-painel"' in html
    assert 'role="tablist"' in html and 'role="tabpanel"' in html
    assert ">\n          Pedidos das ONGs <" in html and ">\n          Alimentos doados <" in html and ">\n          ONGs na rede <" in html
    for ancora in ('id="doacoes"', 'id="excedentes"', 'id="ongs"', 'id="como-funciona"'):
        assert ancora in html  # links antigos e do menu continuam chegando à aba certa
    home = _js("home.js")
    filtro = home[home.index("function montarFiltro"):home.index("function temCategoria")]
    assert 'el("button"' in filtro and "/cadastro" not in filtro and 'el("a"' not in filtro


def test_estado_vazio_so_manda_visitante_ao_cadastro():
    home = _js("home.js")
    acao = home[home.index("function acaoVazio"):home.index("function vazio(")]
    linhas_cadastro = [linha for linha in acao.splitlines() if "/cadastro" in linha]
    assert linhas_cadastro and all("usuarioAtual ? null :" in linha for linha in linhas_cadastro)
    assert "Doar o que sobrou" in acao and "Publicar o primeiro pedido" in acao
    assert "Cadastrar uma ONG não cria pedido" in home


def test_nomes_fixos_e_sua_doacao():
    layout = _js("layout.js")
    assert '{ rotulo: "Pedidos das ONGs", href: "/#doacoes" }' in layout
    assert '["Alimentos doados", "/#excedentes"]' in layout and "Excedentes de hoje" not in layout
    assert 'href: "/?assistente=1", classe: "btn btn--primario btn--pequeno cabecalho__doar" }, ["Doar"]' in layout
    home = _js("home.js")
    assert '"Sua doação"' in home and "Aguardando uma ONG retirar" in home and "Doado por " in home
    excedente = _js("excedente.js")
    assert 'titulo.textContent = "Sua doação"' in excedente and "Doar também" in excedente
    assert "Apenas ONGs podem reservar." not in excedente  # sem o "não" seco para quem não é ONG
    pagina = cliente.get("/excedentes/1").get_data(as_text=True)
    assert "Alimentos doados" in pagina and "doacao.css" not in pagina
