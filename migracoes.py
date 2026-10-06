"""Migrações pequenas e idempotentes para bancos existentes."""

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from models import Contribuicao, Doacao, ItemDoacao, db


def _migrar_indices(engine):
    """Cria os índices ausentes sem alterar dados, em SQLite e PostgreSQL."""
    for modelo in (Doacao, ItemDoacao, Contribuicao):
        if inspect(engine).has_table(modelo.__tablename__):
            for indice in modelo.__table__.indexes:
                indice.create(bind=engine, checkfirst=True)


def _restricao_postgresql(conexao, tabela, nome):
    """None se ausente; caso contrário informa se já foi validada."""
    linha = conexao.execute(text("""
        SELECT convalidated FROM pg_constraint
        WHERE conrelid = to_regclass(:tabela) AND conname = :nome
    """), {"tabela": tabela, "nome": nome}).first()
    return None if linha is None else linha[0]


def _migrar_chave_item_postgresql(engine):
    """Prepara a chave referenciada antes de criar a tabela de contribuições."""
    if not inspect(engine).has_table("itens_doacao"):
        return
    with engine.begin() as conexao:
        if _restricao_postgresql(conexao, "itens_doacao", "uq_itens_doacao_id_doacao_id") is None:
            conexao.execute(text("""ALTER TABLE itens_doacao
                ADD CONSTRAINT uq_itens_doacao_id_doacao_id UNIQUE (id, doacao_id)"""))


def _migrar_integridade_postgresql(engine):
    """Acrescenta restrições sem varrer a tabela no ADD e valida dados existentes."""
    existentes = set(inspect(engine).get_table_names())
    restricoes = (
        ("doacoes", "ck_doacoes_status",
         "CHECK (status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA'))"),
        ("reservas", "ck_reservas_status",
         "CHECK (status IN ('ATIVA', 'CANCELADA', 'CONCLUIDA'))"),
        ("itens_doacao", "ck_itens_doacao_quantidade", "CHECK (quantidade > 0)"),
        ("contribuicoes", "fk_contribuicoes_item_pedido",
         "FOREIGN KEY (item_doacao_id, doacao_id) "
         "REFERENCES itens_doacao (id, doacao_id) ON DELETE RESTRICT"),
    )
    with engine.begin() as conexao:
        for tabela, nome, definicao in restricoes:
            if tabela not in existentes:
                continue
            validada = _restricao_postgresql(conexao, tabela, nome)
            if validada is None:
                conexao.execute(text(f"ALTER TABLE {tabela} ADD CONSTRAINT {nome} {definicao} NOT VALID"))
            if validada is not True:
                try:
                    conexao.execute(text(f"ALTER TABLE {tabela} VALIDATE CONSTRAINT {nome}"))
                except DBAPIError as erro:
                    raise RuntimeError(
                        f"Migração de integridade interrompida: dados existentes violam "
                        f"{nome} em {tabela}; corrija os registros e repita a migração."
                    ) from erro


