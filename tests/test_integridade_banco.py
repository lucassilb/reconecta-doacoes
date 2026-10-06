"""Restrições do esquema novo e migração SQLite em banco descartável."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from migracoes import aplicar_migracoes
from models import Contribuicao, Doacao, ItemDoacao, Reserva, db


@pytest.fixture
def engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def ativar_fks(conexao, _registro):
        conexao.execute("PRAGMA foreign_keys=ON")

    db.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _dados(engine):
    with engine.begin() as conexao:
        conexao.execute(text("""INSERT INTO estabelecimentos
            (id, nome, cnpj, email, telefone, endereco)
            VALUES (1, 'Empresa A', '12345678000195', 'a@exemplo.com',
                    '11999999999', 'Rua A, 1')"""))
        conexao.execute(text("""INSERT INTO doadores
            (id, nome, cpf, email, telefone, criado_em)
            VALUES (1, 'Maria Souza', '52998224725', 'maria@exemplo.com',
                    '11999999999', '2026-10-05')"""))
        conexao.execute(text("""INSERT INTO instituicoes
            (id, nome, cnpj, email, telefone, endereco)
            VALUES (1, 'Instituição', '47508411000156', 'i@exemplo.com',
                    '11999999999', 'Rua I, 1')"""))
        for pedido_id in (1, 2):
            conexao.execute(text("""INSERT INTO doacoes
                (id, estabelecimento_id, data_limite_retirada, status)
                VALUES (:id, 1, '2027-12-01', 'DISPONIVEL')"""),
                {"id": pedido_id})
        for item_id, pedido_id, nome in ((1, 1, "Leite"), (2, 1, "Pão"), (3, 2, "Arroz")):
            conexao.execute(text("""INSERT INTO itens_doacao
                (id, doacao_id, nome, categoria, quantidade, unidade_medida)
                VALUES (:id, :pedido, :nome, 'Alimentos', 100, 'unidade')"""),
                {"id": item_id, "pedido": pedido_id, "nome": nome})
        conexao.execute(text("""INSERT INTO contribuicoes
            (id, doacao_id, item_doacao_id, doador_id, alimento, categoria,
             quantidade, unidade_medida, validade, respostas, foto_arquivo,
             status, criado_em)
            VALUES (1, 1, 1, 1, 'Leite', 'Alimentos', 12, 'unidade',
                    '2027-11-01', '{}', 'foto.jpg', 'ACEITA', '2026-10-05')"""))


def test_esquema_orm_tem_checks_e_fk_composta(engine):
    inspetor = inspect(engine)
    for tabela, nome in (
        ("doacoes", "ck_doacoes_status"),
        ("reservas", "ck_reservas_status"),
        ("itens_doacao", "ck_itens_doacao_quantidade"),
    ):
        assert nome in {check["name"] for check in inspetor.get_check_constraints(tabela)}
    assert "uq_itens_doacao_id_doacao_id" in {
        unique["name"] for unique in inspetor.get_unique_constraints("itens_doacao")}
    assert any(fk["name"] == "fk_contribuicoes_item_pedido" and
               fk["constrained_columns"] == ["item_doacao_id", "doacao_id"] and
               fk["referred_columns"] == ["id", "doacao_id"]
               for fk in inspetor.get_foreign_keys("contribuicoes"))


def test_banco_recusa_status_quantidade_e_item_de_outro_pedido(engine):
    _dados(engine)
    invalidos = (
        "UPDATE doacoes SET status='INVALIDO' WHERE id=1",
        "UPDATE itens_doacao SET quantidade=0 WHERE id=1",
        "INSERT INTO reservas (doacao_id, instituicao_id, status) VALUES (1, 1, 'INVALIDO')",
        "UPDATE contribuicoes SET item_doacao_id=3 WHERE id=1",
    )
    for sql in invalidos:
        with pytest.raises(IntegrityError):
            with engine.begin() as conexao:
                conexao.execute(text(sql))
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT item_doacao_id FROM contribuicoes WHERE id=1")).scalar() == 1


def test_orm_nao_contorna_checks_nem_fk_composta(engine):
    _dados(engine)
    with Session(engine) as sessao:
        alteracoes = (
            (Doacao, 1, "status", "INVALIDO"),
            (ItemDoacao, 1, "quantidade", 0),
            (Contribuicao, 1, "item_doacao_id", 3),
        )
        for modelo, identificador, campo, valor in alteracoes:
            setattr(sessao.get(modelo, identificador), campo, valor)
            with pytest.raises(IntegrityError):
                sessao.commit()
            sessao.rollback()
        sessao.add(Reserva(doacao_id=1, instituicao_id=1, status="INVALIDO"))
        with pytest.raises(IntegrityError):
            sessao.commit()


def test_migracao_sqlite_duas_vezes_preserva_pedido_itens_e_contribuicao(engine):
    _dados(engine)
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT COUNT(*) FROM doacoes")).scalar() == 2
        assert conexao.execute(text("SELECT COUNT(*) FROM itens_doacao")).scalar() == 3
        assert conexao.execute(text("SELECT quantidade FROM contribuicoes WHERE id=1")).scalar() == 12


def test_migracao_sqlite_em_tabelas_antigas_preserva_dados(tmp_path):
    antigo = create_engine(f"sqlite:///{tmp_path / 'anterior.db'}")
    comandos = (
        """CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
            cnpj TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
            telefone TEXT NOT NULL, endereco TEXT NOT NULL, senha_hash TEXT)""",
        """CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
            cpf TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
            telefone TEXT NOT NULL, criado_em DATETIME NOT NULL, senha_hash TEXT)""",
        """CREATE TABLE instituicoes (id INTEGER PRIMARY KEY, nome TEXT NOT NULL,
            cnpj TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE,
            telefone TEXT NOT NULL, endereco TEXT NOT NULL)""",
        """CREATE TABLE doacoes (id INTEGER PRIMARY KEY,
            estabelecimento_id INTEGER REFERENCES estabelecimentos(id),
            doador_id INTEGER REFERENCES doadores(id),
            retirada_endereco TEXT, retirada_municipio TEXT, retirada_uf TEXT,
            data_cadastro DATETIME, data_limite_retirada DATETIME NOT NULL,
            status TEXT)""",
        """CREATE TABLE itens_doacao (id INTEGER PRIMARY KEY,
            doacao_id INTEGER NOT NULL REFERENCES doacoes(id), nome TEXT NOT NULL,
            categoria TEXT NOT NULL, quantidade NUMERIC NOT NULL,
            unidade_medida TEXT NOT NULL, validade DATE)""",
        """CREATE TABLE contribuicoes (id INTEGER PRIMARY KEY,
            doacao_id INTEGER NOT NULL REFERENCES doacoes(id),
            item_doacao_id INTEGER NOT NULL REFERENCES itens_doacao(id),
            doador_id INTEGER REFERENCES doadores(id),
            estabelecimento_id INTEGER REFERENCES estabelecimentos(id),
            alimento TEXT NOT NULL, categoria TEXT NOT NULL,
            quantidade NUMERIC NOT NULL, unidade_medida TEXT NOT NULL,
            validade DATE NOT NULL, respostas TEXT NOT NULL,
            foto_arquivo TEXT NOT NULL, status TEXT NOT NULL,
            criado_em DATETIME NOT NULL)""",
    )
    with antigo.begin() as conexao:
        for comando in comandos:
            conexao.execute(text(comando))
    _dados(antigo)
    aplicar_migracoes(antigo)
    aplicar_migracoes(antigo)
    with antigo.connect() as conexao:
        assert conexao.execute(text("SELECT COUNT(*) FROM doacoes")).scalar() == 2
        assert conexao.execute(text("SELECT nome FROM itens_doacao ORDER BY id")).scalars().all() == [
            "Leite", "Pão", "Arroz"]
        assert conexao.execute(text("SELECT quantidade FROM contribuicoes WHERE id=1")).scalar() == 12
    antigo.dispose()


@pytest.fixture
def postgres_temporario():
    arquivo_senha = os.getenv("CP2_PG_SUPERUSER_PASSWORD_FILE")
    if not arquivo_senha:
        pytest.skip("Defina CP2_PG_SUPERUSER_PASSWORD_FILE para a prova PostgreSQL")
    senha = Path(arquivo_senha).read_text(encoding="utf-8").strip()
    admin_url = URL.create("postgresql+psycopg", username="postgres", password=senha,
                           host="127.0.0.1", port=5432, database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    nome = f"cp2_banco_{uuid4().hex}"
    engine = None
    criado = False
    try:
        with admin.connect() as conexao:
            conexao.exec_driver_sql(f"CREATE DATABASE {nome}")
        criado = True
        engine = create_engine(admin_url.set(database=nome), poolclass=NullPool)
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        try:
            if criado:
                with admin.connect() as conexao:
                    conexao.exec_driver_sql(f"DROP DATABASE {nome}")
        finally:
            admin.dispose()


def _schema_main_com_dados(engine):
    schema = (Path(__file__).parent / "fixtures" / "schema_main_9882e38.sql").read_text(
        encoding="utf-8")
    with engine.begin() as conexao:
        for comando in schema.split(";"):
            if comando.strip():
                conexao.execute(text(comando))
        conexao.execute(text("""INSERT INTO estabelecimentos
            (id, nome, cnpj, email, telefone, endereco)
            VALUES (1, 'Empresa A', '12345678000195', 'a@exemplo.com',
                    '11999999999', 'Rua A, 1')"""))
        conexao.execute(text("""INSERT INTO doadores
            (id, nome, cpf, email, telefone)
            VALUES (1, 'Maria Souza', '52998224725', 'maria@exemplo.com', '11999999999')"""))
        conexao.execute(text("""INSERT INTO doacoes
            (id, estabelecimento_id, data_limite_retirada, status)
            VALUES (1, 1, '2027-12-01', 'DISPONIVEL')"""))
        for item_id, nome in ((1, "Leite"), (2, "Pão")):
            conexao.execute(text("""INSERT INTO itens_doacao
                (id, doacao_id, nome, categoria, quantidade, unidade_medida)
                VALUES (:id, 1, :nome, 'Alimentos', 100, 'unidade')"""),
                {"id": item_id, "nome": nome})
        conexao.execute(text("""INSERT INTO contribuicoes
            (id, doacao_id, item_doacao_id, doador_id, alimento, categoria,
             quantidade, unidade_medida, validade, respostas, foto_arquivo)
            VALUES (1, 1, 1, 1, 'Leite', 'Alimentos', 12, 'unidade',
                    '2027-11-01', '{}', 'foto.jpg')"""))


def _outro_pedido(engine):
    with engine.begin() as conexao:
        conexao.execute(text("""INSERT INTO doacoes
            (id, estabelecimento_id, data_limite_retirada, status)
            VALUES (2, 1, '2027-12-01', 'DISPONIVEL')"""))
        conexao.execute(text("""INSERT INTO itens_doacao
            (id, doacao_id, nome, categoria, quantidade, unidade_medida)
            VALUES (3, 2, 'Arroz', 'Alimentos', 100, 'unidade')"""))


def test_postgresql_migra_schema_main_duas_vezes_sem_perder_dados(postgres_temporario):
    engine = postgres_temporario
    _schema_main_com_dados(engine)
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT COUNT(*) FROM doacoes")).scalar() == 1
        assert conexao.execute(text("SELECT nome FROM itens_doacao ORDER BY id")).scalars().all() == [
            "Leite", "Pão"]
        assert conexao.execute(text("SELECT quantidade FROM contribuicoes WHERE id=1")).scalar() == 12
        restricoes = dict(conexao.execute(text("""
            SELECT conname, convalidated FROM pg_constraint
            WHERE conname IN ('ck_doacoes_status', 'ck_reservas_status',
                'ck_itens_doacao_quantidade', 'uq_itens_doacao_id_doacao_id',
                'fk_contribuicoes_item_pedido')""")).all())
        assert restricoes == {nome: True for nome in (
            "ck_doacoes_status", "ck_reservas_status", "ck_itens_doacao_quantidade",
            "uq_itens_doacao_id_doacao_id", "fk_contribuicoes_item_pedido")}
    _outro_pedido(engine)
    with pytest.raises(IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(text("UPDATE contribuicoes SET item_doacao_id=3 WHERE id=1"))


def test_postgresql_migracao_recusa_vinculo_antigo_invalido(postgres_temporario):
    engine = postgres_temporario
    _schema_main_com_dados(engine)
    _outro_pedido(engine)
    with engine.begin() as conexao:
        conexao.execute(text("UPDATE contribuicoes SET item_doacao_id=3 WHERE id=1"))
    with pytest.raises(RuntimeError, match="fk_contribuicoes_item_pedido"):
        aplicar_migracoes(engine)
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT item_doacao_id FROM contribuicoes WHERE id=1")).scalar() == 3
    with engine.begin() as conexao:
        conexao.execute(text("UPDATE contribuicoes SET item_doacao_id=1 WHERE id=1"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)


def test_postgresql_schema_sql_novo_tem_as_restricoes(postgres_temporario):
    schema = (Path(__file__).parents[1] / "schema.sql").read_text(encoding="utf-8")
    with postgres_temporario.begin() as conexao:
        for comando in schema.split(";"):
            if comando.strip():
                conexao.execute(text(comando))
    with postgres_temporario.connect() as conexao:
        restricoes = dict(conexao.execute(text("""
            SELECT conname, convalidated FROM pg_constraint
            WHERE conname IN ('ck_doacoes_status', 'ck_reservas_status',
                'ck_itens_doacao_quantidade', 'uq_itens_doacao_id_doacao_id',
                'fk_contribuicoes_item_pedido')"""
        )).all())
        assert restricoes == {nome: True for nome in (
            "ck_doacoes_status", "ck_reservas_status", "ck_itens_doacao_quantidade",
            "uq_itens_doacao_id_doacao_id", "fk_contribuicoes_item_pedido")}
