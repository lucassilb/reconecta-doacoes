"""Sessão por cookie e autenticação dos dois tipos de doador."""

import os
import json
import logging
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import request, session
from flask_restx import Namespace, Resource, fields
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from cnpj_service import formatar_cnpj
from models import Doador, Estabelecimento, db
from pii import ip_reduzido
from registro import neutralizar_controles
from privacidade import (anonimizar_conta, consentimento_registrado,
                         conta_removida, exportar_dados)


ns = Namespace("auth", description="Entrada, saída e sessão do usuário")
_auditoria = logging.getLogger("reconecta.auditoria")
_auditoria.setLevel(logging.INFO)
_auditoria.propagate = False
if not _auditoria.handlers:
    _saida_auditoria = logging.StreamHandler(sys.stdout)
    _saida_auditoria.setFormatter(logging.Formatter("%(message)s"))
    _auditoria.addHandler(_saida_auditoria)


def registrar_auditoria(evento, resultado, *, tipo=None, ator_id=None):
    """Emite somente metadados de segurança, sem dados pessoais nem payloads.

    O IP sai truncado (/24 no IPv4, /48 no IPv6): basta para ver rajadas de tentativas
    vindas da mesma rede sem identificar a pessoa."""
    _auditoria.info(json.dumps({
        "data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evento": evento, "ator_tipo": tipo, "ator_id": ator_id,
        "ip": neutralizar_controles(ip_reduzido(request.remote_addr)), "resultado": resultado,
    }, ensure_ascii=False, separators=(",", ":")))

_falhas = {}
_falhas_lock = threading.Lock()
JANELA_FALHAS = 15 * 60
LIMITE_FALHAS = 5
# Hash fictício verificado quando o identificador não existe: quem não tem conta
# paga o mesmo custo de verificação de quem tem, e o tempo de resposta não revela
# se o e-mail, CPF ou CNPJ está cadastrado.
_HASH_FICTICIO = generate_password_hash("senha-ficticia-para-tempo-constante")

login_entrada = ns.model("LoginEntrada", {
    "identificador": fields.String(required=True, description="E-mail, CNPJ ou CPF"),
    "senha": fields.String(required=True),
})
me_model = ns.model("UsuarioAutenticado", {
    "tipo": fields.String, "id": fields.Integer, "nome": fields.String,
    "email": fields.String, "telefone": fields.String,
    "cnpj_formatado": fields.String, "endereco": fields.String,
    "cpf_formatado": fields.String,
    "perfis": fields.List(fields.String),
    "consentimento": fields.Raw,
})


def perfis_estabelecimento(usuario):
    perfis = []
    if usuario.sem_fins_lucrativos:
        perfis.append("ong")
    if usuario.atividade_alimentar:
        perfis.append("empresa_alimentos")
    return perfis
