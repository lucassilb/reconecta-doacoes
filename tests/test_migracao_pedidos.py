"""Migração segura de arrecadações vazias e pedidos existentes."""
import pytest
from sqlalchemy import create_engine, inspect, text
from migracoes import aplicar_migracoes


def _esquema_anterior(engine, *, com_dados=False):
    with engine.begin() as conexao:
        conexao.execute(text("""CREATE TABLE estabelecimentos (
            id INTEGER PRIMARY KEY, nome TEXT, senha_hash TEXT)"""))
        conexao.execute(text("""CREATE TABLE doadores (
            id INTEGER PRIMARY KEY, nome TEXT, senha_hash TEXT)"""))
        conexao.execute(text("""CREATE TABLE doacoes (
            id INTEGER PRIMARY KEY, estabelecimento_id INTEGER,
            doador_id INTEGER, retirada_endereco TEXT, retirada_municipio TEXT,
            retirada_uf TEXT, data_cadastro DATETIME,
            data_limite_retirada DATETIME NOT NULL, status TEXT,
            CHECK ((estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)))"""))
        conexao.execute(text("""CREATE TABLE itens_doacao (
            id INTEGER PRIMARY KEY, doacao_id INTEGER NOT NULL REFERENCES doacoes(id),
            nome TEXT NOT NULL, categoria TEXT NOT NULL, quantidade NUMERIC NOT NULL,
            unidade_medida TEXT NOT NULL, validade DATE NOT NULL)"""))
        conexao.execute(text("CREATE TABLE arrecadacoes (id INTEGER PRIMARY KEY)"))
        conexao.execute(text("""CREATE TABLE contribuicoes (
            id INTEGER PRIMARY KEY, arrecadacao_id INTEGER NOT NULL REFERENCES arrecadacoes(id))"""))
        conexao.execute(text("INSERT INTO estabelecimentos VALUES (1, 'ASSOCIACAO HUMANITARIA E POR AMOR', NULL)"))
        conexao.execute(text("""INSERT INTO doacoes VALUES
            (1, 1, NULL, NULL, NULL, NULL, '2026-10-03', '2027-12-01', 'DISPONIVEL')"""))
        conexao.execute(text("""INSERT INTO itens_doacao VALUES
            (1, 1, 'Pão', 'Padaria', 100, 'unidade', '2027-12-01'),
            (2, 1, 'Leite', 'Laticínios', 100, 'unidade', '2027-12-01')"""))
        if com_dados:
            conexao.execute(text("INSERT INTO arrecadacoes VALUES (1)"))
            conexao.execute(text("INSERT INTO contribuicoes VALUES (1, 1)"))


def test_sqlite_converte_duas_vezes_e_preserva_primeiro_pedido(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r8.db'}")
    _esquema_anterior(engine)
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    inspetor = inspect(engine)
    assert "arrecadacoes" not in inspetor.get_table_names()
    assert {"doacao_id", "item_doacao_id"} <= {
        coluna["name"] for coluna in inspetor.get_columns("contribuicoes")}
    assert "arrecadacao_id" not in {
        coluna["name"] for coluna in inspetor.get_columns("contribuicoes")}
    assert next(c for c in inspetor.get_columns("itens_doacao") if c["name"] == "validade")["nullable"]
    with engine.begin() as conexao:
        assert conexao.execute(text("SELECT nome, quantidade FROM itens_doacao ORDER BY id")).all() == [
            ("Pão", 100), ("Leite", 100)]
        assert conexao.execute(text("SELECT status FROM doacoes WHERE id=1")).scalar() == "DISPONIVEL"
        conexao.execute(text("""INSERT INTO itens_doacao
            (id, doacao_id, nome, categoria, quantidade, unidade_medida)
            VALUES (3, 1, 'Arroz', 'Grãos e cereais', 5, 'pacote')"""))


def test_tabelas_antigas_com_dados_interrompem_sem_apagar(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r8-com-dados.db'}")
    _esquema_anterior(engine, com_dados=True)
    with pytest.raises(RuntimeError, match="contém dados"):
        aplicar_migracoes(engine)
    with engine.begin() as conexao:
        assert conexao.execute(text("SELECT COUNT(*) FROM arrecadacoes")).scalar() == 1
        assert conexao.execute(text("SELECT COUNT(*) FROM contribuicoes")).scalar() == 1
        assert conexao.execute(text("SELECT COUNT(*) FROM itens_doacao")).scalar() == 2
