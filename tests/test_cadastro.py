import os
import sys
import types

import pytest
import requests


os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from cnpj_service import _cache  # noqa: E402
from models import Doador, Estabelecimento, db  # noqa: E402


PAO = "47508411000156"
GOOGLE = "06990590000123"
BAIXADA = "19131243000197"


class Resposta:
    def __init__(self, status=200, dados=None):
        self.status_code = status
        self.dados = dados or {}

    def json(self):
        return self.dados

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def empresa(cnpj=PAO, situacao="ATIVA", principal=4789099, secundarios=None):
    return {
        "cnpj": cnpj,
        "razao_social": "COMPANHIA BRASILEIRA DE DISTRIBUICAO",
        "nome_fantasia": "",
        "situacao_cadastral": 2 if situacao == "ATIVA" else 8,
        "descricao_situacao_cadastral": situacao,
        "cnae_fiscal": principal,
        "cnae_fiscal_descricao": "Comércio varejista de outros produtos",
        "cnaes_secundarios": secundarios if secundarios is not None else [
            {"codigo": 4711301, "descricao": "Hipermercados"}],
        "logradouro": "AV BRIGADEIRO LUIS ANTONIO", "numero": "3126",
        "bairro": "JARDIM PAULISTA", "municipio": "SAO PAULO", "uf": "SP",
        "cep": "01402000", "ddd_telefone_1": "1140040010",
    }


def classificar_atividades_stub(cnaes):
    return [{**item, "categoria": "Supermercados e mercearias"}
            for item in cnaes if item["codigo"] == "4711301"]


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    app.config["TESTING"] = True
    _cache.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()

    # A Frente C entrega este módulo; o teste usa só a interface combinada.
    monkeypatch.setitem(sys.modules, "cnae_alimentos", types.SimpleNamespace(
        classificar_atividades=classificar_atividades_stub))
    yield
    _cache.clear()


@pytest.fixture
def cliente():
    return app.test_client()


def mock_brasilapi(monkeypatch, dados=None):
    chamadas = []

    def get(url, timeout):
        chamadas.append((url, timeout))
        return Resposta(dados=dados or empresa())

    monkeypatch.setattr("cnpj_service.requests.get", get)
    return chamadas


def test_cnpj_invalido_antes_da_rede(cliente, monkeypatch):
    monkeypatch.setattr("cnpj_service.requests.get", lambda *args, **kwargs: pytest.fail("não deve consultar API"))
    resposta = cliente.get("/reconecta/cadastro/cnpj/11.111.111/1111-11")
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "CNPJ_INVALIDO"


def test_cnpj_nao_encontrado(cliente, monkeypatch):
    monkeypatch.setattr("cnpj_service.requests.get", lambda *args, **kwargs: Resposta(404))
    resposta = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    assert resposta.status_code == 404
    assert resposta.json["codigo"] == "CNPJ_NAO_ENCONTRADO"


def test_inativo_e_tecnologia_recusados(cliente, monkeypatch):
    mock_brasilapi(monkeypatch, empresa(cnpj=BAIXADA, situacao="BAIXADA"))
    inativo = cliente.get(f"/reconecta/cadastro/cnpj/{BAIXADA}")
    assert inativo.status_code == 200
    assert inativo.json["apto"] is False
    assert inativo.json["motivos"][0]["codigo"] == "CNPJ_INATIVO"
    assert "BAIXADA" in inativo.json["motivos"][0]["mensagem"]

    mock_brasilapi(monkeypatch, empresa(cnpj=GOOGLE, principal=6319400, secundarios=[]))
    tecnologia = cliente.get(f"/reconecta/cadastro/cnpj/{GOOGLE}")
    assert tecnologia.status_code == 200
    assert tecnologia.json["ativo"] is True
    assert tecnologia.json["apto"] is False
    assert tecnologia.json["motivos"][0]["codigo"] == "SEM_RELACAO_ALIMENTAR"


def test_atividade_alimentar_secundaria_e_cache(cliente, monkeypatch):
    chamadas = mock_brasilapi(monkeypatch)
    primeira = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    segunda = cliente.get(f"/reconecta/cadastro/cnpj/47.508.411/0001-56")
    assert primeira.status_code == segunda.status_code == 200
    assert primeira.json["cnae_principal"]["codigo"] == "4789099"
    assert primeira.json["atividades_alimentares"][0]["codigo"] == "4711301"
    assert primeira.json["apto"] is True
    assert primeira.json["fonte"] == "brasilapi"
    assert len(chamadas) == 1
    assert chamadas[0][1] == 8


def test_fallback_opencnpj(cliente, monkeypatch):
    chamadas = []

    def get(url, timeout):
        chamadas.append(url)
        if "brasilapi" in url:
            raise requests.Timeout()
        return Resposta(dados={
            "razao_social": "MERCADO TESTE", "situacao_cadastral": "Ativa",
            "cnae_principal": "4789099", "cnaes_secundarios": ["4711301"],
            "cnaes": [{"codigo": "4711301", "descricao": "Hipermercados"}],
        })

    monkeypatch.setattr("cnpj_service.requests.get", get)
    resposta = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "opencnpj"
    assert resposta.json["apto"] is True
    assert len(chamadas) == 2


