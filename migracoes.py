"""Migrações pequenas e idempotentes para bancos existentes."""

from sqlalchemy import inspect, text

from models import Arrecadacao, Contribuicao, db


def _migrar_doacoes_sqlite(engine, colunas):
    """SQLite não permite retirar NOT NULL de uma coluna sem recriar a tabela."""
    nomes = {coluna["name"] for coluna in colunas}
    if {"doador_id", "retirada_endereco", "retirada_municipio", "retirada_uf"} <= nomes and next(
        coluna["nullable"] for coluna in colunas if coluna["name"] == "estabelecimento_id"
    ):
        return
    with engine.connect() as conexao:
        # Desativar antes da transação conserva itens e reservas que referenciam doacoes.
        conexao.exec_driver_sql("PRAGMA foreign_keys=OFF")
        conexao.commit()
        try:
            with conexao.begin():
                conexao.exec_driver_sql("""
                    CREATE TABLE doacoes_nova (
                        id INTEGER PRIMARY KEY,
                        estabelecimento_id INTEGER REFERENCES estabelecimentos(id),
                        doador_id INTEGER REFERENCES doadores(id) ON DELETE RESTRICT,
                        retirada_endereco VARCHAR(200),
                        retirada_municipio VARCHAR(80),
                        retirada_uf VARCHAR(2),
                        data_cadastro DATETIME,
                        data_limite_retirada DATETIME NOT NULL,
                        status VARCHAR(20) CHECK (status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA')),
                        CONSTRAINT ck_doacoes_uma_origem CHECK (
                            (estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL))
                    )
                """)
                campos = ["id", "estabelecimento_id", "doador_id", "retirada_endereco",
                          "retirada_municipio", "retirada_uf", "data_cadastro",
                          "data_limite_retirada", "status"]
                fontes = [campo if campo in nomes else "NULL" for campo in campos]
                conexao.exec_driver_sql(
                    f"INSERT INTO doacoes_nova ({', '.join(campos)}) "
                    f"SELECT {', '.join(fontes)} FROM doacoes")
                conexao.exec_driver_sql("DROP TABLE doacoes")
                conexao.exec_driver_sql("ALTER TABLE doacoes_nova RENAME TO doacoes")
        finally:
            conexao.exec_driver_sql("PRAGMA foreign_keys=ON")
            conexao.commit()
        violacoes = conexao.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violacoes:
            raise RuntimeError(f"Migração de doações deixou referências inválidas: {violacoes}")


def _migrar_doacoes_postgresql(engine):
    with engine.begin() as conexao:
        conexao.execute(text("ALTER TABLE doacoes ALTER COLUMN estabelecimento_id DROP NOT NULL"))
        for coluna, tipo in (("doador_id", "INTEGER"),
                             ("retirada_endereco", "VARCHAR(200)"),
                             ("retirada_municipio", "VARCHAR(80)"),
                             ("retirada_uf", "CHAR(2)")):
            conexao.execute(text(f"ALTER TABLE doacoes ADD COLUMN IF NOT EXISTS {coluna} {tipo}"))
        if not conexao.execute(text("""
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_doacao_doador' AND conrelid = 'doacoes'::regclass
        """)).scalar():
            conexao.execute(text("""
                ALTER TABLE doacoes ADD CONSTRAINT fk_doacao_doador
                FOREIGN KEY (doador_id) REFERENCES doadores(id) ON DELETE RESTRICT
            """))
        if not conexao.execute(text("""
            SELECT 1 FROM pg_constraint
            WHERE conname = 'ck_doacoes_uma_origem' AND conrelid = 'doacoes'::regclass
        """)).scalar():
            conexao.execute(text("""
                ALTER TABLE doacoes ADD CONSTRAINT ck_doacoes_uma_origem
                CHECK ((estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL))
            """))


def aplicar_migracoes(engine=None):
    engine = engine or db.engine
    inspector = inspect(engine)
    for tabela in ("estabelecimentos", "doadores"):
        if not inspector.has_table(tabela):
            continue
        colunas = {coluna["name"] for coluna in inspector.get_columns(tabela)}
        if "senha_hash" not in colunas:
            with engine.begin() as conexao:
                conexao.execute(text(f"ALTER TABLE {tabela} ADD COLUMN senha_hash VARCHAR(255)"))
    if inspector.has_table("doacoes"):
        if engine.dialect.name == "sqlite":
            _migrar_doacoes_sqlite(engine, inspector.get_columns("doacoes"))
        elif engine.dialect.name == "postgresql":
            _migrar_doacoes_postgresql(engine)
    # Tabelas novas: checkfirst permite rodar duas vezes e também migrar sem create_all.
    Arrecadacao.__table__.create(engine, checkfirst=True)
    Contribuicao.__table__.create(engine, checkfirst=True)
