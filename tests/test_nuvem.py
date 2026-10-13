"""Contratos de nuvem sem tocar em banco ou servico externo."""
import os
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url

os.environ["DATABASE_URL"] = "sqlite://"
from app import _database_url, app  # noqa: E402
from migracoes import _migrar_foto_contribuicao  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, ItemDoacao, db  # noqa: E402

FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"


@pytest.fixture
def cliente(tmp_path):
    instancia, teste = app.instance_path, app.config["TESTING"]
    app.instance_path = str(tmp_path)
    app.config["TESTING"] = True
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
    yield app.test_client()
    with app.app_context():
        db.session.remove()
        db.drop_all()
    app.instance_path, app.config["TESTING"] = instancia, teste


def test_url_postgres_local_e_supabase():
    assert _database_url(None) == "sqlite:///reconecta.db"
    assert _database_url("sqlite://") == "sqlite://"
    local = make_url(_database_url("postgres://u:p@localhost:5432/dev"))
    assert local.drivername == "postgresql+psycopg"
    assert "sslmode" not in local.query
    remota = make_url(_database_url(
        "postgresql://u:p@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?application_name=reconecta"))
    assert remota.drivername == "postgresql+psycopg"
    assert remota.query["sslmode"] == "require"
    assert remota.query["application_name"] == "reconecta"
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_pre_ping"] is True


def test_saude_consulta_banco_e_sinaliza_falha(cliente, monkeypatch):
    resposta = cliente.get("/reconecta/saude")
    assert resposta.status_code == 200
    assert resposta.json == {"status": "ok", "banco": "ok"}

    def falhar(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("sem conexao"))

    monkeypatch.setattr(db.session, "execute", falhar)
    resposta = cliente.get("/reconecta/saude")
    assert resposta.status_code == 503
    assert resposta.json["banco"] == "indisponivel"


def test_migracao_foto_sqlite_idempotente_preserva_linha(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legado.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE contribuicoes (id INTEGER PRIMARY KEY, foto_arquivo TEXT NOT NULL)"))
        conexao.execute(text("INSERT INTO contribuicoes VALUES (1, 'antiga.jpg')"))
    _migrar_foto_contribuicao(engine)
    _migrar_foto_contribuicao(engine)
    assert sum(c["name"] == "foto_dados" for c in inspect(engine).get_columns("contribuicoes")) == 1
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT foto_arquivo, foto_dados FROM contribuicoes")).one() == (
            "antiga.jpg", None)
    engine.dispose()


def test_nova_foto_no_banco_e_fallback_legado_com_acesso_privado(cliente):
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado", cnpj="47508411000156", email="mercado@example.org",
                                  telefone="11999998888", endereco="Rua A, 1")
        doador = Doador(nome="Maria", cpf="52998224725", email="maria@example.org",
                        telefone="11999997777")
        db.session.add_all([empresa, doador])
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id,
                        data_limite_retirada=datetime.now() + timedelta(days=3), status="DISPONIVEL")
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Mercearia",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.commit()
        doador_id, pedido_id, item_id = doador.id, pedido.id, item.id

    with cliente.session_transaction() as sessao:
        sessao["tipo"] = "doador"
        sessao["usuario_id"] = doador_id
    resposta = cliente.post(f"/reconecta/publico/doacoes/{pedido_id}/contribuicoes", data={
        "item_id": str(item_id), "quantidade": "2", "validade": (date.today() + timedelta(days=4)).isoformat(),
        "dentro_validade": "sim", "embalagem_ok": "sim", "armazenado_ok": "sim", "nao_caseiro": "sim",
        "foto": (BytesIO(FOTO), "arroz.jpg"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 201, resposta.json
    foto_url = f"/reconecta/contribuicoes/{resposta.json['id']}/foto"
    with app.app_context():
        contribuicao = db.session.get(Contribuicao, resposta.json["id"])
        assert contribuicao.foto_dados == FOTO
        caminho = Path(app.instance_path) / "uploads" / "contribuicoes" / contribuicao.foto_arquivo
        assert caminho.is_file()
        caminho.unlink()
    resposta_foto = cliente.get(foto_url)
    assert resposta_foto.status_code == 200
    assert resposta_foto.data == FOTO
    assert resposta_foto.headers["Cache-Control"] == "private, no-store"
    with app.app_context():
        contribuicao = db.session.get(Contribuicao, resposta.json["id"])
        contribuicao.foto_dados = None
        db.session.commit()
        caminho.write_bytes(FOTO)
    assert cliente.get(foto_url).data == FOTO
    with cliente.session_transaction() as sessao:
        sessao.clear()
    assert cliente.get(foto_url).status_code == 404
