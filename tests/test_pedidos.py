"""Fluxo de pedidos e contribuições da rodada 9."""
import os
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
import pytest
from werkzeug.security import generate_password_hash

os.environ["DATABASE_URL"] = "sqlite://"
from app import app  # noqa: E402
from Auth import _falhas  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, Instituicao, db  # noqa: E402

SENHA = "Segredo123"
FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"

@pytest.fixture(autouse=True)
def banco(tmp_path):
    instancia = app.instance_path
    app.instance_path = str(tmp_path)
    app.config["TESTING"] = True
    _falhas.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    with app.app_context():
        db.session.remove()
    app.instance_path = instancia
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
    resposta = cliente.post("/reconecta/auth/login", json={
        "identificador": email, "senha": SENHA})
    assert resposta.status_code == 200, resposta.json

def sair(cliente):
    assert cliente.post("/reconecta/auth/logout").status_code == 204

def corpo_pedido(**mudancas):
    return {"receber_ate": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"),
            "itens": [{"nome": "Leite", "categoria": "Laticínios", "quantidade": 100,
                       "unidade_medida": "unidade"},
                      {"nome": "Pão", "categoria": "Padaria", "quantidade": 100,
                       "unidade_medida": "unidade"}], **mudancas}

def criar_pedido(cliente, **mudancas):
    resposta = cliente.post("/reconecta/painel/doacoes", json=corpo_pedido(**mudancas))
    assert resposta.status_code == 201, resposta.json
    return resposta.json

def contribuir(cliente, pedido, item_id=None, foto=FOTO, **mudancas):
    dados = {"item_id": str(item_id or pedido["itens"][0]["id"]), "quantidade": "20",
             "validade": (date.today() + timedelta(days=4)).isoformat(),
             "dentro_validade": "sim", "embalagem_ok": "sim", "armazenado_ok": "sim",
             "nao_caseiro": "sim", **mudancas}
    dados["foto"] = (BytesIO(foto), "foto.jpg")
    return cliente.post(f"/reconecta/publico/doacoes/{pedido['id']}/contribuicoes",
                        data=dados, content_type="multipart/form-data")

def test_empresa_publica_pedido_sem_validade_e_doador_nao_publica(cliente):
    usuarios()
    assert cliente.post("/reconecta/painel/doacoes", json=corpo_pedido()).status_code == 401
    entrar(cliente, "maria@exemplo.com")
    for metodo in (cliente.get, cliente.post):
        resposta = metodo("/reconecta/painel/doacoes", **({"json": corpo_pedido()} if metodo == cliente.post else {}))
        assert resposta.status_code == 403
        assert resposta.json["codigo"] == "APENAS_EMPRESAS"
    assert cliente.delete("/reconecta/painel/doacoes/1").status_code == 403
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    assert pedido["empresa"]["nome"] == "Mercado Verde"
    assert [item["faltam"] for item in pedido["itens"]] == [100, 100]
    with app.app_context():
        assert all(item.validade is None for item in Doacao.query.one().itens)
    assert [p["id"] for p in cliente.get("/reconecta/painel/doacoes").json] == [pedido["id"]]
    assert cliente.get("/reconecta/doacoes/").status_code == 200

@pytest.mark.parametrize("mudanca,campo", [
    ({"itens": []}, "itens"),
    ({"itens": [{"nome": "Leite", "categoria": "Laticínios", "quantidade": 0,
                 "unidade_medida": "unidade"}]}, "itens[0].quantidade"),
    ({"itens": [{"nome": "Leite", "categoria": "Outra", "quantidade": 1,
                 "unidade_medida": "unidade"}]}, "itens[0].categoria"),
    ({"receber_ate": "2020-01-01T00:00"}, "receber_ate"),
])
def test_pedido_invalido_nao_grava(cliente, mudanca, campo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    resposta = cliente.post("/reconecta/painel/doacoes", json=corpo_pedido(**mudanca))
    assert resposta.status_code == 400
    assert campo in resposta.json["campos"]
    with app.app_context():
        assert Doacao.query.count() == 0

def test_lista_detalhe_resumo_e_privacidade(cliente):
    usuarios()
    with app.app_context():
        db.session.add(Instituicao(nome="ONG", cnpj="12345678000190",
                                   email="ong@exemplo.com", telefone="11999995555", endereco="BARUERI/SP"))
        db.session.commit()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    detalhe = cliente.get(f"/reconecta/publico/doacoes/{pedido['id']}").json
    assert detalhe["pode_doar"] is False
    assert detalhe["motivo_bloqueio"] == "Este é o seu próprio pedido"
    sair(cliente)
    detalhe = cliente.get(f"/reconecta/publico/doacoes/{pedido['id']}")
    assert detalhe.json["motivo_bloqueio"] == "Entre para doar"
    assert detalhe.json["empresa"]["municipio_uf"] == "BARUERI/SP"
    assert [i["recebido"] for i in detalhe.json["itens"]] == [0, 0]
    for segredo in ("AV CENTRAL", "47508411000156", "verde@exemplo.com"):
        assert segredo not in detalhe.get_data(as_text=True)
    assert cliente.get("/reconecta/publico/doacoes").json[0]["id"] == pedido["id"]
    assert cliente.get("/reconecta/publico/resumo").json == {
        "empresas": 2, "doadores": 1, "instituicoes": 1,
        "doacoes_disponiveis": 1, "itens_disponiveis": 2,
        "kg_disponiveis": 0.0, "doacoes_recebidas": 0}

def test_doador_e_outra_empresa_doam_com_foto_e_progresso(cliente):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    assert contribuir(cliente, pedido).status_code == 409
    sair(cliente)
    assert contribuir(cliente, pedido).status_code == 401
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, pedido)
    assert resposta.status_code == 201, resposta.json
    assert resposta.json["entrega"]["endereco"].startswith("AV CENTRAL")
    foto_url = f"/reconecta/contribuicoes/{resposta.json['id']}/foto"
    assert cliente.get(foto_url).status_code == 200
    minhas = cliente.get("/reconecta/painel/minhas-doacoes").json
    assert minhas[0]["pedido"]["id"] == pedido["id"]
    assert minhas[0]["entrega"]["endereco"].startswith("AV CENTRAL")
    sair(cliente)
    assert cliente.get(foto_url).status_code == 404
    entrar(cliente, "azul@exemplo.com")
    assert cliente.get(foto_url).status_code == 404
    segunda = contribuir(cliente, pedido, quantidade="90")
    assert segunda.status_code == 201, segunda.json
    assert cliente.get("/reconecta/painel/minhas-doacoes").json[0]["id"] == segunda.json["id"]
    detalhe = cliente.get(f"/reconecta/publico/doacoes/{pedido['id']}").json
    assert detalhe["itens"][0]["recebido"] == 110
    assert detalhe["itens"][0]["faltam"] == 0
    assert detalhe["doacoes_recebidas"] == 2
    assert cliente.get("/reconecta/publico/resumo").json["doacoes_recebidas"] == 2
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    painel = cliente.get("/reconecta/painel/doacoes").json[0]
    assert {c["quem"] for c in painel["contribuicoes"]} == {"Maria", "Mercado Azul"}
    assert cliente.get(foto_url).status_code == 200
    assert cliente.delete(f"/reconecta/painel/doacoes/{pedido['id']}").status_code == 409
    with app.app_context():
        assert Contribuicao.query.count() == 2
        assert all(Path(app.instance_path, "uploads", "contribuicoes", c.foto_arquivo).is_file()
                   for c in Contribuicao.query.all())

