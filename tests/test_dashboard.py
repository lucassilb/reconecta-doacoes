import os
from datetime import date, datetime, timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from Dashboard import montar_dashboard  # noqa: E402
from fuso import hoje_brasilia  # noqa: E402
from models import (Contribuicao, Doacao, Doador, Estabelecimento, Instituicao,
                    ItemDoacao, _utc_naive, db)  # noqa: E402


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def test_dashboard_vazio_tem_contrato_e_30_dias():
    resposta = app.test_client().get("/reconecta/dashboard")
    assert resposta.status_code == 200
    dados = resposta.json
    assert set(dados) == {"gerado_em", "indicadores", "por_categoria", "por_dia",
                         "top_empresas", "alertas", "ultimas_doacoes"}
    assert all(valor == 0 for valor in dados["indicadores"].values())
    assert len(dados["por_dia"]) == 30
    assert dados["por_dia"][-1] == {"data": hoje_brasilia().isoformat(), "doacoes": 0}
    with app.app_context():
        assert montar_dashboard()["indicadores"] == dados["indicadores"]


def test_dashboard_agrega_doacoes_aceitas_limita_meta_e_nao_expoe_pessoas():
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado Sol", cnpj="12345678000195",
            email="sigilo@exemplo.com", telefone="11999999999",
            endereco="RUA TESTE, 1 - CENTRO, OSASCO/SP - 06000000")
        doador = Doador(nome="Pessoa Privada", cpf="52998224725",
                        email="pessoa@exemplo.com", telefone="11988888888")
        instituicao = Instituicao(nome="Instituição", cnpj="23456789000189",
            email="instituicao@exemplo.com", telefone="11977777777", endereco="Rua A")
        db.session.add_all((empresa, doador, instituicao))
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id, status="DISPONIVEL",
                         data_cadastro=_utc_naive() - timedelta(days=4),
                         data_limite_retirada=datetime.now() + timedelta(days=2))
        encerrado = Doacao(estabelecimento_id=empresa.id, status="RESERVADA",
                           data_limite_retirada=datetime.now() + timedelta(days=5))
        db.session.add_all((pedido, encerrado))
        db.session.flush()
        leite = ItemDoacao(doacao_id=pedido.id, nome="Leite", categoria="Laticínios",
                           quantidade=100, unidade_medida="unidade")
        pao = ItemDoacao(doacao_id=pedido.id, nome="Pão", categoria="Padaria",
                         quantidade=100, unidade_medida="unidade")
        db.session.add_all((leite, pao))
        db.session.flush()
        for item, quantidade, status in ((leite, 120, "ACEITA"),
                                          (pao, 80, "ACEITA"),
                                          (pao, 10, "CANCELADA")):
            db.session.add(Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id,
                doador_id=doador.id, alimento=item.nome, categoria=item.categoria,
                quantidade=quantidade, unidade_medida=item.unidade_medida,
                validade=date.today() + timedelta(days=10), respostas="{}",
                foto_arquivo="foto.jpg", status=status, criado_em=_utc_naive()))
        db.session.commit()
    resposta = app.test_client().get("/reconecta/dashboard")
    assert resposta.status_code == 200
    dados = resposta.json
    assert dados["indicadores"] == {
        "empresas": 1, "doadores": 1, "instituicoes": 1,
        "pedidos_abertos": 1, "pedidos_encerrados": 1,
        "doacoes_recebidas": 2, "itens_pedidos": 2,
        "itens_atendidos": 1, "percentual_atendimento": 90.0,
    }
    assert dados["por_categoria"] == [
        {"categoria": "Laticínios", "pedido": 100.0, "recebido": 120.0},
        {"categoria": "Padaria", "pedido": 100.0, "recebido": 80.0},
    ]
    assert dados["por_dia"][-1]["doacoes"] == 2
    assert dados["top_empresas"] == [{"nome": "Mercado Sol", "municipio_uf": "OSASCO/SP",
                                      "pedidos": 2, "doacoes_recebidas": 2}]
    assert {a["tipo"] for a in dados["alertas"]} == {
        "PRAZO_PROXIMO", "META_ATINGIDA", "QUASE_COMPLETO"}
    assert len(dados["ultimas_doacoes"]) == 2
    assert all(c["origem"] == "pessoa" for c in dados["ultimas_doacoes"])
    assert all(s not in resposta.get_data(as_text=True) for s in
               ("sigilo@", "pessoa@", "52998224725", "11999999999"))


def test_rota_dashboard_entrega_html(monkeypatch, tmp_path):
    (tmp_path / "dashboard.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))
    resposta = app.test_client().get("/dashboard")
    assert resposta.status_code == 200
    assert b"Dashboard" in resposta.data
