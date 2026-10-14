"""Cria três contas fictícias apenas no SQLite efêmero de compose.dast.yml."""

import os

if (os.getenv("RECONECTA_DAST") != "1" or
        os.getenv("DATABASE_URL") != "sqlite:////tmp/reconecta-dast.sqlite"):
    raise SystemExit("Semente DAST permitida somente no SQLite efêmero do Compose")

from app import app
from models import Doador, Estabelecimento, db
from werkzeug.security import generate_password_hash


def main():
    with app.app_context():
        if Doador.query.filter_by(email="doador@dast.invalid").first():
            return
        senha = generate_password_hash("DastSenha123")
        db.session.add(Doador(nome="Doador Ficticio", cpf="52998224725",
                              email="doador@dast.invalid", telefone="11900000001",
                              senha_hash=senha))
        db.session.add(Estabelecimento(nome="Mercado Ficticio", cnpj="47508411000156",
                                       email="empresa@dast.invalid", telefone="11900000002",
                                       endereco="Endereco Ficticio 1", senha_hash=senha,
                                       sem_fins_lucrativos=False, atividade_alimentar=True))
        db.session.add(Estabelecimento(nome="ONG Ficticia", cnpj="11222333000181",
                                       email="ong@dast.invalid", telefone="11900000003",
                                       endereco="Endereco Ficticio 2", senha_hash=senha,
                                       sem_fins_lucrativos=True, atividade_alimentar=False))
        db.session.commit()


if __name__ == "__main__":
    main()
