"""Migrações pequenas e idempotentes para bancos criados antes do login."""

from sqlalchemy import inspect, text

from models import db


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
