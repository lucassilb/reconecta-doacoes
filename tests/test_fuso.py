"""Datas de eventos UTC e prazos locais apresentados no fuso de Brasília."""

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, ItemDoacao, db  # noqa: E402


BRASILIA = ZoneInfo("America/Sao_Paulo")


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()


def test_doacao_2330_brasilia_entra_no_dia_correto_do_dashboard():
    dia_brasilia = datetime.now(BRASILIA).date() - timedelta(days=1)
    horario_brasilia = datetime.combine(dia_brasilia, time(23, 30), BRASILIA)
    horario_utc = horario_brasilia.astimezone(timezone.utc).replace(tzinfo=None)
    assert horario_utc.date() == dia_brasilia + timedelta(days=1)
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado", cnpj="47508411000156",
                                  email="mercado@exemplo.com", telefone="11999998888",
                                  endereco="Rua A, São Paulo/SP")
        doador = Doador(nome="Doador", cpf="52998224725",
                        email="doador@exemplo.com", telefone="11999997777")
        db.session.add_all((empresa, doador))
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id,
                        data_limite_retirada=datetime.combine(
                            dia_brasilia + timedelta(days=2), time(18)))
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Leite", categoria="Laticínios",
                          quantidade=100, unidade_medida="unidade")
        db.session.add(item)
        db.session.flush()
        db.session.add(Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id,
                                   doador_id=doador.id, alimento="Leite",
                                   categoria="Laticínios", quantidade=1,
                                   unidade_medida="unidade", validade=date.today() + timedelta(days=5),
                                   respostas="{}", foto_arquivo="foto.jpg",
                                   status="ACEITA", criado_em=horario_utc))
        db.session.commit()
    resposta = app.test_client().get("/reconecta/dashboard")
    assert resposta.status_code == 200
    por_dia = {linha["data"]: linha["doacoes"] for linha in resposta.json["por_dia"]}
    assert por_dia[dia_brasilia.isoformat()] == 1
    assert por_dia[(dia_brasilia + timedelta(days=1)).isoformat()] == 0
    assert datetime.fromisoformat(resposta.json["gerado_em"]).utcoffset() is not None
    assert datetime.fromisoformat(resposta.json["ultimas_doacoes"][0]["data"]) == horario_brasilia
    cliente = app.test_client()
    publico = cliente.get("/reconecta/publico/doacoes/1").json
    legado = cliente.get("/reconecta/doacoes/1").json
    prazo = datetime.combine(dia_brasilia + timedelta(days=2), time(18), BRASILIA)
    assert datetime.fromisoformat(publico["receber_ate"]) == prazo
    assert datetime.fromisoformat(legado["data_limite_retirada"]) == prazo
    for valor in (publico["data_cadastro"], legado["data_cadastro"]):
        assert datetime.fromisoformat(valor).utcoffset() is not None
    with app.app_context():
        from Contribuicoes import serializar_contribuicao
        contribuicao = serializar_contribuicao(Contribuicao.query.one(), entrega=True)
    assert datetime.fromisoformat(contribuicao["criado_em"]) == horario_brasilia
    assert datetime.fromisoformat(contribuicao["entrega"]["receber_ate"]) == prazo
