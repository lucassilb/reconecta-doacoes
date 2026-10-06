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


def test_perfil_exige_sessao_e_corpo_valido(cliente, monkeypatch):
    sem_sessao = cliente.put("/reconecta/auth/me", json={"telefone": "11988887777"})
    assert sem_sessao.status_code == 401
    assert sem_sessao.json["codigo"] == "NAO_AUTENTICADO"

    cadastrar_empresa(cliente, monkeypatch)
    for corpo in ({}, [], None):
        resposta = cliente.put("/reconecta/auth/me", json=corpo)
        assert resposta.status_code == 400
        assert resposta.json["codigo"] == "DADOS_INVALIDOS"
        assert resposta.json["campos"]
    for campo in ("cnpj", "cpf", "nome", "id", "endereco", "senha_hash"):
        resposta = cliente.put("/reconecta/auth/me", json={campo: "alterado"})
        assert resposta.status_code == 400
        assert campo in resposta.json["campos"]
    assert cliente.get("/reconecta/auth/me").json["telefone"] == "11999998888"


def test_empresa_edita_contatos_sem_mudar_dados_da_receita(cliente, monkeypatch):
    cadastrar_empresa(cliente, monkeypatch)
    original = cliente.get("/reconecta/auth/me").json
    resposta = cliente.put("/reconecta/auth/me", json={
        "email": "  NOVO@Exemplo.com ", "telefone": "(11) 98888-7777",
    })
    assert resposta.status_code == 200
    assert resposta.json == cliente.get("/reconecta/auth/me").json
    assert resposta.json["email"] == "novo@exemplo.com"
    assert resposta.json["telefone"] == "11988887777"
    for campo in ("id", "nome", "cnpj_formatado", "endereco"):
        assert resposta.json[campo] == original[campo]
    assert cliente.put("/reconecta/auth/me", json={
        "email": "NOVO@EXEMPLO.COM"}).status_code == 200


def test_doador_edita_nome_e_contatos(cliente):
    cadastrar_doador(cliente)
    resposta = cliente.put("/reconecta/auth/me", json={
        "nome": "  Maria Nova  ", "email": "  NOVA@Exemplo.com ",
        "telefone": "(11) 4004-0010",
    })
    assert resposta.status_code == 200
    assert resposta.json == cliente.get("/reconecta/auth/me").json
    assert (resposta.json["nome"], resposta.json["email"], resposta.json["telefone"]) == (
        "Maria Nova", "nova@exemplo.com", "1140040010")
    assert resposta.json["cpf_formatado"] == "***.982.247-**"
    for campo in ("cpf", "cnpj", "id"):
        invalido = cliente.put("/reconecta/auth/me", json={campo: "alterado"})
        assert invalido.status_code == 400
        assert campo in invalido.json["campos"]


@pytest.mark.parametrize("tipo", ["empresa", "doador"])
def test_perfil_valida_campos_e_preserva_estado_em_erro(cliente, monkeypatch, tipo):
    if tipo == "empresa":
        cadastrar_empresa(cliente, monkeypatch)
    else:
        cadastrar_doador(cliente)
    original = cliente.get("/reconecta/auth/me").json
    invalidos = {"email": "invalido", "telefone": "123", "nova_senha": "abcdefghi"}
    if tipo == "doador":
        invalidos["nome"] = " A "
    resposta = cliente.put("/reconecta/auth/me", json=invalidos)
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "DADOS_INVALIDOS"
    assert set(invalidos) <= set(resposta.json["campos"])
    assert "senha_atual" in resposta.json["campos"]
    assert cliente.get("/reconecta/auth/me").json == original


