import os
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash


os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from Auth import _falhas  # noqa: E402
from models import Arrecadacao, Contribuicao, Doador, Estabelecimento, db  # noqa: E402


SENHA = "Segredo123"
FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"


@pytest.fixture(autouse=True)
def banco(tmp_path):
    instancia_anterior = app.instance_path
    app.instance_path = str(tmp_path)
    app.config["TESTING"] = True
    _falhas.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    with app.app_context():
        db.session.remove()
    app.instance_path = instancia_anterior
    _falhas.clear()


@pytest.fixture
def cliente():
    return app.test_client()


def usuarios():
    with app.app_context():
        db.session.add_all([
            Estabelecimento(nome="Mercado Verde", cnpj="47508411000156",
                            email="verde@exemplo.com", telefone="11999998888",
                            endereco="AV CENTRAL, 12 - CENTRO, BARUERI/SP - 06400000",
                            senha_hash=generate_password_hash(SENHA)),
            Estabelecimento(nome="Mercado Azul", cnpj="06990590000123",
                            email="azul@exemplo.com", telefone="11999997777",
                            endereco="AV OUTRA, 10 - CENTRO, OSASCO/SP - 06000000",
                            senha_hash=generate_password_hash(SENHA)),
            Doador(nome="Maria Souza", cpf="52998224725", email="maria@exemplo.com",
                   telefone="11999996666", senha_hash=generate_password_hash(SENHA)),
        ])
        db.session.commit()


def entrar(cliente, email):
    assert cliente.post("/reconecta/auth/login", json={
        "identificador": email, "senha": SENHA,
    }).status_code == 200


def sair(cliente):
    assert cliente.post("/reconecta/auth/logout").status_code == 204


def corpo_acao(inicio=0, fim=4):
    return {
        "titulo": "Campanha de alimentos", "descricao": "Recebemos alimentos para famílias locais.",
        "categorias": ["Hortifrúti", "Padaria"], "meta_descricao": "100 kg de alimentos",
        "data_inicio": (date.today() + timedelta(days=inicio)).isoformat(),
        "data_fim": (date.today() + timedelta(days=fim)).isoformat(),
    }


def criar_acao(cliente, **mudancas):
    resposta = cliente.post("/reconecta/arrecadacoes/", json={**corpo_acao(), **mudancas})
    assert resposta.status_code == 201, resposta.json
    return resposta.json


def contribuir(cliente, acao_id, *, foto=FOTO, nome="foto.jpg", **mudancas):
    dados = {
        "alimento": "Banana", "categoria": "Hortifrúti", "quantidade": "2.5",
        "unidade_medida": "kg", "validade": (date.today() + timedelta(days=3)).isoformat(),
        "dentro_validade": "sim", "embalagem_ok": "sim", "armazenado_ok": "sim",
        "nao_caseiro": "sim", **mudancas,
    }
    dados["foto"] = (BytesIO(foto), nome)
    return cliente.post(f"/reconecta/arrecadacoes/{acao_id}/contribuicoes",
                        data=dados, content_type="multipart/form-data")


def test_empresa_cria_doador_nao_e_lista_publica_preserva_privacidade(cliente):
    usuarios()
    assert cliente.post("/reconecta/arrecadacoes/", json=corpo_acao()).status_code == 401
    entrar(cliente, "maria@exemplo.com")
    recusa = cliente.post("/reconecta/arrecadacoes/", json=corpo_acao())
    assert recusa.status_code == 403
    assert recusa.json["codigo"] == "APENAS_EMPRESAS"
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    acao = criar_acao(cliente)
    assert acao["entrega"] == {"municipio_uf": "BARUERI/SP"}
    assert acao["pode_contribuir"] is False
    assert acao["motivo_bloqueio"] == "Esta é a sua própria ação"
    minhas = cliente.get("/reconecta/arrecadacoes/minhas")
    assert minhas.status_code == 200
    assert minhas.json[0]["contribuicoes"] == []
    assert minhas.json[0]["entrega_endereco"].startswith("AV CENTRAL")
    sair(cliente)
    publico = cliente.get("/reconecta/arrecadacoes/")
    assert publico.status_code == 200
    assert len(publico.json) == 1
    assert publico.json[0]["empresa"] == {"nome": "Mercado Verde", "municipio_uf": "BARUERI/SP"}
    for privado in ("47508411000156", "verde@exemplo.com", "AV CENTRAL"):
        assert privado not in publico.get_data(as_text=True)
    detalhe = cliente.get(f"/reconecta/arrecadacoes/{acao['id']}")
    assert detalhe.json["pode_contribuir"] is False
    assert detalhe.json["motivo_bloqueio"] == "Entre para doar"
    assert cliente.get("/swagger.json").status_code == 200


