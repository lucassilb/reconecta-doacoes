"""Autorização, privacidade e regras dos CRUDs legados do CP1."""

import os
from datetime import datetime, timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from models import Doacao, Estabelecimento, Instituicao, ItemDoacao, Reserva, db  # noqa: E402


TOKEN = "token-administrativo-de-prova"
HEADERS = {"X-Admin-Token": TOKEN}
EMPRESA_CNPJ = "47508411000156"
OUTRO_CNPJ = "06990590000123"
INSTITUICAO_CNPJ = "19131243000197"


@pytest.fixture(autouse=True)
def banco(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


@pytest.fixture
def cliente():
    return app.test_client()


def empresa(**mudancas):
    return {"nome": "Mercado", "cnpj": EMPRESA_CNPJ,
            "email": "mercado@exemplo.com", "telefone": "(11) 4004-0010",
            "endereco": "Rua A", **mudancas}


def instituicao(**mudancas):
    return {"nome": "ONG", "cnpj": INSTITUICAO_CNPJ,
            "email": "ong@exemplo.com", "telefone": "(11) 99999-8888",
            "endereco": "Rua B", **mudancas}


def consulta_apta(monkeypatch, *, ativo=True, alimentar=True):
    def consultar(cnpj):
        return {"cnpj": cnpj, "ativo": ativo,
                "situacao": "ATIVA" if ativo else "BAIXADA",
                "relacionado_alimentacao": alimentar}
    monkeypatch.setattr("cnpj_service.consultar_cnpj", consultar)


@pytest.mark.parametrize("rota", ["estabelecimentos", "instituicoes", "doacoes"])
@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_escrita_cp1_exige_token_configurado_e_valido(cliente, monkeypatch, rota, metodo):
    url = f"/reconecta/{rota}/" if metodo == "post" else f"/reconecta/{rota}/1"
    chamar = getattr(cliente, metodo)
    kwargs = {"json": {}} if metodo != "delete" else {}
    desativado = chamar(url, **kwargs)
    assert desativado.status_code == 403
    assert desativado.json["codigo"] == "ADMIN_DESATIVADO"
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    for cabecalhos in ({}, {"X-Admin-Token": "errado"}):
        negado = chamar(url, headers=cabecalhos, **kwargs)
        assert negado.status_code == 401
        assert negado.json["codigo"] == "ADMIN_NAO_AUTORIZADO"


def test_casos_reais_cnpj_privacidade_e_delete_dependente(cliente, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    consulta_apta(monkeypatch)
    corpo = empresa(cnpj="123")
    invalido = cliente.post("/reconecta/estabelecimentos/", json=corpo, headers=HEADERS)
    assert invalido.status_code == 400
    assert invalido.json["codigo"] == "CNPJ_INVALIDO"
    with app.app_context():
        assert Estabelecimento.query.count() == 0

    criado = cliente.post("/reconecta/estabelecimentos/", json=empresa(
        cnpj="47.508.411/0001-56"), headers=HEADERS)
    assert criado.status_code == 201
    assert criado.json["cnpj"] == EMPRESA_CNPJ
    assert criado.json["telefone"] == "1140040010"
    identificador = criado.json["id"]
    with app.app_context():
        db.session.add(Doacao(estabelecimento_id=identificador,
                              data_limite_retirada=datetime.now() + timedelta(days=2)))
        db.session.add(Instituicao(**instituicao()))
        db.session.commit()

    for rota in ("estabelecimentos", "instituicoes"):
        publico = cliente.get(f"/reconecta/{rota}/").json[0]
        detalhe = cliente.get(f"/reconecta/{rota}/{publico['id']}").json
        assert set(publico) == set(detalhe) == {"id", "nome", "cnpj", "endereco"}
        assert publico["cnpj"].isdigit()
        completo = cliente.get(f"/reconecta/{rota}/", headers=HEADERS).json[0]
        assert {"email", "telefone"} <= set(completo)
        assert cliente.get(f"/reconecta/{rota}/{publico['id']}", headers=HEADERS).json == completo
    assert cliente.delete(f"/reconecta/estabelecimentos/{identificador}").status_code == 401
    dependente = cliente.delete(f"/reconecta/estabelecimentos/{identificador}",
                                headers=HEADERS)
    assert dependente.status_code == 409
    assert dependente.json["codigo"] == "REGISTROS_DEPENDENTES"


def test_empresa_rejeita_inativa_sem_cnae_e_duplicados(cliente, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    consulta_apta(monkeypatch, ativo=False, alimentar=False)
    resposta = cliente.post("/reconecta/estabelecimentos/", json=empresa(), headers=HEADERS)
    assert resposta.status_code == 422
    assert {motivo["codigo"] for motivo in resposta.json["motivos"]} == {
        "CNPJ_INATIVO", "SEM_RELACAO_ALIMENTAR"}
    consulta_apta(monkeypatch)
    criado = cliente.post("/reconecta/estabelecimentos/", json=empresa(), headers=HEADERS)
    assert criado.status_code == 201
    troca_invalida = cliente.put(f"/reconecta/estabelecimentos/{criado.json['id']}",
                                json={"cnpj": "123"}, headers=HEADERS)
    assert troca_invalida.status_code == 400
    assert troca_invalida.json["codigo"] == "CNPJ_INVALIDO"
    consulta_apta(monkeypatch, ativo=False, alimentar=True)
    troca_inativa = cliente.put(f"/reconecta/estabelecimentos/{criado.json['id']}",
                               json={"cnpj": OUTRO_CNPJ}, headers=HEADERS)
    assert troca_inativa.status_code == 422
    assert troca_inativa.json["codigo"] == "EMPRESA_NAO_APTA"
    consulta_apta(monkeypatch)
    duplicado_cnpj = cliente.post("/reconecta/estabelecimentos/", json=empresa(
        email="outro@exemplo.com"), headers=HEADERS)
    assert (duplicado_cnpj.status_code, duplicado_cnpj.json["codigo"]) == (409, "CNPJ_JA_CADASTRADO")
    duplicado_email = cliente.post("/reconecta/estabelecimentos/", json=empresa(
        cnpj=OUTRO_CNPJ), headers=HEADERS)
    assert (duplicado_email.status_code, duplicado_email.json["codigo"]) == (409, "EMAIL_JA_CADASTRADO")
    ruim = cliente.put(f"/reconecta/estabelecimentos/{criado.json['id']}",
                       json={"email": "ruim", "telefone": "123"}, headers=HEADERS)
    assert ruim.status_code == 400 and set(ruim.json["campos"]) == {"email", "telefone"}
    atualizado = cliente.put(f"/reconecta/estabelecimentos/{criado.json['id']}",
                             json={"nome": "Novo Mercado"}, headers=HEADERS)
    assert atualizado.status_code == 200 and atualizado.json["nome"] == "Novo Mercado"


def test_instituicao_exige_cnpj_ativo_mas_nao_cnae_alimentar(cliente, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    consulta_apta(monkeypatch, ativo=False, alimentar=False)
    inativa = cliente.post("/reconecta/instituicoes/", json=instituicao(), headers=HEADERS)
    assert inativa.status_code == 422 and inativa.json["codigo"] == "INSTITUICAO_NAO_APTA"
    consulta_apta(monkeypatch, alimentar=False)
    criada = cliente.post("/reconecta/instituicoes/", json=instituicao(), headers=HEADERS)
    assert criada.status_code == 201
    assert criada.json["cnpj"] == INSTITUICAO_CNPJ
    duplicada = cliente.post("/reconecta/instituicoes/", json=instituicao(), headers=HEADERS)
    assert duplicada.status_code == 409
    troca_invalida = cliente.put(f"/reconecta/instituicoes/{criada.json['id']}",
                                json={"cnpj": "123"}, headers=HEADERS)
    assert troca_invalida.status_code == 400
    assert troca_invalida.json["codigo"] == "CNPJ_INVALIDO"
    atualizada = cliente.put(f"/reconecta/instituicoes/{criada.json['id']}",
                             json={"nome": "ONG Atualizada"}, headers=HEADERS)
    assert atualizada.status_code == 200 and atualizada.json["nome"] == "ONG Atualizada"
    with app.app_context():
        empresa_modelo = Estabelecimento(**empresa())
        db.session.add(empresa_modelo)
        db.session.flush()
        doacao = Doacao(estabelecimento_id=empresa_modelo.id,
                        data_limite_retirada=datetime.now() + timedelta(days=2))
        db.session.add(doacao)
        db.session.flush()
        db.session.add(Reserva(doacao_id=doacao.id, instituicao_id=criada.json["id"]))
        db.session.commit()
    dependente = cliente.delete(f"/reconecta/instituicoes/{criada.json['id']}",
                                headers=HEADERS)
    assert dependente.status_code == 409
    assert dependente.json["codigo"] == "REGISTROS_DEPENDENTES"


def test_doacao_valida_referencia_status_data_e_dependencias(cliente, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    prazo = (datetime.now() + timedelta(days=2)).isoformat(timespec="seconds")
    inexistente = cliente.post("/reconecta/doacoes/", json={
        "estabelecimento_id": 999, "data_limite_retirada": prazo}, headers=HEADERS)
    assert inexistente.status_code == 400
    assert "estabelecimento_id" in inexistente.json["campos"]
    with app.app_context():
        db.session.add(Estabelecimento(**empresa()))
        db.session.commit()
        empresa_id = Estabelecimento.query.one().id
    for alteracao in ({"status": "INVENTADO"}, {"data_limite_retirada": "ontem"}):
        invalida = cliente.post("/reconecta/doacoes/", json={
            "estabelecimento_id": empresa_id, "data_limite_retirada": prazo,
            **alteracao}, headers=HEADERS)
        assert invalida.status_code == 400
    criada = cliente.post("/reconecta/doacoes/", json={
        "estabelecimento_id": empresa_id, "data_limite_retirada": prazo}, headers=HEADERS)
    assert criada.status_code == 201
    with app.app_context():
        db.session.add(ItemDoacao(doacao_id=criada.json["id"], nome="Leite",
                                  categoria="Laticínios", quantidade=10,
                                  unidade_medida="unidade"))
        db.session.commit()
    dependente = cliente.delete(f"/reconecta/doacoes/{criada.json['id']}", headers=HEADERS)
    assert dependente.status_code == 409
    assert dependente.json["codigo"] == "REGISTROS_DEPENDENTES"


def test_swagger_documenta_token_somente_na_escrita(cliente):
    especificacao = cliente.get("/swagger.json").json
    assert especificacao["securityDefinitions"]["AdminToken"] == {
        "type": "apiKey", "in": "header", "name": "X-Admin-Token"}
    for rota in ("estabelecimentos", "instituicoes", "doacoes"):
        for caminho, metodos in ((f"/reconecta/{rota}/", ("post",)),
                                 (f"/reconecta/{rota}/{{id}}", ("put", "delete"))):
            for metodo in metodos:
                assert especificacao["paths"][caminho][metodo]["security"] == [{"AdminToken": []}]
            assert "security" not in especificacao["paths"][caminho]["get"]