def _migrar_pedidos(engine):
    """Descarta somente tabelas vazias da rodada 8 e libera validade do pedido."""
    inspector = inspect(engine)
    tabelas = set(inspector.get_table_names())
    contribuicoes_antigas = ("contribuicoes" in tabelas and
                            "arrecadacao_id" in {c["name"] for c in inspector.get_columns("contribuicoes")})
    if "arrecadacoes" in tabelas or contribuicoes_antigas:
        with engine.connect() as conexao:
            for tabela in ("arrecadacoes", "contribuicoes"):
                if tabela in tabelas and (tabela == "arrecadacoes" or contribuicoes_antigas):
                    if conexao.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar():
                        raise RuntimeError(
                            f"Migração de pedidos interrompida: {tabela} contém dados; "
                            "não é seguro descartá-los automaticamente.")
        with engine.begin() as conexao:
            if contribuicoes_antigas:
                conexao.execute(text("DROP TABLE contribuicoes"))
            if "arrecadacoes" in tabelas:
                conexao.execute(text("DROP TABLE arrecadacoes"))

    inspector = inspect(engine)
    if inspector.has_table("itens_doacao"):
        colunas = {c["name"]: c for c in inspector.get_columns("itens_doacao")}
        if "validade" not in colunas:
            with engine.begin() as conexao:
                conexao.execute(text("ALTER TABLE itens_doacao ADD COLUMN validade DATE"))
        elif not colunas["validade"]["nullable"]:
            if engine.dialect.name == "postgresql":
                with engine.begin() as conexao:
                    conexao.execute(text("ALTER TABLE itens_doacao ALTER COLUMN validade DROP NOT NULL"))
            elif engine.dialect.name == "sqlite":
                with engine.connect() as conexao:
                    conexao.exec_driver_sql("PRAGMA foreign_keys=OFF")
                    conexao.commit()
                    try:
                        with conexao.begin():
                            conexao.exec_driver_sql("""CREATE TABLE itens_doacao_nova (
                                id INTEGER PRIMARY KEY,
                                doacao_id INTEGER NOT NULL REFERENCES doacoes(id) ON DELETE CASCADE,
                                nome VARCHAR(100) NOT NULL,
                                categoria VARCHAR(50) NOT NULL,
                                quantidade NUMERIC(10,2) NOT NULL,
                                unidade_medida VARCHAR(20) NOT NULL,
                                validade DATE,
                                CONSTRAINT ck_itens_doacao_quantidade CHECK (quantidade > 0),
                                CONSTRAINT uq_itens_doacao_id_doacao_id UNIQUE (id, doacao_id)
                            )""")
                            campos = "id, doacao_id, nome, categoria, quantidade, unidade_medida, validade"
                            conexao.exec_driver_sql(
                                f"INSERT INTO itens_doacao_nova ({campos}) SELECT {campos} FROM itens_doacao")
                            conexao.exec_driver_sql("DROP TABLE itens_doacao")
                            conexao.exec_driver_sql("ALTER TABLE itens_doacao_nova RENAME TO itens_doacao")
                    finally:
                        conexao.exec_driver_sql("PRAGMA foreign_keys=ON")
                        conexao.commit()
                    violacoes = conexao.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                    if violacoes:
                        raise RuntimeError(f"Migração de itens deixou referências inválidas: {violacoes}")
    Contribuicao.__table__.create(engine, checkfirst=True)


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
                        estabelecimento_id INTEGER REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
                        doador_id INTEGER REFERENCES doadores(id) ON DELETE RESTRICT,
                        retirada_endereco VARCHAR(200),
                        retirada_municipio VARCHAR(80),
                        retirada_uf VARCHAR(2),
                        data_cadastro DATETIME,
                        data_limite_retirada DATETIME NOT NULL,
                        status VARCHAR(20),
                        CONSTRAINT ck_doacoes_uma_origem CHECK (
                            (estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)),
                        CONSTRAINT ck_doacoes_status CHECK (
                            status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA'))
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
    # A checagem de perda de dados antecede qualquer alteração do esquema.
    inspector = inspect(engine)
    tabelas = set(inspector.get_table_names())
    if "arrecadacoes" in tabelas or ("contribuicoes" in tabelas and
        "arrecadacao_id" in {c["name"] for c in inspector.get_columns("contribuicoes")}):
        with engine.connect() as conexao:
            for tabela in ("arrecadacoes", "contribuicoes"):
                if tabela in tabelas and conexao.execute(text(f"SELECT COUNT(*) FROM {tabela}")).scalar():
                    raise RuntimeError(f"Migração de pedidos interrompida: {tabela} contém dados.")
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
    if engine.dialect.name == "postgresql":
        _migrar_chave_item_postgresql(engine)
    _migrar_pedidos(engine)
    _migrar_indices(engine)
    if engine.dialect.name == "postgresql":
        _migrar_integridade_postgresql(engine)
