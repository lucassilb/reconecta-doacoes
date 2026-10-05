"""Migração de um banco SQLite criado pelo esquema anterior."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from migracoes import aplicar_migracoes


def test_migracao_sqlite_antiga_duas_vezes_preserva_doacao_itens_e_reserva(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'antigo.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome TEXT)"))
        conexao.execute(text("CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome TEXT)"))
        conexao.execute(text("""CREATE TABLE doacoes (
            id INTEGER PRIMARY KEY, estabelecimento_id INTEGER NOT NULL REFERENCES estabelecimentos(id),
            data_cadastro DATETIME, data_limite_retirada DATETIME NOT NULL, status VARCHAR(20))"""))
        conexao.execute(text("CREATE TABLE itens_doacao (id INTEGER PRIMARY KEY, doacao_id INTEGER REFERENCES doacoes(id))"))
        conexao.execute(text("CREATE TABLE reservas (id INTEGER PRIMARY KEY, doacao_id INTEGER REFERENCES doacoes(id))"))
        conexao.execute(text("INSERT INTO estabelecimentos VALUES (1, 'Mercado')"))
        conexao.execute(text("INSERT INTO doadores VALUES (1, 'Maria')"))
        conexao.execute(text("INSERT INTO doacoes VALUES (1, 1, '2026-10-03', '2026-10-06', 'DISPONIVEL')"))
        conexao.execute(text("INSERT INTO itens_doacao VALUES (1, 1)"))
        conexao.execute(text("INSERT INTO reservas VALUES (1, 1)"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    assert "arrecadacoes" not in inspect(engine).get_table_names()
    assert "contribuicoes" in inspect(engine).get_table_names()
    assert {"doacao_id", "item_doacao_id"} <= {
        coluna["name"] for coluna in inspect(engine).get_columns("contribuicoes")}
    assert inspect(engine).get_columns("itens_doacao")[-1]["name"] == "validade"
    colunas = {coluna["name"]: coluna for coluna in inspect(engine).get_columns("doacoes")}
    assert colunas["estabelecimento_id"]["nullable"]
    assert {"doador_id", "retirada_endereco", "retirada_municipio", "retirada_uf"} <= colunas.keys()
    with engine.begin() as conexao:
        assert conexao.execute(text("SELECT estabelecimento_id, doador_id FROM doacoes WHERE id=1")).one() == (1, None)
        assert conexao.execute(text("SELECT doacao_id FROM itens_doacao")).scalar() == 1
        assert conexao.execute(text("SELECT doacao_id FROM reservas")).scalar() == 1
        conexao.execute(text("""INSERT INTO doacoes
            (id, doador_id, retirada_endereco, retirada_municipio, retirada_uf, data_limite_retirada)
            VALUES (2, 1, 'Rua das Flores, 123', 'Barueri', 'SP', '2026-10-06')"""))
    with pytest.raises(IntegrityError):
        with engine.begin() as conexao:
            conexao.execute(text("""INSERT INTO doacoes
                (id, estabelecimento_id, doador_id, data_limite_retirada)
                VALUES (3, 1, 1, '2026-10-06')"""))