def test_perfil_aplica_limites_do_cadastro(cliente):
    cadastrar_doador(cliente)
    original = cliente.get("/reconecta/auth/me").json
    for campo, valor in (
        ("nome", "x" * 101),
        ("email", "x" * 90 + "@exemplo.com"),
        ("telefone", "119999988889"),
        ("nova_senha", "12345678"),
        ("nova_senha", "Ab12345"),
    ):
        corpo = {campo: valor, "senha_atual": SENHA} if campo == "nova_senha" else {campo: valor}
        resposta = cliente.put("/reconecta/auth/me", json=corpo)
        assert resposta.status_code == 400
        assert campo in resposta.json["campos"]
    misto = cliente.put("/reconecta/auth/me", json={
        "nome": "Maria Nova", "cpf": "11144477735"})
    assert misto.status_code == 400
    assert "cpf" in misto.json["campos"]
    assert cliente.get("/reconecta/auth/me").json == original


@pytest.mark.parametrize("tipo", ["empresa", "doador"])
def test_perfil_email_unico_entre_tipos(cliente, monkeypatch, tipo):
    cadastrar_empresa(cliente, monkeypatch)
    cliente.post("/reconecta/auth/logout")
    cadastrar_doador(cliente)
    if tipo == "empresa":
        cliente.post("/reconecta/auth/logout")
        login = cliente.post("/reconecta/auth/login", json={
            "identificador": "empresa@exemplo.com", "senha": SENHA})
        assert login.status_code == 200
        email_alheio = "MARIA@EXEMPLO.COM"
    else:
        email_alheio = "EMPRESA@EXEMPLO.COM"
    original = cliente.get("/reconecta/auth/me").json
    resposta = cliente.put("/reconecta/auth/me", json={
        "email": email_alheio, "telefone": "11988887777"})
    assert resposta.status_code == 409
    assert resposta.json["codigo"] == "EMAIL_JA_CADASTRADO"
    assert cliente.get("/reconecta/auth/me").json == original


@pytest.mark.parametrize("tipo", ["empresa", "doador"])
def test_perfil_troca_senha_mantem_sessao_e_login_novo(cliente, monkeypatch, tipo):
    if tipo == "empresa":
        cadastrar_empresa(cliente, monkeypatch)
        email = "empresa@exemplo.com"
    else:
        cadastrar_doador(cliente)
        email = "maria@exemplo.com"
    for corpo, campos in (
        ({"senha_atual": SENHA}, {"nova_senha"}),
        ({"nova_senha": "SenhaNova123"}, {"senha_atual"}),
        ({"senha_atual": "Errada123", "nova_senha": "SenhaNova123"}, {"senha_atual"}),
        ({"senha_atual": SENHA, "nova_senha": "semnumero"}, {"nova_senha"}),
    ):
        resposta = cliente.put("/reconecta/auth/me", json=corpo)
        assert resposta.status_code == 400
        assert resposta.json["codigo"] == "DADOS_INVALIDOS"
        assert campos <= set(resposta.json["campos"])
    sucesso = cliente.put("/reconecta/auth/me", json={
        "senha_atual": SENHA, "nova_senha": "SenhaNova123"})
    assert sucesso.status_code == 200
    assert sucesso.json == cliente.get("/reconecta/auth/me").json
    assert "senha_hash" not in sucesso.json
    assert cliente.post("/reconecta/auth/logout").status_code == 204
    antigo = cliente.post("/reconecta/auth/login", json={
        "identificador": email, "senha": SENHA})
    assert antigo.status_code == 401
    novo = cliente.post("/reconecta/auth/login", json={
        "identificador": email, "senha": "SenhaNova123"})
    assert novo.status_code == 200


def test_perfil_put_documentado_no_swagger(cliente):
    especificacao = cliente.get("/swagger.json").json
    operacao = especificacao["paths"]["/reconecta/auth/me"]["put"]
    assert operacao["responses"]["200"]["schema"]["$ref"] == "#/definitions/UsuarioAutenticado"
    assert {"400", "401", "409"} <= set(operacao["responses"])
    entrada = operacao["parameters"][0]["schema"]["$ref"]
    assert set(especificacao["definitions"][entrada.split("/")[-1]]["properties"]) == {
        "nome", "email", "telefone", "senha_atual", "nova_senha"}
