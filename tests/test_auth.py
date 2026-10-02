import os

import pytest
from flask import Flask
from sqlalchemy import create_engine, inspect, text


os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from Auth import _falhas, configurar_chave_secreta  # noqa: E402
from migracoes import aplicar_migracoes  # noqa: E402
from models import Doador, Estabelecimento, db  # noqa: E402


EMPRESA_CNPJ = "47508411000156"
CPF = "52998224725"
SENHA = "Segredo123"


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    _falhas.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    _falhas.clear()


@pytest.fixture
def cliente():
    return app.test_client()


def empresa_consultada():
    return {
        "cnpj": EMPRESA_CNPJ, "cnpj_formatado": "47.508.411/0001-56",
        "razao_social": "MERCADO REAL", "nome_fantasia": "Mercado Real",
        "situacao": "ATIVA", "ativo": True,
        "cnae_principal": {"codigo": "4711301", "descricao": "Hipermercados"},
        "atividades_alimentares": [{"codigo": "4711301", "descricao": "Hipermercados",
                                   "categoria": "Supermercados e mercearias"}],
        "relacionado_alimentacao": True,
        "endereco": {"logradouro": "AV EXEMPLO", "numero": "10", "complemento": "",
                     "bairro": "CENTRO", "municipio": "BARUERI", "uf": "SP", "cep": "06400000"},
        "email": None, "telefone": "(11) 4004-0010", "fonte": "teste",
    }


def cadastrar_empresa(cliente, monkeypatch):
    monkeypatch.setattr("Cadastro.consultar_cnpj", lambda _: empresa_consultada())
    return cliente.post("/reconecta/cadastro/empresa", json={
        "cnpj": EMPRESA_CNPJ, "email": "empresa@exemplo.com",
        "telefone": "11999998888", "senha": SENHA,
    })


def cadastrar_doador(cliente):
    return cliente.post("/reconecta/cadastro/doador", json={
        "nome": "Maria Souza", "cpf": CPF, "email": "maria@exemplo.com",
        "telefone": "11999998888", "senha": SENHA,
    })


def test_senha_fraca_e_obrigatoria(cliente, monkeypatch):
    monkeypatch.setattr("Cadastro.consultar_cnpj", lambda _: pytest.fail("não consulta com senha inválida"))
    for senha in (None, "abcdefgh", "12345678", "Ab1"):
        resposta = cliente.post("/reconecta/cadastro/empresa", json={
            "cnpj": EMPRESA_CNPJ, "email": "empresa@exemplo.com",
            "telefone": "11999998888", "senha": senha,
        })
        assert resposta.status_code == 400
        assert resposta.json["codigo"] == "DADOS_INVALIDOS"
        assert "senha" in resposta.json["campos"]
    doador = cliente.post("/reconecta/cadastro/doador", json={
        "nome": "Maria Souza", "cpf": CPF, "email": "maria@exemplo.com",
        "telefone": "11999998888", "senha": "semnumeros",
    })
    assert doador.status_code == 400
    assert "senha" in doador.json["campos"]


def test_empresa_cadastro_login_automatico_e_por_email_cnpj(cliente, monkeypatch):
    criado = cadastrar_empresa(cliente, monkeypatch)
    assert criado.status_code == 201
    assert "HttpOnly" in criado.headers["Set-Cookie"]
    assert "SameSite=Lax" in criado.headers["Set-Cookie"]
    with app.app_context():
        empresa = Estabelecimento.query.one()
        assert empresa.senha_hash != SENHA
        assert empresa.senha_hash
    me = cliente.get("/reconecta/auth/me")
    assert me.status_code == 200
    assert me.json["tipo"] == "empresa"
    assert me.json["cnpj_formatado"] == "47.508.411/0001-56"
    assert "senha_hash" not in me.json
    assert cliente.post("/reconecta/auth/logout").status_code == 204
    assert cliente.get("/reconecta/auth/me").json["codigo"] == "NAO_AUTENTICADO"
    for identificador in ("EMPRESA@EXEMPLO.COM", "47.508.411/0001-56"):
        resposta = cliente.post("/reconecta/auth/login", json={
            "identificador": identificador, "senha": SENHA,
        })
        assert resposta.status_code == 200
        assert resposta.json["usuario"]["tipo"] == "empresa"
        assert cliente.post("/reconecta/auth/logout").status_code == 204


def test_doador_cadastro_login_cpf_mascarado(cliente):
    criado = cadastrar_doador(cliente)
    assert criado.status_code == 201
    assert cliente.get("/reconecta/auth/me").json["cpf_formatado"] == "***.982.247-**"
    with app.app_context():
        assert Doador.query.one().senha_hash != SENHA
    cliente.post("/reconecta/auth/logout")
    resposta = cliente.post("/reconecta/auth/login", json={
        "identificador": "529.982.247-25", "senha": SENHA,
    })
    assert resposta.status_code == 200
    assert resposta.json["usuario"]["tipo"] == "doador"
    assert "cpf" not in resposta.json["usuario"]


def test_credenciais_invalidas_indistinguiveis_e_conta_antiga(cliente):
    with app.app_context():
        db.session.add(Doador(nome="Conta Antiga", cpf=CPF, email="antiga@exemplo.com",
                              telefone="11999998888"))
        db.session.commit()
    respostas = [cliente.post("/reconecta/auth/login", json={
        "identificador": identificador, "senha": "Errada123",
    }) for identificador in ("antiga@exemplo.com", "naoexiste@exemplo.com")]
    assert [resposta.status_code for resposta in respostas] == [401, 401]
    assert respostas[0].json == respostas[1].json
    assert respostas[0].json["codigo"] == "CREDENCIAIS_INVALIDAS"
    assert cliente.get("/reconecta/auth/me").status_code == 401


def test_bloqueio_na_sexta_falha_por_identificador(cliente, monkeypatch):
    cadastrar_empresa(cliente, monkeypatch)
    cliente.post("/reconecta/auth/logout")
    for indice in range(5):
        identificador = "47.508.411/0001-56" if indice % 2 else EMPRESA_CNPJ
        assert cliente.post("/reconecta/auth/login", json={
            "identificador": identificador, "senha": "Errada123",
        }).status_code == 401
    bloqueado = cliente.post("/reconecta/auth/login", json={
        "identificador": EMPRESA_CNPJ, "senha": SENHA,
    })
    assert bloqueado.status_code == 429
    assert bloqueado.json["codigo"] == "MUITAS_TENTATIVAS"


def test_migracao_de_tabelas_antigas_idempotente(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'antigo.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
        conexao.execute(text("CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome VARCHAR(100))"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    inspector = inspect(engine)
    for tabela in ("estabelecimentos", "doadores"):
        assert sum(coluna["name"] == "senha_hash" for coluna in inspector.get_columns(tabela)) == 1


def test_chave_secreta_local_persiste(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    primeiro = Flask("teste1", instance_path=str(tmp_path))
    configurar_chave_secreta(primeiro)
    segundo = Flask("teste2", instance_path=str(tmp_path))
    configurar_chave_secreta(segundo)
    assert primeiro.secret_key == segundo.secret_key
    assert len(primeiro.secret_key) >= 64
