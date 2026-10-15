"""Correções da rodada 25: tempo de login, revogação de sessão, EXIF da
contribuição, cota da consulta de CNPJ, verificação de origem e SRI da CDN."""
import os
import struct
from datetime import datetime, timedelta
from io import BytesIO

import pytest
from werkzeug.security import generate_password_hash

os.environ["DATABASE_URL"] = "sqlite://"
from app import app  # noqa: E402
import Auth  # noqa: E402
from Auth import _falhas  # noqa: E402
from Cadastro import _consultas_cnpj  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, ItemDoacao, db  # noqa: E402

SENHA = "Segredo123"
EMAIL = "doador@exemplo.invalid"
GPS = b"GPS-DO-DOADOR-MARCADOR"
JPEG = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34\xff\xd9")
JPEG_EXIF = (JPEG[:2] + b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(GPS))
             + b"Exif\x00\x00" + GPS + JPEG[2:])


@pytest.fixture(autouse=True)
def banco(tmp_path):
    instancia = app.instance_path
    app.instance_path = str(tmp_path)
    app.config["TESTING"] = True
    _falhas.clear()
    _consultas_cnpj.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    with app.app_context():
        db.session.remove()
    app.instance_path = instancia
    _falhas.clear()
    _consultas_cnpj.clear()


@pytest.fixture
def cliente():
    return app.test_client()


def semear_doador(email=EMAIL, senha=SENHA):
    with app.app_context():
        doador = Doador(nome="Maria Souza", cpf="52998224725", email=email,
                        telefone="11999996666", senha_hash=generate_password_hash(senha))
        db.session.add(doador)
        db.session.commit()
        return doador.id


def entrar(cliente, email=EMAIL, senha=SENHA):
    resposta = cliente.post("/reconecta/auth/login",
                            json={"identificador": email, "senha": senha})
    assert resposta.status_code == 200, resposta.json
    return resposta


def cookie_da(resposta):
    bruto = resposta.headers["Set-Cookie"]
    return bruto.split(";", 1)[0]


def cliente_com_cookie(valor):
    outro = app.test_client()
    outro.set_cookie("session", valor.split("=", 1)[1])
    return outro


# ---------------- login sem enumeração por tempo ----------------

def test_verifica_hash_mesmo_sem_usuario(cliente, monkeypatch):
    """A resposta do login é igual e a verificação de senha sempre acontece."""
    semear_doador()
    chamadas = []

    def espiar(alvo, senha):
        chamadas.append(alvo)
        return check_real(alvo, senha)

    from werkzeug.security import check_password_hash as check_real
    monkeypatch.setattr(Auth, "check_password_hash", espiar)
    for identificador in (EMAIL, "semconta@exemplo.invalid"):
        resposta = cliente.post("/reconecta/auth/login",
                                json={"identificador": identificador, "senha": "Errada123"})
        assert resposta.status_code == 401
        assert resposta.json["codigo"] == "CREDENCIAIS_INVALIDAS"
    assert len(chamadas) == 2  # o usuário inexistente também pagou a verificação
    assert chamadas[0] != Auth._HASH_FICTICIO
    assert chamadas[1] == Auth._HASH_FICTICIO


# ---------------- revogação de sessão ----------------

def test_logout_invalida_o_cookie_emitido(cliente):
    semear_doador()
    resposta = entrar(cliente)
    antigo = cookie_da(resposta)
    assert cliente.get("/reconecta/auth/me").status_code == 200
    assert cliente.post("/reconecta/auth/logout").status_code == 204
    # replay do cookie capturado antes do logout: antes era 200, agora 401
    assert cliente_com_cookie(antigo).get("/reconecta/auth/me").status_code == 401


def test_troca_de_senha_derruba_as_outras_sessoes(cliente):
    semear_doador()
    primeiro = entrar(cliente)  # cliente principal fica com a sessão nova
    segundo = app.test_client()
    entrar(segundo)
    assert segundo.get("/reconecta/auth/me").status_code == 200
    mudou = cliente.put("/reconecta/auth/me", json={
        "senha_atual": SENHA, "nova_senha": "OutraSenha123"})
    assert mudou.status_code == 200, mudou.json
    # a outra sessão morre; quem trocou a senha continua
    assert segundo.get("/reconecta/auth/me").status_code == 401
    assert cliente.get("/reconecta/auth/me").status_code == 200
    assert cliente_com_cookie(cookie_da(primeiro)).get("/reconecta/auth/me").status_code == 401


def test_excluir_conta_invalida_o_cookie(cliente):
    semear_doador()
    resposta = entrar(cliente)
    antigo = cookie_da(resposta)
    assert cliente.delete("/reconecta/auth/me").status_code == 204
    assert cliente_com_cookie(antigo).get("/reconecta/auth/me").status_code == 401


def test_sessao_antiga_sem_geracao_segue_valendo_ate_expirar(cliente):
    """Cookie emitido antes da coluna de versão não é confundido com revogado."""
    doador_id = semear_doador()
    with cliente.session_transaction() as sessao:
        sessao["tipo"], sessao["usuario_id"] = "doador", doador_id
    assert cliente.get("/reconecta/auth/me").status_code == 200


# ---------------- EXIF também sai da foto da contribuição ----------------

