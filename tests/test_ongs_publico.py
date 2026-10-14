"""GET /reconecta/publico/ongs — aba "ONGs na rede" da Home (rodada 16)."""
import os
from datetime import timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from models import Doacao, Estabelecimento, db  # noqa: E402


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


@pytest.fixture
def cliente():
    return app.test_client()


def _estabelecimento(nome, endereco, ong=True, email=None):
    com = Estabelecimento(nome=nome, cnpj=f"{hash(nome) % 10**8:08d}00155",
                          email=email or f"{nome.lower().replace(' ', '')[:10]}@exemplo.test",
                          telefone="11000000000", endereco=endereco,
                          sem_fins_lucrativos=ong)
    db.session.add(com)
    db.session.flush()
    return com


def _pedido(ong, status="DISPONIVEL", dias=3):
    pedido = Doacao(estabelecimento_id=ong.id, status=status,
                    data_limite_retirada=agora_brasilia_sem_fuso() + timedelta(days=dias))
    db.session.add(pedido)
    db.session.flush()
    return pedido


def test_lista_ongs_nome_cidade_e_pedidos(cliente):
    with app.app_context():
        ong_a = _estabelecimento("ONG Aurora", "Rua A, 1 - Centro, Osasco/SP - 06000000")
        ong_b = _estabelecimento("ONG Benção", "Av B, 2 - Centro, Barueri/SP - 06400000")
        _pedido(ong_b)
        _pedido(ong_b)
        _pedido(ong_a)
        _estabelecimento("Mercado Comum", "Rua C, 3 - Centro, São Paulo/SP - 01000000", ong=False)
        db.session.commit()
    resposta = cliente.get("/reconecta/publico/ongs")
    assert resposta.status_code == 200
    lista = resposta.json
    assert [o["nome"] for o in lista] == ["ONG Benção", "ONG Aurora"]
    assert lista[0]["municipio_uf"] == "Barueri/SP"
    assert lista[1]["pedidos_abertos"] == 1
    # empresa não-ONG não aparece
    assert all(o["nome"] != "Mercado Comum" for o in lista)
    # minimização: nenhum campo de contato ou documento
    for item in lista:
        assert set(item) == {"nome", "municipio_uf", "pedidos_abertos"}


def test_ong_sem_pedido_aparece_com_zero(cliente):
    with app.app_context():
        _estabelecimento("ONG Zen", "Rua Z, 9 - Vila, Cotia/SP - 06700000")
        db.session.commit()
    resposta = cliente.get("/reconecta/publico/ongs")
    assert resposta.json == [{"nome": "ONG Zen", "municipio_uf": "Cotia/SP",
                              "pedidos_abertos": 0}]


def test_pedido_vencido_ou_fechado_nao_conta(cliente):
    with app.app_context():
        ong = _estabelecimento("ONG Sol", "Rua S, 1 - Centro, Osasco/SP - 06000000")
        _pedido(ong, status="RETIRADA")
        fechado = _pedido(ong)
        fechado.data_limite_retirada = agora_brasilia_sem_fuso() - timedelta(hours=1)
        db.session.commit()
    assert cliente.get("/reconecta/publico/ongs").json[0]["pedidos_abertos"] == 0


def test_ong_anonimizada_some_da_lista(cliente):
    with app.app_context():
        ong = _estabelecimento("ONG Viva", "Rua V, 1 - Centro, Osasco/SP - 06000000")
        _pedido(ong)
        ong.email = "removido-empresa-1@removido.invalid"
        db.session.commit()
    assert cliente.get("/reconecta/publico/ongs").json == []


def test_ordem_pedidos_depois_nome(cliente):
    with app.app_context():
        ong_z = _estabelecimento("ONG Zeta", "Rua Z, 1 - Centro, Osasco/SP - 06000000")
        ong_a = _estabelecimento("ONG Alfa", "Rua A, 1 - Centro, Osasco/SP - 06000000")
        _pedido(ong_a)
        _pedido(ong_z)
        db.session.commit()
    assert [o["nome"] for o in cliente.get("/reconecta/publico/ongs").json] == \
        ["ONG Alfa", "ONG Zeta"]


def test_endereco_sem_municipio(cliente):
    with app.app_context():
        _estabelecimento("ONG Nua", "Endereço sem cidade")
        db.session.commit()
    assert cliente.get("/reconecta/publico/ongs").json[0]["municipio_uf"] is None
