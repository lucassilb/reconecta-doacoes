import os
from flask import Flask
from flask_restx import Api
from dotenv import load_dotenv
from models import db 

load_dotenv()

app = Flask(__name__)

# 2. Configura a conexão com o PostgreSQL local
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

api = Api(
    app,
    version="1.0",
    title="ReConecta API",
    description="API REST da plataforma ReConecta para redistribuição de excedentes alimentares",
    doc="/swagger"
)

from Estabelecimentos import ns as estabelecimentos_ns
from Instituicoes import ns as instituicoes_ns
from Doacoes import ns as doacoes_ns

api.add_namespace(estabelecimentos_ns, path="/reconecta/estabelecimentos")
api.add_namespace(instituicoes_ns, path="/reconecta/instituicoes")
api.add_namespace(doacoes_ns, path="/reconecta/doacoes")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)