def _semente_pedido():
    with app.app_context():
        ong = Estabelecimento(nome="ONG Prato", cnpj="11444777000161",
                              email="ong@exemplo.invalid", telefone="11999990000",
                              endereco="Av Paulista, 1 - Centro, São Paulo/SP - 01310200",
                              senha_hash=generate_password_hash(SENHA),
                              sem_fins_lucrativos=True, atividade_alimentar=False)
        db.session.add(ong)
        db.session.flush()
        pedido = Doacao(estabelecimento_id=ong.id,
                        data_limite_retirada=datetime.now() + timedelta(days=3),
                        status="DISPONIVEL")
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz",
                          categoria="Grãos e cereais", quantidade=10,
                          unidade_medida="kg")
        db.session.add(item)
        db.session.commit()
        return ong.id, pedido.id


def _contribuir(cliente, pedido_id, item_id, foto=JPEG_EXIF):
    dados = {"item_id": str(item_id), "quantidade": "2",
             "validade": (datetime.now() + timedelta(days=4)).date().isoformat(),
             "dentro_validade": "sim", "embalagem_ok": "sim",
             "armazenado_ok": "sim", "nao_caseiro": "sim"}
    dados["foto"] = (BytesIO(foto), "foto.jpg")
    return cliente.post(f"/reconecta/publico/doacoes/{pedido_id}/contribuicoes",
                        data=dados, content_type="multipart/form-data")


def test_foto_da_contribuicao_grava_sem_exif(cliente):
    semear_doador()
    ong_id, pedido_id = _semente_pedido()
    entrar(cliente)
    with app.app_context():
        item_id = db.session.get(Doacao, pedido_id).itens[0].id
    criado = _contribuir(cliente, pedido_id, item_id)
    assert criado.status_code == 201, criado.json
    with app.app_context():
        gravada = db.session.get(Contribuicao, criado.json["id"])
        assert GPS not in gravada.foto_dados
    # e na leitura pela ONG o metadado também não volta
    ong = app.test_client()
    entrar(ong, email="ong@exemplo.invalid")
    baixada = ong.get(f"/reconecta/contribuicoes/{criado.json['id']}/foto")
    assert baixada.status_code == 200
    assert GPS not in baixada.data


def test_foto_antiga_sai_sem_metadados_na_leitura(cliente):
    """Contribuição gravada antes da limpeza é servida já sem EXIF."""
    semear_doador()
    _, pedido_id = _semente_pedido()
    entrar(cliente)
    with app.app_context():
        item_id = db.session.get(Doacao, pedido_id).itens[0].id
        antiga = Contribuicao(doacao_id=pedido_id, item_doacao_id=item_id,
                              doador_id=1, alimento="Arroz", categoria="Grãos e cereais",
                              quantidade=2, unidade_medida="kg",
                              validade=(datetime.now() + timedelta(days=4)).date(),
                              respostas="{}", foto_arquivo="a" * 32 + ".jpg",
                              foto_dados=JPEG_EXIF, status="ACEITA")
        db.session.add(antiga)
        db.session.commit()
        foto_id = antiga.id
    baixada = cliente.get(f"/reconecta/contribuicoes/{foto_id}/foto")
    assert baixada.status_code == 200 and baixada.mimetype == "image/jpeg"
    assert GPS not in baixada.data


# ---------------- cota da consulta pública de CNPJ ----------------

def test_consulta_cnpj_tem_cota_por_ip(cliente):
    from Cadastro import LIMITE_CONSULTA
    for _ in range(LIMITE_CONSULTA):
        resposta = cliente.get("/reconecta/cadastro/cnpj/11111111")  # inválido: não consulta rede
        assert resposta.status_code == 400
    bloqueada = cliente.get("/reconecta/cadastro/cnpj/11111111")
    assert bloqueada.status_code == 429
    assert bloqueada.json["codigo"] == "MUITAS_TENTATIVAS"
    assert bloqueada.headers["Retry-After"] == "60"


# ---------------- verificação de origem nas escritas ----------------

def test_escrita_com_origem_de_outro_site_e_recusada(cliente):
    resposta = cliente.post("/reconecta/auth/login",
                            json={"identificador": "a@b.c", "senha": "x"},
                            headers={"Origin": "https://malicioso.example"})
    assert resposta.status_code == 403
    assert resposta.json["codigo"] == "ORIGEM_RECUSADA"


def test_origem_null_e_referer_externo_tambem_sao_recusados(cliente):
    assert cliente.post("/reconecta/auth/login", json={"identificador": "a", "senha": "b"},
                        headers={"Origin": "null"}).status_code == 403
    assert cliente.post("/reconecta/auth/login", json={"identificador": "a", "senha": "b"},
                        headers={"Referer": "https://phishing.example/login"}
                        ).status_code == 403


def test_escrita_sem_origem_ou_na_mesma_origem_passa(cliente):
    """Scripts locais (sem Origin) e o front na mesma origem seguem funcionando."""
    sem = cliente.post("/reconecta/auth/login",
                       json={"identificador": "a", "senha": "b"})
    assert sem.status_code == 401  # credenciais, não o bloqueio de origem
    mesmo = cliente.post("/reconecta/auth/login",
                         json={"identificador": "a", "senha": "b"},
                         headers={"Origin": "http://localhost"})
    assert mesmo.status_code == 401
    # leitura não passa pela checagem
    assert cliente.get("/reconecta/saude",
                       headers={"Origin": "https://malicioso.example"}).status_code == 200


# ---------------- integridade do script da CDN ----------------

def test_chartjs_da_cdn_tem_integridade(cliente):
    pagina = cliente.get("/dashboard").data.decode()
    assert 'src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"' in pagina
    assert 'integrity="sha384-' in pagina
    assert 'crossorigin="anonymous"' in pagina