@pytest.mark.parametrize("pergunta,codigo", [
    ("dentro_validade", "ALIMENTO_VENCIDO"),
    ("embalagem_ok", "EMBALAGEM_INADEQUADA"),
    ("armazenado_ok", "ARMAZENAMENTO_INADEQUADO"),
    ("nao_caseiro", "COMIDA_CASEIRA"),
])
def test_cada_resposta_nao_recusa_sem_gravar(cliente, pergunta, codigo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, pedido, **{pergunta: "nao"})
    assert resposta.status_code == 422
    assert codigo in [m["codigo"] for m in resposta.json["motivos"]]
    with app.app_context():
        assert Contribuicao.query.count() == 0

@pytest.mark.parametrize("mudanca,codigo", [
    ({"validade": "2020-01-01"}, "ALIMENTO_VENCIDO"),
    ({"categoria": "Padaria"}, "CATEGORIA_NAO_ACEITA"),
    ({"quantidade": "0"}, "QUANTIDADE_INVALIDA"),
])
def test_alimento_inelegivel_recusado(cliente, mudanca, codigo):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    resposta = contribuir(cliente, pedido, **mudanca)
    assert resposta.status_code == 422
    assert codigo in [m["codigo"] for m in resposta.json["motivos"]]
    with app.app_context():
        assert Contribuicao.query.count() == 0

def test_item_alheio_foto_invalida_e_grande(cliente):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    outro = criar_pedido(cliente)
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    assert contribuir(cliente, pedido, item_id=outro["itens"][0]["id"]).status_code == 422
    assert contribuir(cliente, pedido, foto=b"texto puro").status_code == 400
    grande = contribuir(cliente, pedido, foto=FOTO + b"x" * (5 * 1024 * 1024))
    assert grande.status_code in (400, 413)
    assert grande.json["codigo"] in ("DADOS_INVALIDOS", "ARQUIVO_GRANDE")
    acima_limite_total = contribuir(cliente, pedido, foto=FOTO + b"x" * (6 * 1024 * 1024))
    assert acima_limite_total.status_code == 413
    assert acima_limite_total.json["codigo"] == "ARQUIVO_GRANDE"
    with app.app_context():
        assert Contribuicao.query.count() == 0

def test_pedido_encerrado_remocao_e_rotas_arrecadacao_sumiram(cliente):
    usuarios()
    entrar(cliente, "verde@exemplo.com")
    pedido = criar_pedido(cliente)
    with app.app_context():
        p = db.session.get(Doacao, pedido["id"])
        p.status = "RETIRADA"
        db.session.commit()
    sair(cliente)
    entrar(cliente, "maria@exemplo.com")
    assert contribuir(cliente, pedido).status_code == 422
    assert cliente.get("/reconecta/publico/doacoes").json == []
    assert cliente.get(f"/reconecta/publico/doacoes/{pedido['id']}").json["motivo_bloqueio"] == "Pedido encerrado"
    assert cliente.get("/reconecta/arrecadacoes/").status_code == 404
    assert cliente.get("/arrecadacoes").status_code == 404
    sair(cliente)
    entrar(cliente, "verde@exemplo.com")
    novo = criar_pedido(cliente)
    assert cliente.delete(f"/reconecta/painel/doacoes/{novo['id']}").status_code == 204
