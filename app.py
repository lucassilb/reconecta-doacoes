import os
import secrets
from urllib.parse import urlsplit
from flask import Flask, request, send_from_directory
from flask_restx import Api, Resource
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound, RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from models import db
from Auth import configurar_chave_secreta
from migracoes import aplicar_migracoes
from registro import configurar_logs, neutralizar_controles

load_dotenv()

app = Flask(__name__)
# log mínimo: máscara de dados pessoais em todo log do processo (registro.py)
configurar_logs(app)

def _database_url(valor):
    # painéis de nuvem costumam colar a URL com espaço ou quebra de linha no fim
    valor = (valor or "").strip()
    if not valor:
        return "sqlite:///reconecta.db"
    if valor.startswith("postgres://"):
        valor = "postgresql://" + valor[len("postgres://"):]
    url = make_url(valor)
    if url.drivername in ("postgresql", "postgresql+psycopg"):
        parametros = dict(url.query)
        if url.host not in ("localhost", "127.0.0.1", "::1", "db"):
            parametros["sslmode"] = "require"
        return url.set(drivername="postgresql+psycopg", query=parametros).render_as_string(hide_password=False)
    return valor


app.config["SQLALCHEMY_DATABASE_URI"] = _database_url(os.getenv("DATABASE_URL"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# hide_parameters: erros do banco não levam valores (e-mail, CPF, endereço) para o log
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "hide_parameters": True}
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024  # foto até 5 MB + campos do questionário
app.config["ERROR_INCLUDE_MESSAGE"] = False  # erros RESTX usam codigo/mensagem da API
configurar_chave_secreta(app)
if os.getenv("COOKIE_SEGURO") == "1":
    app.config["SESSION_COOKIE_SECURE"] = True
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

db.init_app(app)

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _origem_aceita():
    """Escritas por cookie exigem Origin/Referer da própria origem (anti-CSRF).

    Sem o cabeçalho a requisição passa (scripts e clientes de API não mandam
    Origin; o SameSite=Lax continua protegendo o navegador). Com ele, o host
    precisa ser o do serviço — ou qualquer loopback no desenvolvimento local."""
    origem = request.headers.get("Origin") or request.headers.get("Referer")
    if origem is None:
        return True
    try:
        partes = urlsplit(origem)
    except ValueError:
        return False
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return False
    alvo = urlsplit("//" + request.host).hostname or ""
    return partes.hostname == alvo or (partes.hostname in _LOOPBACK
                                     and alvo in _LOOPBACK)


@app.before_request
def conferir_origem_escrita():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    if not _origem_aceita():
        return {"codigo": "ORIGEM_RECUSADA",
                "mensagem": "Origem da requisição não corresponde ao site."}, 403
    return None


_CSP = (
    "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
    "form-action 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' https://fonts.googleapis.com; style-src-attr 'unsafe-inline'; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; connect-src 'self'; "
    "media-src 'self'; worker-src 'none'"
)
_SWAGGER_INLINE_SCRIPT = b'<script type="text/javascript">'


@app.after_request
def cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "DENY"
    resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resposta.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    resposta.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    if request.path.startswith("/reconecta/"):
        cache = resposta.headers.get("Cache-Control", "")
        if "no-store" not in cache.lower():
            resposta.headers["Cache-Control"] = f"{cache}, no-store".strip(", ")
    resposta.headers["Permissions-Policy"] = (
        "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
    csp = _CSP
    if request.path == "/swagger" and resposta.status_code == 200 and resposta.mimetype == "text/html":
        # Flask-RESTX inicializa o Swagger UI em um único script inline.
        # O nonce autoriza só esse script nesta resposta, sem liberar inline no site.
        corpo = resposta.get_data()
        if corpo.count(_SWAGGER_INLINE_SCRIPT) == 1:
            nonce = secrets.token_urlsafe(24)
            marcado = f'<script type="text/javascript" nonce="{nonce}">'.encode("ascii")
            resposta.set_data(corpo.replace(_SWAGGER_INLINE_SCRIPT, marcado, 1))
            csp = _CSP.replace("script-src 'self' https://cdn.jsdelivr.net;",
                               f"script-src 'self' https://cdn.jsdelivr.net 'nonce-{nonce}';")
    resposta.headers["Content-Security-Policy"] = csp
    if app.config["SESSION_COOKIE_SECURE"]:
        resposta.headers["Strict-Transport-Security"] = "max-age=31536000"
    return resposta


@app.get("/")
def home_page():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/sobre")
def sobre_page():
    return send_from_directory(app.static_folder, "sobre.html")

@app.get("/privacidade")
def privacidade_page():
    return send_from_directory(app.static_folder, "privacidade.html")

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

@app.get("/excedentes/<int:excedente_id>")
def excedente_page(excedente_id):
    return send_from_directory(app.static_folder, "excedente.html")

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


class Saude(Resource):
    @api.doc(responses={200: "Aplicação e banco disponíveis",
                        503: "Banco indisponível"})
    def get(self):
        """Verifica a conexão com o banco para healthchecks."""
        try:
            db.session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            db.session.rollback()
            return {"status": "indisponivel", "banco": "indisponivel"}, 503
        return {"status": "ok", "banco": "ok"}, 200


api.add_resource(Saude, "/reconecta/saude")

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
    app.logger.exception("Falha em %s", neutralizar_controles(request.path), exc_info=erro)
    return _erro_api("ERRO_INTERNO", "Não foi possível concluir a solicitação.", 500)


@app.errorhandler(500)
def erro_interno(erro):
    if request.path.startswith("/reconecta/"):
        app.logger.exception("Falha em %s", neutralizar_controles(request.path), exc_info=erro)
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
from Excedentes import ns as excedentes_ns
from IA import ns as ia_ns
from TempoReal import ns as tempo_real_ns
from Rotas import ns as rotas_ns

api.add_namespace(estabelecimentos_ns, path="/reconecta/estabelecimentos")
api.add_namespace(instituicoes_ns, path="/reconecta/instituicoes")
api.add_namespace(doacoes_ns, path="/reconecta/doacoes")
api.add_namespace(cadastro_ns, path="/reconecta/cadastro")
api.add_namespace(auth_ns, path="/reconecta/auth")
api.add_namespace(publico_ns, path="/reconecta/publico")
api.add_namespace(painel_ns, path="/reconecta/painel")
api.add_namespace(contribuicoes_ns, path="/reconecta/contribuicoes")
api.add_namespace(dashboard_ns, path="/reconecta/dashboard")
api.add_namespace(excedentes_ns, path="/reconecta/excedentes")
api.add_namespace(ia_ns, path="/reconecta/ia")
api.add_namespace(tempo_real_ns, path="/reconecta")
api.add_namespace(rotas_ns, path="/reconecta/excedentes/rota")

with app.app_context():
    db.create_all()
    aplicar_migracoes()

if os.getenv("RECONECTA_IAST") == "1":
    from iast_sensor import instalar
    instalar(app, db)

if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_RUN_HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "5000")),
            debug=os.getenv("FLASK_DEBUG") == "1")