@pytest.mark.parametrize("mudanca,campo", [
    ({"titulo": "Oi"}, "titulo"),
    ({"categorias": []}, "categorias"),
    ({"categorias": ["Inventada"]}, "categorias"),
    ({"data_inicio": "2020-01-01"}, "data_inicio"),
    ({"data_fim": "2020-01-01"}, "data_fim"),
    ({"entrega_endereco": "Rua"}, "entrega_endereco"),
])
def test_acao_invalida_nao_grava(cliente, mudanca, campo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    resposta = cliente.post("/reconecta/arrecadacoes/", json={**corpo_acao(), **mudanca})
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "DADOS_INVALIDOS"
    assert campo in resposta.json["campos"]
    with app.app_context():
        assert Arrecadacao.query.count() == 0


def test_doador_contribui_foto_somente_para_ele_e_dona_da_acao(cliente):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    acao = criar_acao(cliente)
    assert contribuir(cliente, acao["id"]).status_code == 409
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, acao["id"])
    assert resposta.status_code == 201, resposta.json
    assert resposta.json["status"] == "ACEITA"
    assert resposta.json["entrega"]["endereco"].startswith("AV CENTRAL")
    contribuicao_id = resposta.json["id"]
    minhas = cliente.get("/reconecta/arrecadacoes/minhas-contribuicoes")
    assert [item["id"] for item in minhas.json] == [contribuicao_id]
    assert minhas.json[0]["entrega"]["data_fim"] == acao["data_fim"]
    foto_url = minhas.json[0]["foto_url"]
    foto = cliente.get(foto_url)
    assert foto.status_code == 200 and foto.data == FOTO
    assert foto.content_type.startswith("image/jpeg")
    assert foto.headers["X-Content-Type-Options"] == "nosniff"
    assert foto.headers["Cache-Control"] == "private, no-store"
    with app.app_context():
        gravada = db.session.get(Contribuicao, contribuicao_id)
        assert gravada.doador_id is not None and gravada.estabelecimento_id is None
        assert gravada.foto_arquivo.endswith(".jpg")
        assert "foto.jpg" not in gravada.foto_arquivo
        assert Path(app.instance_path, "uploads", "contribuicoes", gravada.foto_arquivo).is_file()
    sair(cliente)
    assert cliente.get(foto_url).status_code == 404
    entrar(cliente, "azul@exemplo.com")
    assert cliente.get(foto_url).status_code == 404
    outra = contribuir(cliente, acao["id"])
    assert outra.status_code == 201
    assert cliente.get(f"/reconecta/arrecadacoes/contribuicoes/{outra.json['id']}/foto").status_code == 200
    assert cliente.get(foto_url).status_code == 404
    assert [item["id"] for item in cliente.get("/reconecta/arrecadacoes/minhas-contribuicoes").json] == [outra.json["id"]]
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    assert cliente.get(foto_url).status_code == 200
    minhas_acoes = cliente.get("/reconecta/arrecadacoes/minhas").json
    assert minhas_acoes[0]["contribuicoes_aceitas"] == 2
    assert {item["quem"] for item in minhas_acoes[0]["contribuicoes"]} == {"Maria", "Mercado Azul"}


@pytest.mark.parametrize("pergunta,codigo", [
    ("dentro_validade", "ALIMENTO_VENCIDO"),
    ("embalagem_ok", "EMBALAGEM_INADEQUADA"),
    ("armazenado_ok", "ARMAZENAMENTO_INADEQUADO"),
    ("nao_caseiro", "COMIDA_CASEIRA"),
])
def test_cada_resposta_nao_recusa_sem_salvar(cliente, pergunta, codigo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    acao = criar_acao(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, acao["id"], **{pergunta: "nao"})
    assert resposta.status_code == 422
    assert resposta.json["codigo"] == "CONTRIBUICAO_RECUSADA"
    assert codigo in [motivo["codigo"] for motivo in resposta.json["motivos"]]
    with app.app_context():
        assert Contribuicao.query.count() == 0
    assert not list(Path(app.instance_path).rglob("*.jpg"))


@pytest.mark.parametrize("mudanca,codigo", [
    ({"validade": "2020-01-01"}, "ALIMENTO_VENCIDO"),
    ({"categoria": "Laticínios"}, "CATEGORIA_NAO_ACEITA"),
    ({"quantidade": "0"}, "QUANTIDADE_INVALIDA"),
])
def test_alimento_inelegivel_recusado(cliente, mudanca, codigo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    acao = criar_acao(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, acao["id"], **mudanca)
    assert resposta.status_code == 422
    assert codigo in [motivo["codigo"] for motivo in resposta.json["motivos"]]
    with app.app_context():
        assert Contribuicao.query.count() == 0


@pytest.mark.parametrize("foto,nome", [
    pytest.param(b"isto nao e imagem", "foto.jpg", id="assinatura-invalida"),
    pytest.param(FOTO + b"x" * (5 * 1024 * 1024), "foto.jpg", id="maior-que-5mb"),
])
def test_foto_invalida_ou_grande_retorna_400(cliente, foto, nome):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    acao = criar_acao(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, acao["id"], foto=foto, nome=nome)
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "DADOS_INVALIDOS"
    assert "foto" in resposta.json["campos"]
    with app.app_context():
        assert Contribuicao.query.count() == 0


def test_acao_fora_do_periodo_ou_encerrada_recusa_e_so_dona_encerra(cliente):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    futura = criar_acao(cliente, data_inicio=(date.today() + timedelta(days=1)).isoformat())
    ativa = criar_acao(cliente)
    sair(cliente)
    entrar(cliente, "azul@exemplo.com")
    assert cliente.post(f"/reconecta/arrecadacoes/{ativa['id']}/encerrar").status_code == 404
    assert contribuir(cliente, futura["id"]).status_code == 422
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    encerrada = cliente.post(f"/reconecta/arrecadacoes/{ativa['id']}/encerrar")
    assert encerrada.status_code == 200
    assert encerrada.json["status"] == "ENCERRADA"
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    assert contribuir(cliente, ativa["id"]).status_code == 422
    assert cliente.get("/reconecta/arrecadacoes/").json == []
