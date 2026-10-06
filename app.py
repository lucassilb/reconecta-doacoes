import os
from flask import Flask, request, send_from_directory
from flask_restx import Api
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound, RequestEntityTooLarge
from dotenv import load_dotenv
from models import db
from Auth import configurar_chave_secreta
from migracoes import aplicar_migracoes

load_dotenv()

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL") or "sqlite:///reconecta.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # foto até 5 MB + campos do questionário
app.config["ERROR_INCLUDE_MESSAGE"] = False  # erros RESTX usam codigo/mensagem da API
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

@app.get("/dashboard")
def dashboard_page():
    return send_from_directory(app.static_folder, "dashboard.html")

@app.get("/doacoes/<int:doacao_id>")
def doacao_page(doacao_id):
    return send_from_directory(app.static_folder, "doacao.html")

@app.errorhandler(413)
def arquivo_grande(_erro):
    return {"codigo": "ARQUIVO_GRANDE", "mensagem": "O envio excede o limite de 6 MB.",
            "campos": {"foto": "Escolha uma foto de até 5 MB."}}, 413

api = Api(
    app,
    version="1.0",
    title="ReConecta API",
    description="API REST da plataforma ReConecta para redistribuição de excedentes alimentares",
    authorizations={"AdminToken": {"type": "apiKey", "in": "header", "name": "X-Admin-Token"}},
    doc="/swagger"
)

@api.errorhandler(RequestEntityTooLarge)
def requisicao_grande(_erro):
    return {"codigo": "ARQUIVO_GRANDE", "mensagem": "O envio excede o limite de 6 MB.",
            "campos": {"foto": "Escolha uma foto de até 5 MB."}}, 413


def _erro_api(codigo, mensagem, status):
    return {"codigo": codigo, "mensagem": mensagem}, status


@app.errorhandler(404)
def pagina_nao_encontrada(erro):
    if request.path.startswith("/reconecta/"):
        return _erro_api("NAO_ENCONTRADO", "Rota não encontrada.", 404)
    return erro


@api.errorhandler(NotFound)
def recurso_nao_encontrado(_erro):
    return _erro_api("NAO_ENCONTRADO", "Rota não encontrada.", 404)


@api.errorhandler(MethodNotAllowed)
def metodo_nao_permitido(_erro):
    return _erro_api("METODO_NAO_PERMITIDO", "Método não permitido.", 405)


@api.errorhandler(Exception)
def erro_api_interno(erro):
    if isinstance(erro, HTTPException) and 400 <= erro.code < 500:
        return _erro_api("REQUISICAO_INVALIDA", erro.description, erro.code)
    app.logger.exception("Falha em %s", request.path, exc_info=erro)
    return _erro_api("ERRO_INTERNO", "Não foi possível concluir a solicitação.", 500)


@app.errorhandler(500)
def erro_interno(erro):
    if request.path.startswith("/reconecta/"):
        app.logger.exception("Falha em %s", request.path, exc_info=erro)
        return _erro_api("ERRO_INTERNO", "Não foi possível concluir a solicitação.", 500)
    return erro

from Estabelecimentos import ns as estabelecimentos_ns
from Instituicoes import ns as instituicoes_ns
from Doacoes import ns as doacoes_ns
from Cadastro import ns as cadastro_ns
from Auth import ns as auth_ns
from Publico import ns as publico_ns
from Painel import ns as painel_ns
from Contribuicoes import ns as contribuicoes_ns
from Dashboard import ns as dashboard_ns
from IA import ns as ia_ns

api.add_namespace(estabelecimentos_ns, path="/reconecta/estabelecimentos")
api.add_namespace(instituicoes_ns, path="/reconecta/instituicoes")
api.add_namespace(doacoes_ns, path="/reconecta/doacoes")
api.add_namespace(cadastro_ns, path="/reconecta/cadastro")
api.add_namespace(auth_ns, path="/reconecta/auth")
api.add_namespace(publico_ns, path="/reconecta/publico")
api.add_namespace(painel_ns, path="/reconecta/painel")
api.add_namespace(contribuicoes_ns, path="/reconecta/contribuicoes")
api.add_namespace(dashboard_ns, path="/reconecta/dashboard")
api.add_namespace(ia_ns, path="/reconecta/ia")

with app.app_context():
    db.create_all()
    aplicar_migracoes()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG") == "1")
