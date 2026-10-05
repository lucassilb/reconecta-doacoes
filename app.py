import os
from flask import Flask, send_from_directory
from flask_restx import Api
from werkzeug.exceptions import RequestEntityTooLarge
from dotenv import load_dotenv
from models import db
from Auth import configurar_chave_secreta
from migracoes import aplicar_migracoes

load_dotenv()

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or "sqlite:///reconecta.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # foto até 5 MB + campos do questionário
configurar_chave_secreta(app)

db.init_app(app)

@app.get("/")
def home_page():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/sobre")
def sobre_page():
    return send_from_directory(app.static_folder, "sobre.html")

@app.get("/cadastro")
def cadastro_page():
    return send_from_directory(app.static_folder, "cadastro.html")

@app.get("/entrar")
def entrar_page():
    return send_from_directory(app.static_folder, "entrar.html")

@app.get("/painel")
def painel_page():
    return send_from_directory(app.static_folder, "painel.html")

@app.errorhandler(413)
def arquivo_grande(_erro):
    return {"codigo": "ARQUIVO_GRANDE", "mensagem": "O envio excede o limite de 6 MB.",
            "campos": {"foto": "Escolha uma foto de até 5 MB."}}, 413

api = Api(
    app,
    version="1.0",
    title="ReConecta API",
    description="API REST da plataforma ReConecta para redistribuição de excedentes alimentares",
    doc="/swagger"
)

@api.errorhandler(RequestEntityTooLarge)
def requisicao_grande(_erro):
    return {"codigo": "ARQUIVO_GRANDE", "mensagem": "O envio excede o limite de 6 MB.",
            "campos": {"foto": "Escolha uma foto de até 5 MB."}}, 413

from Estabelecimentos import ns as estabelecimentos_ns
from Instituicoes import ns as instituicoes_ns
from Doacoes import ns as doacoes_ns
from Cadastro import ns as cadastro_ns
from Auth import ns as auth_ns
from Publico import ns as publico_ns
from Painel import ns as painel_ns
from Contribuicoes import ns as contribuicoes_ns

api.add_namespace(estabelecimentos_ns, path="/reconecta/estabelecimentos")
api.add_namespace(instituicoes_ns, path="/reconecta/instituicoes")
api.add_namespace(doacoes_ns, path="/reconecta/doacoes")
api.add_namespace(cadastro_ns, path="/reconecta/cadastro")
api.add_namespace(auth_ns, path="/reconecta/auth")
api.add_namespace(publico_ns, path="/reconecta/publico")
api.add_namespace(painel_ns, path="/reconecta/painel")
api.add_namespace(contribuicoes_ns, path="/reconecta/contribuicoes")

with app.app_context():
    db.create_all()
    aplicar_migracoes()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG") == "1")