me_atualizar_entrada = ns.model("AtualizarPerfilEntrada", {
    "nome": fields.String(description="Apenas doador; 3 a 100 caracteres"),
    "email": fields.String(description="E-mail válido e único; até 100 caracteres"),
    "telefone": fields.String(description="DDD e telefone, 10 ou 11 dígitos"),
    "senha_atual": fields.String(description="Obrigatória junto com nova_senha"),
    "nova_senha": fields.String(description="Mínimo 8 caracteres, com letra e número"),
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


def iniciar_sessao(tipo, usuario):
    session.clear()
    session["tipo"] = tipo
    session["usuario_id"] = usuario.id
    session["nonce"] = secrets.token_hex(16)
    session["sv"] = usuario.sessao_versao or 0


def sessao_expirada(usuario):
    """True quando o cookie tem geração divergente da gravada (logout, troca de
    senha ou exclusão derrubam as demais). Cookies antigos sem a geração seguem
    valendo até expirar no navegador — a checagem só se aplica às sessões novas."""
    versao = session.get("sv")
    return versao is not None and versao != (usuario.sessao_versao or 0)


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
    # Conta anonimizada perde a sessão em qualquer navegador.
    if not usuario or conta_removida(usuario) or sessao_expirada(usuario):
        return None
    return tipo, usuario


def dados_usuario(tipo, usuario):
    dados = {"tipo": tipo, "id": usuario.id, "nome": usuario.nome,
             "email": usuario.email, "telefone": usuario.telefone,
             "consentimento": consentimento_registrado(usuario)}
    if tipo == "empresa":
        cnpj = re.sub(r"\D", "", usuario.cnpj)
        dados.update(cnpj_formatado=formatar_cnpj(cnpj), endereco=usuario.endereco,
                     perfis=perfis_estabelecimento(usuario))
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
            registrar_auditoria("login", "falha")
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        chave = _chave_identificador(identificador)
        if _bloqueado(chave):
            registrar_auditoria("login", "bloqueado")
            return _erro("MUITAS_TENTATIVAS", "Aguarde 15 minutos antes de tentar novamente.", 429)
        encontrado = _buscar_identificador(chave)
        alvo = encontrado[1].senha_hash if encontrado and encontrado[1].senha_hash else _HASH_FICTICIO
        if not check_password_hash(alvo, senha) or not encontrado or not encontrado[1].senha_hash:
            _registrar_falha(chave)
            registrar_auditoria("login", "falha")
            return _erro("CREDENCIAIS_INVALIDAS", "Identificador ou senha inválidos.", 401)
        with _falhas_lock:
            _falhas.pop(chave, None)
        tipo, usuario = encontrado
        iniciar_sessao(tipo, usuario)
        registrar_auditoria("login", "ok", tipo=tipo, ator_id=usuario.id)
        return {"usuario": dados_usuario(tipo, usuario)}, 200


@ns.route("/logout")
class Logout(Resource):
    @ns.response(204, "Sessão encerrada")
    def post(self):
        """Encerra a sessão atual e invalida os cookies emitidos para a conta."""
        registrar_auditoria("logout", "ok", tipo=session.get("tipo"),
                            ator_id=session.get("usuario_id"))
        atual = usuario_atual()
        if atual:
            # geração nova: o cookie desta sessão (e os das outras) morre de vez
            atual[1].sessao_versao = (atual[1].sessao_versao or 0) + 1
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
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

    @ns.expect(me_atualizar_entrada)
    @ns.response(200, "Perfil atualizado", me_model)
    @ns.response(400, "Dados inválidos", erro_model)
    @ns.response(401, "Não autenticado", erro_model)
    @ns.response(409, "E-mail já cadastrado", erro_model)
    def put(self):
        """Atualiza contatos e, para doadores, nome; pode trocar a senha."""
        atual = usuario_atual()
        if not atual:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        tipo, usuario = atual
        corpo = request.get_json(silent=True)
        if not isinstance(corpo, dict) or not corpo:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400,
                         campos={"corpo": "Informe ao menos um campo para atualizar."})

        # Mesmas regras de entrada usadas no cadastro, sem importar Cadastro no
        # topo deste módulo (Cadastro usa iniciar_sessao de Auth).
        from Cadastro import _email, _email_cadastrado, _senha_valida, _telefone

        permitidos = {"email", "telefone", "senha_atual", "nova_senha"}
        if tipo == "doador":
            permitidos.add("nome")
        campos = {chave: "Campo não permitido para este perfil."
                  for chave in corpo if chave not in permitidos}
        if "nome" in corpo and tipo == "doador":
            nome = corpo["nome"]
            if not isinstance(nome, str) or not 3 <= len(nome.strip()) <= 100:
                campos["nome"] = "Informe um nome entre 3 e 100 caracteres."
        if "email" in corpo and not _email(corpo["email"]):
            campos["email"] = "Informe um e-mail válido de até 100 caracteres."
        if "telefone" in corpo and not _telefone(corpo["telefone"]):
            campos["telefone"] = "Informe um telefone com DDD e 10 ou 11 dígitos."
        trocando_senha = "senha_atual" in corpo or "nova_senha" in corpo
        if trocando_senha:
            senha_atual = corpo.get("senha_atual")
            if (not isinstance(senha_atual, str) or not senha_atual or
                    not usuario.senha_hash or
                    not check_password_hash(usuario.senha_hash, senha_atual)):
                campos["senha_atual"] = "Informe a senha atual correta."
            if not _senha_valida(corpo.get("nova_senha")):
                campos["nova_senha"] = "Use pelo menos 8 caracteres, com uma letra e um número."
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400,
                         campos=campos)

        if "email" in corpo:
            email = corpo["email"].strip().lower()
            if email != usuario.email.lower() and _email_cadastrado(email):
                return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
            usuario.email = email
        if "telefone" in corpo:
            usuario.telefone = _telefone(corpo["telefone"])
        if "nome" in corpo and tipo == "doador":
            usuario.nome = corpo["nome"].strip()
        if trocando_senha:
            usuario.senha_hash = generate_password_hash(corpo["nova_senha"])
            # sessões antigas (outros navegadores) morrem; esta continua
            usuario.sessao_versao = (usuario.sessao_versao or 0) + 1
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
        if trocando_senha:
            session["sv"] = usuario.sessao_versao
        registrar_auditoria("dados_editados", "ok", tipo=tipo, ator_id=usuario.id)
        if trocando_senha:
            registrar_auditoria("senha_trocada", "ok", tipo=tipo, ator_id=usuario.id)
        return dados_usuario(tipo, usuario), 200

    @ns.response(204, "Conta excluída e dados anonimizados")
    @ns.response(401, "Não autenticado", erro_model)
    def delete(self):
        """Exclui a conta por anonimização, preservando a estatística agregada.

        Pedidos, doações e excedentes ficam sem identificação do titular.
        """
        atual = usuario_atual()
        if not atual:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        tipo, usuario = atual
        # a geração sobe junto com a anonimização: cookies desta conta morrem
        usuario.sessao_versao = (usuario.sessao_versao or 0) + 1
        anonimizar_conta(tipo, usuario)
        registrar_auditoria("conta_removida", "ok", tipo=tipo, ator_id=usuario.id)
        session.clear()
        return "", 204


@ns.route("/me/dados")
class MeusDados(Resource):
    @ns.response(200, "Cópia dos dados pessoais e registros da conta")
    @ns.response(401, "Não autenticado", erro_model)
    def get(self):
        """Exporta os dados da conta em JSON, para portabilidade pela LGPD.

        Cópia completa do cadastro e dos registros do titular (artigo 18).
        """
        atual = usuario_atual()
        if not atual:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        tipo, usuario = atual
        registrar_auditoria("dados_exportados", "ok", tipo=tipo, ator_id=usuario.id)
        return exportar_dados(tipo, usuario), 200
