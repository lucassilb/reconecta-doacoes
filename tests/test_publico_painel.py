import os
from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash


os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from Auth import _falhas  # noqa: E402
from fuso import iso_prazo  # noqa: E402
from models import Doacao, Doador, Estabelecimento, Instituicao, ItemDoacao, Reserva, db  # noqa: E402


SENHA = "Segredo123"
ADMIN_HEADERS = {"X-Admin-Token": "teste-admin"}


@pytest.fixture(autouse=True)
def banco(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_HEADERS["X-Admin-Token"])
    _falhas.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    _falhas.clear()


@pytest.fixture
def cliente():
    return app.test_client()


def criar_usuarios():
    with app.app_context():
        primeira = Estabelecimento(nome="Mercado Verde", cnpj="47508411000156",
                                   email="verde@exemplo.com", telefone="11999998888",
                                   endereco="AV CENTRAL, 12 - CENTRO, BARUERI/SP - 06400000",
                                   senha_hash=generate_password_hash(SENHA))
        segunda = Estabelecimento(nome="Mercado Azul", cnpj="06990590000123",
                                  email="azul@exemplo.com", telefone="11999997777",
                                  endereco="AV OUTRA, 10 - CENTRO, OSASCO/SP - 06000000",
                                  senha_hash=generate_password_hash(SENHA))
        doador = Doador(nome="Maria Souza", cpf="52998224725",
                        email="maria@exemplo.com", telefone="11999996666",
                        senha_hash=generate_password_hash(SENHA))
        db.session.add_all((primeira, segunda, doador))
        db.session.commit()
        return primeira.id, segunda.id


def entrar(cliente, email):
    resposta = cliente.post("/reconecta/auth/login", json={
        "identificador": email, "senha": SENHA,
    })
    assert resposta.status_code == 200


