"""Sessão por cookie e autenticação dos dois tipos de doador."""

import os
import re
import secrets
import threading
import time
from pathlib import Path

from flask import request, session
from flask_restx import Namespace, Resource, fields
from sqlalchemy import func
from werkzeug.security import check_password_hash

from cnpj_service import formatar_cnpj
from models import Doador, Estabelecimento, db


ns = Namespace("auth", description="Entrada, saída e sessão do usuário")
_falhas = {}
_falhas_lock = threading.Lock()
JANELA_FALHAS = 15 * 60
LIMITE_FALHAS = 5

login_entrada = ns.model("LoginEntrada", {
    "identificador": fields.String(required=True, description="E-mail, CNPJ ou CPF"),
    "senha": fields.String(required=True),
})
me_model = ns.model("UsuarioAutenticado", {
    "tipo": fields.String, "id": fields.Integer, "nome": fields.String,
    "email": fields.String, "telefone": fields.String,
    "cnpj_formatado": fields.String, "endereco": fields.String,
    "cpf_formatado": fields.String,
})
login_saida = ns.model("LoginSaida", {"usuario": fields.Nested(me_model)})
erro_model = ns.model("AuthErro", {
    "codigo": fields.String, "mensagem": fields.String, "campos": fields.Raw,
})


def configurar_chave_secreta(app):
    """Usa o ambiente ou uma chave local estável, fora do controle de versão."""
    chave = os.getenv("SECRET_KEY")
    if not chave:
        caminho = Path(app.instance_path) / "secret_key"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        try:
            chave = caminho.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            chave = secrets.token_hex(32)
            try:
                with caminho.open("x", encoding="ascii") as arquivo:
                    arquivo.write(chave)
            except FileExistsError:
                chave = caminho.read_text(encoding="ascii").strip()
    app.config["SECRET_KEY"] = chave
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def iniciar_sessao(tipo, usuario_id):
    session.clear()
    session["tipo"] = tipo
    session["usuario_id"] = usuario_id
    session["nonce"] = secrets.token_hex(16)


def usuario_atual():
    tipo = session.get("tipo")
    usuario_id = session.get("usuario_id")
    if type(usuario_id) is not int:
        return None
    if tipo == "empresa":
        usuario = db.session.get(Estabelecimento, usuario_id)
    elif tipo == "doador":
        usuario = db.session.get(Doador, usuario_id)
    else:
        return None
    return (tipo, usuario) if usuario else None


def dados_usuario(tipo, usuario):
    dados = {"tipo": tipo, "id": usuario.id, "nome": usuario.nome,
             "email": usuario.email, "telefone": usuario.telefone}
    if tipo == "empresa":
        cnpj = re.sub(r"\D", "", usuario.cnpj)
        dados.update(cnpj_formatado=formatar_cnpj(cnpj), endereco=usuario.endereco)
    else:
        cpf = usuario.cpf
        dados["cpf_formatado"] = f"***.{cpf[3:6]}.{cpf[6:9]}-**"
    return dados


def _chave_identificador(identificador):
    identificador = identificador.strip().lower()
    if "@" in identificador:
        return identificador
    if re.fullmatch(r"[0-9]+|[0-9.\-/]+", identificador):
        digitos = re.sub(r"\D", "", identificador)
        if len(digitos) in (11, 14):
            return digitos
    return identificador


def _buscar_identificador(chave):
    if "@" in chave:
        empresa = Estabelecimento.query.filter(func.lower(Estabelecimento.email) == chave).first()
        if empresa:
            return "empresa", empresa
        doador = Doador.query.filter(func.lower(Doador.email) == chave).first()
        return ("doador", doador) if doador else None
    if len(chave) == 14 and chave.isascii() and chave.isdigit():
        empresa = Estabelecimento.query.filter(Estabelecimento.cnpj.in_((chave, formatar_cnpj(chave)))).first()
        return ("empresa", empresa) if empresa else None
    if len(chave) == 11 and chave.isascii() and chave.isdigit():
        doador = Doador.query.filter_by(cpf=chave).first()
        return ("doador", doador) if doador else None
    return None


def _bloqueado(chave):
    agora = time.monotonic()
    with _falhas_lock:
        recentes = [instante for instante in _falhas.get(chave, []) if agora - instante < JANELA_FALHAS]
        if recentes:
            _falhas[chave] = recentes
        else:
            _falhas.pop(chave, None)
        return len(recentes) >= LIMITE_FALHAS


def _registrar_falha(chave):
    with _falhas_lock:
        _falhas.setdefault(chave, []).append(time.monotonic())


def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


@ns.route("/login")
class Login(Resource):
    @ns.expect(login_entrada)
    @ns.response(200, "Sessão iniciada", login_saida)
    @ns.response(400, "Dados inválidos", erro_model)
    @ns.response(401, "Credenciais inválidas", erro_model)
    @ns.response(429, "Muitas tentativas", erro_model)
    def post(self):
        """Entra por e-mail, CNPJ ou CPF."""
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        identificador = corpo.get("identificador")
        senha = corpo.get("senha")
        campos = {}
        if not isinstance(identificador, str) or not identificador.strip() or len(identificador.strip()) > 254:
            campos["identificador"] = "Informe um e-mail, CNPJ ou CPF."
        if not isinstance(senha, str) or not senha:
            campos["senha"] = "Informe sua senha."
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        chave = _chave_identificador(identificador)
        if _bloqueado(chave):
            return _erro("MUITAS_TENTATIVAS", "Aguarde 15 minutos antes de tentar novamente.", 429)
        encontrado = _buscar_identificador(chave)
        if not encontrado or not encontrado[1].senha_hash or not check_password_hash(encontrado[1].senha_hash, senha):
            _registrar_falha(chave)
            return _erro("CREDENCIAIS_INVALIDAS", "Identificador ou senha inválidos.", 401)
        with _falhas_lock:
            _falhas.pop(chave, None)
        tipo, usuario = encontrado
        iniciar_sessao(tipo, usuario.id)
        return {"usuario": dados_usuario(tipo, usuario)}, 200


@ns.route("/logout")
class Logout(Resource):
    @ns.response(204, "Sessão encerrada")
    def post(self):
        """Encerra a sessão atual."""
        session.clear()
        return "", 204


@ns.route("/me")
class Me(Resource):
    @ns.response(200, "Usuário atual", me_model)
    @ns.response(401, "Não autenticado", erro_model)
    def get(self):
        """Retorna o perfil mínimo da sessão atual."""
        atual = usuario_atual()
        if not atual:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        return dados_usuario(*atual), 200