def test_fallback_cnpjws(cliente, monkeypatch):
    chamadas = []

    def get(url, timeout):
        chamadas.append(url)
        if "cnpj.ws" not in url:
            raise requests.Timeout()
        return Resposta(dados={
            "razao_social": "MERCADO TESTE", "estabelecimento": {
                "situacao_cadastral": "Ativa",
                "atividade_principal": {"id": 4789099, "descricao": "Outros"},
                "atividades_secundarias": [{"id": 4711301, "descricao": "Hipermercados"}],
            },
        })

    monkeypatch.setattr("cnpj_service.requests.get", get)
    resposta = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "cnpjws"
    assert resposta.json["apto"] is True
    assert len(chamadas) == 3


def test_todas_fontes_falham(cliente, monkeypatch):
    chamadas = []

    def get(url, timeout):
        chamadas.append(url)
        raise requests.Timeout()

    monkeypatch.setattr("cnpj_service.requests.get", get)
    resposta = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    assert resposta.status_code == 503
    assert resposta.json["codigo"] == "CONSULTA_INDISPONIVEL"
    assert len(chamadas) == 3


def test_empresa_grava_digitos_e_recusa_duplicado(cliente, monkeypatch):
    mock_brasilapi(monkeypatch)
    corpo = {"cnpj": "47.508.411/0001-56", "email": "Empresa@Exemplo.com", "telefone": "(11) 4004-0010", "senha": "Senha1234"}
    resposta = cliente.post("/reconecta/cadastro/empresa", json=corpo)
    assert resposta.status_code == 201
    assert resposta.json["cnpj"] == PAO
    assert resposta.json["nome"] == "COMPANHIA BRASILEIRA DE DISTRIBUICAO"
    with app.app_context():
        assert Estabelecimento.query.one().cnpj == PAO
    duplicado = cliente.post("/reconecta/cadastro/empresa", json=corpo)
    assert duplicado.status_code == 409
    assert duplicado.json["codigo"] == "CNPJ_JA_CADASTRADO"
    consulta = cliente.get(f"/reconecta/cadastro/cnpj/{PAO}")
    assert consulta.json["ja_cadastrado"] is True
    assert consulta.json["apto"] is False


def test_empresa_nao_apta_e_email_duplicado(cliente, monkeypatch):
    mock_brasilapi(monkeypatch, empresa(principal=6319400, secundarios=[]))
    corpo = {"cnpj": PAO, "email": "empresa@exemplo.com", "telefone": "11999998888", "senha": "Senha1234"}
    nao_apta = cliente.post("/reconecta/cadastro/empresa", json=corpo)
    assert nao_apta.status_code == 422
    assert nao_apta.json["codigo"] == "EMPRESA_NAO_APTA"
    assert nao_apta.json["motivos"][0]["codigo"] == "SEM_RELACAO_ALIMENTAR"
    with app.app_context():
        assert Estabelecimento.query.count() == 0

    _cache.clear()
    mock_brasilapi(monkeypatch)
    with app.app_context():
        db.session.add(Doador(nome="Maria Souza", cpf="52998224725", email="empresa@exemplo.com", telefone="11999998888"))
        db.session.commit()
    duplicado = cliente.post("/reconecta/cadastro/empresa", json=corpo)
    assert duplicado.status_code == 409
    assert duplicado.json["codigo"] == "EMAIL_JA_CADASTRADO"


def test_doador_valido_invalido_e_duplicados(cliente):
    corpo = {"nome": "Maria Souza", "cpf": "529.982.247-25", "email": "Maria@Exemplo.com", "telefone": "(11) 99999-8888", "senha": "Senha1234"}
    criado = cliente.post("/reconecta/cadastro/doador", json=corpo)
    assert criado.status_code == 201
    assert criado.json["cpf_formatado"] == "***.982.247-**"
    assert "cpf" not in criado.json
    with app.app_context():
        assert Doador.query.one().cpf == "52998224725"
    repetido = cliente.post("/reconecta/cadastro/doador", json=corpo)
    assert repetido.status_code == 409
    assert repetido.json["codigo"] == "CPF_JA_CADASTRADO"
    outro_cpf = cliente.post("/reconecta/cadastro/doador", json={**corpo, "cpf": "111.444.777-35"})
    assert outro_cpf.status_code == 409
    assert outro_cpf.json["codigo"] == "EMAIL_JA_CADASTRADO"
    invalido = cliente.post("/reconecta/cadastro/doador", json={**corpo, "cpf": "111.111.111-11"})
    assert invalido.status_code == 400
    assert "cpf" in invalido.json["campos"]


def test_validacoes_e_rotas_existentes(cliente, monkeypatch, tmp_path):
    invalido = cliente.post("/reconecta/cadastro/empresa", json={"cnpj": PAO, "email": "ruim", "telefone": "123", "senha": "Senha1234"})
    assert invalido.status_code == 400
    assert set(invalido.json["campos"]) == {"email", "telefone"}
    assert cliente.get("/swagger").status_code == 200
    assert cliente.get("/swagger.json").status_code == 200
    assert cliente.get("/reconecta/estabelecimentos/").status_code == 200
    assert cliente.get("/reconecta/instituicoes/").status_code == 200
    assert cliente.get("/reconecta/doacoes/").status_code == 200
    for pagina in ("index", "sobre", "cadastro", "entrar", "painel", "doacao"):
        (tmp_path / f"{pagina}.html").write_text(f"<h1>{pagina}</h1>", encoding="utf-8")
    monkeypatch.setattr(app, "static_folder", str(tmp_path))
    raiz = cliente.get("/")
    assert raiz.status_code == 200
    assert b"index" in raiz.data
    for rota in ("/sobre", "/cadastro", "/entrar", "/painel", "/doacoes/1"):
        assert cliente.get(rota).status_code == 200