def corpo_doacao(dias=2):
    return {
        "data_limite_retirada": (datetime.now() + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M"),
        "itens": [{"nome": "Banana", "categoria": "Hortifrúti", "quantidade": 2.5,
                   "unidade_medida": "kg"}],
    }


def test_publico_filtra_status_prazo_privacidade_e_soma_kg(cliente):
    empresa_id, _ = criar_usuarios()
    with app.app_context():
        ativa = Doacao(estabelecimento_id=empresa_id, status="DISPONIVEL",
                       data_limite_retirada=datetime.now() + timedelta(days=2))
        vencida = Doacao(estabelecimento_id=empresa_id, status="DISPONIVEL",
                         data_limite_retirada=datetime.now() - timedelta(hours=1))
        reservada = Doacao(estabelecimento_id=empresa_id, status="RESERVADA",
                           data_limite_retirada=datetime.now() + timedelta(days=2))
        db.session.add_all((ativa, vencida, reservada))
        db.session.flush()
        for doacao, nome, quantidade, unidade in (
            (ativa, "Banana", 2.5, "kg"), (ativa, "Maçã", 500, "g"),
            (ativa, "Pão", 4, "unidade"), (vencida, "Velha", 7, "kg"),
            (reservada, "Reservada", 8, "kg"),
        ):
            db.session.add(ItemDoacao(doacao_id=doacao.id, nome=nome,
                                      categoria="Hortifrúti", quantidade=quantidade,
                                      unidade_medida=unidade))
        db.session.commit()
        ativa_id = ativa.id
    resumo = cliente.get("/reconecta/publico/resumo")
    assert resumo.status_code == 200
    assert resumo.json == {"empresas": 2, "doadores": 1, "instituicoes": 0,
                           "doacoes_disponiveis": 1,
                           "itens_disponiveis": 3, "kg_disponiveis": 3.0,
                           "doacoes_recebidas": 0}
    resposta = cliente.get("/reconecta/publico/doacoes?limite=8")
    assert resposta.status_code == 200
    assert len(resposta.json) == 1
    assert resposta.json[0]["id"] == ativa_id
    assert resposta.json[0]["empresa"] == {"nome": "Mercado Verde", "municipio_uf": "BARUERI/SP"}
    assert [item["nome"] for item in resposta.json[0]["itens"]] == ["Banana", "Maçã", "Pão"]
    assert [item["faltam"] for item in resposta.json[0]["itens"]] == [2.5, 500, 4]
    assert "email" not in resposta.get_data(as_text=True)
    assert "cnpj" not in resposta.get_data(as_text=True)
    opcoes = cliente.get("/reconecta/publico/opcoes")
    assert opcoes.json["unidades"] == ["kg", "g", "L", "unidade", "pacote", "caixa"]
    assert "Hortifrúti" in opcoes.json["categorias"]


def test_resumo_conta_instituicoes_sem_alterar_os_outros_contadores(cliente):
    with app.app_context():
        db.session.add_all([
            Instituicao(nome="ONG Vida", cnpj="12345678000190", email="vida@exemplo.com",
                        telefone="11999995555", endereco="BARUERI/SP"),
            Instituicao(nome="Banco de Alimentos", cnpj="98765432000110",
                        email="banco@exemplo.com", telefone="11999994444",
                        endereco="OSASCO/SP"),
        ])
        db.session.commit()

    resposta = cliente.get("/reconecta/publico/resumo")
    assert resposta.status_code == 200
    assert resposta.json == {"empresas": 0, "doadores": 0, "instituicoes": 2,
                            "doacoes_disponiveis": 0, "itens_disponiveis": 0,
                            "kg_disponiveis": 0.0, "doacoes_recebidas": 0}


def test_painel_exige_login_e_empresa_cria_doacao_com_itens(cliente):
    empresa_id, _ = criar_usuarios()
    assert cliente.get("/reconecta/painel/doacoes").status_code == 401
    assert cliente.post("/reconecta/painel/doacoes", json=corpo_doacao()).status_code == 401
    entrar(cliente, "maria@exemplo.com")
    assert cliente.get("/reconecta/painel/doacoes").status_code == 403
    recusada = cliente.post("/reconecta/painel/doacoes", json=corpo_doacao())
    assert recusada.status_code == 403
    assert recusada.json["codigo"] == "APENAS_EMPRESAS"
    cliente.post("/reconecta/auth/logout")
    entrar(cliente, "verde@exemplo.com")
    criado = cliente.post("/reconecta/painel/doacoes", json=corpo_doacao())
    assert criado.status_code == 201
    assert criado.json["status"] == "DISPONIVEL"
    assert criado.json["itens"][0]["nome"] == "Banana"
    assert criado.json["empresa"]["municipio_uf"] == "BARUERI/SP"
    assert criado.json["itens"][0]["recebido"] == 0
    assert "retirada" not in criado.json
    with app.app_context():
        assert Doacao.query.one().estabelecimento_id == empresa_id
        assert ItemDoacao.query.count() == 1
        assert ItemDoacao.query.one().validade is None
    lista = cliente.get("/reconecta/painel/doacoes")
    assert lista.status_code == 200
    assert [doacao["id"] for doacao in lista.json] == [criado.json["id"]]
    assert cliente.get("/reconecta/publico/doacoes").json[0]["id"] == criado.json["id"]


def test_doador_nao_publica_pedido_e_nao_ve_endereco_da_empresa(cliente):
    criar_usuarios()
    entrar(cliente, "verde@exemplo.com")
    empresa = cliente.post("/reconecta/painel/doacoes", json={
        **corpo_doacao(), "retirada": {"endereco": "IGNORAR", "municipio": "IGNORAR", "uf": "ZZ"}
    })
    assert empresa.status_code == 201
    assert "retirada" not in empresa.json
    cliente.post("/reconecta/auth/logout")
    entrar(cliente, "maria@exemplo.com")
    corpo = corpo_doacao()
    corpo["retirada"] = {"endereco": "Rua das Flores, 123", "municipio": "Barueri", "uf": "SP"}
    assert cliente.post("/reconecta/painel/doacoes", json=corpo).status_code == 403
    assert cliente.get("/reconecta/painel/doacoes").status_code == 403
    assert cliente.delete(f"/reconecta/painel/doacoes/{empresa.json['id']}").status_code == 403
    publico = cliente.get("/reconecta/publico/doacoes").json
    assert [item["id"] for item in publico] == [empresa.json["id"]]
    for privado in ("AV CENTRAL", "Rua das Flores", "Souza", "52998224725", "maria@exemplo.com"):
        assert privado not in str(publico)
    assert cliente.get("/reconecta/publico/resumo").json["doacoes_disponiveis"] == 1
    cliente.post("/reconecta/auth/logout")
    entrar(cliente, "verde@exemplo.com")
    assert [item["id"] for item in cliente.get("/reconecta/painel/doacoes").json] == [empresa.json["id"]]


@pytest.mark.parametrize("alteracao,campo", [
    ({"itens": []}, "itens"),
    ({"itens[0].quantidade": 0}, "itens[0].quantidade"),
    ({"itens[0].quantidade": 0.001}, "itens[0].quantidade"),
    ({"itens[0].nome": ""}, "itens[0].nome"),
    ({"itens[0].categoria": "Inventada"}, "itens[0].categoria"),
    ({"itens[0].unidade_medida": "litro"}, "itens[0].unidade_medida"),
])
def test_painel_recusa_campos_invalidos_sem_gravar(cliente, alteracao, campo):
    criar_usuarios()
    entrar(cliente, "verde@exemplo.com")
    corpo = corpo_doacao()
    for caminho, valor in alteracao.items():
        if caminho.startswith("itens[0]."):
            corpo["itens"][0][caminho.split(".", 1)[1]] = valor
        else:
            corpo[caminho] = valor
    resposta = cliente.post("/reconecta/painel/doacoes", json=corpo)
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "DADOS_INVALIDOS"
    assert campo in resposta.json["campos"]
    with app.app_context():
        assert Doacao.query.count() == 0
        assert ItemDoacao.query.count() == 0


def test_limite_passado_e_remocao_alheia_ou_reservada(cliente):
    primeiro_id, segundo_id = criar_usuarios()
    entrar(cliente, "verde@exemplo.com")
    corpo = corpo_doacao(dias=-1)
    invalido = cliente.post("/reconecta/painel/doacoes", json=corpo)
    assert invalido.status_code == 400
    assert "receber_ate" in invalido.json["campos"]
    with app.app_context():
        propria = Doacao(estabelecimento_id=primeiro_id, status="DISPONIVEL",
                         data_limite_retirada=datetime.now() + timedelta(days=2))
        alheia = Doacao(estabelecimento_id=segundo_id, status="DISPONIVEL",
                        data_limite_retirada=datetime.now() + timedelta(days=2))
        reservada = Doacao(estabelecimento_id=primeiro_id, status="RESERVADA",
                           data_limite_retirada=datetime.now() + timedelta(days=2))
        com_reserva = Doacao(estabelecimento_id=primeiro_id, status="DISPONIVEL",
                             data_limite_retirada=datetime.now() + timedelta(days=2))
        instituicao = Instituicao(nome="ONG Vida", cnpj="12345678000190", email="ong@exemplo.com",
                                  telefone="11999995555", endereco="BARUERI/SP")
        db.session.add_all((propria, alheia, reservada, com_reserva, instituicao))
        db.session.flush()
        db.session.add(Reserva(doacao_id=com_reserva.id, instituicao_id=instituicao.id))
        db.session.commit()
        ids = propria.id, alheia.id, reservada.id, com_reserva.id
    assert cliente.delete(f"/reconecta/painel/doacoes/{ids[1]}").status_code == 404
    bloqueada = cliente.delete(f"/reconecta/painel/doacoes/{ids[2]}")
    assert bloqueada.status_code == 409
    assert bloqueada.json["codigo"] == "PEDIDO_NAO_REMOVIVEL"
    assert cliente.delete(f"/reconecta/painel/doacoes/{ids[3]}").status_code == 409
    assert cliente.delete(f"/reconecta/painel/doacoes/{ids[0]}").status_code == 204
    with app.app_context():
        assert db.session.get(Doacao, ids[0]) is None
    assert cliente.get("/swagger.json").status_code == 200
    assert cliente.get("/reconecta/estabelecimentos/").status_code == 200
    assert cliente.get("/reconecta/doacoes/").status_code == 200


def test_crud_original_doacoes_mantem_campos_respostas_e_swagger(cliente):
    primeira_id, segunda_id = criar_usuarios()
    prazo = (datetime.now() + timedelta(days=2)).isoformat(timespec="seconds")
    novo = cliente.post("/reconecta/doacoes/", json={
        "estabelecimento_id": primeira_id, "data_limite_retirada": prazo},
        headers=ADMIN_HEADERS)
    assert novo.status_code == 201
    assert set(novo.json) == {"id", "estabelecimento_id", "data_cadastro",
                             "data_limite_retirada", "status"}
    assert novo.json["estabelecimento_id"] == primeira_id
    assert novo.json["data_limite_retirada"] == iso_prazo(datetime.fromisoformat(prazo))
    assert novo.json["status"] == "DISPONIVEL"
    identificador = novo.json["id"]
    assert cliente.get("/reconecta/doacoes/").json == [novo.json]
    assert cliente.get(f"/reconecta/doacoes/{identificador}").json == novo.json
    outro_prazo = (datetime.now() + timedelta(days=4)).isoformat(timespec="seconds")
    alterado = cliente.put(f"/reconecta/doacoes/{identificador}", json={
        "estabelecimento_id": segunda_id, "data_limite_retirada": outro_prazo,
        "status": "RESERVADA"}, headers=ADMIN_HEADERS)
    assert alterado.status_code == 200
    assert alterado.json == {**novo.json, "estabelecimento_id": segunda_id,
                            "data_limite_retirada": iso_prazo(datetime.fromisoformat(outro_prazo)),
                            "status": "RESERVADA"}
    assert cliente.delete(f"/reconecta/doacoes/{identificador}", headers=ADMIN_HEADERS).json == {
        "message": "Doação deletada com sucesso"}
    assert cliente.get(f"/reconecta/doacoes/{identificador}").status_code == 404
    swagger = cliente.get("/swagger.json").json["paths"]
    assert {"get", "post"} <= set(swagger["/reconecta/doacoes/"])
    assert {"get", "put", "delete"} <= set(swagger["/reconecta/doacoes/{id}"])


@pytest.mark.parametrize("metodo", ["get", "put", "delete"])
def test_crud_original_doacoes_id_ausente_retorna_404(cliente, metodo):
    resposta = getattr(cliente, metodo)(
        "/reconecta/doacoes/999", headers=ADMIN_HEADERS,
        **({"json": {"status": "RESERVADA"}} if metodo == "put" else {}))
    assert resposta.status_code == 404
    assert resposta.json == {"message": "Doação não encontrada"}
