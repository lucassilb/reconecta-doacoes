"""Cadastro validado de empresas alimentares e doadores pessoa física."""

import re

from flask import request
from flask_restx import Namespace, Resource, fields
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from Auth import iniciar_sessao
from cnpj_service import ConsultaCNPJError, consultar_cnpj, formatar_cnpj, validar_cnpj
from models import Doador, Estabelecimento, db


ns = Namespace("cadastro", description="Verificação de CNPJ e cadastro de doadores")

empresa_entrada = ns.model("CadastroEmpresaEntrada", {
    "cnpj": fields.String(required=True, description="CNPJ com ou sem máscara"),
    "email": fields.String(required=True),
    "telefone": fields.String(required=True, description="DDD e telefone, 10 ou 11 dígitos"),
    "senha": fields.String(required=True, description="Mínimo 8 caracteres, com letra e número"),
})
doador_entrada = ns.model("CadastroDoadorEntrada", {
    "nome": fields.String(required=True),
    "cpf": fields.String(required=True, description="CPF com ou sem máscara"),
    "email": fields.String(required=True),
    "telefone": fields.String(required=True),
    "senha": fields.String(required=True, description="Mínimo 8 caracteres, com letra e número"),
})
motivo_model = ns.model("CadastroMotivo", {
    "codigo": fields.String,
    "mensagem": fields.String,
})
atividade_model = ns.model("CadastroAtividade", {
    "codigo": fields.String,
    "descricao": fields.String,
    "categoria": fields.String,
})
endereco_model = ns.model("CadastroEndereco", {
    chave: fields.String for chave in
    ("logradouro", "numero", "complemento", "bairro", "municipio", "uf", "cep")
})
consulta_model = ns.model("ConsultaCNPJ", {
    "cnpj": fields.String,
    "cnpj_formatado": fields.String,
    "razao_social": fields.String,
    "nome_fantasia": fields.String,
    "situacao": fields.String,
    "ativo": fields.Boolean,
    "cnae_principal": fields.Nested(atividade_model),
    "atividades_alimentares": fields.List(fields.Nested(atividade_model)),
    "relacionado_alimentacao": fields.Boolean,
    "endereco": fields.Nested(endereco_model),
    "email": fields.String,
    "telefone": fields.String,
    "ja_cadastrado": fields.Boolean,
    "apto": fields.Boolean,
    "motivos": fields.List(fields.Nested(motivo_model)),
    "fonte": fields.String,
})
empresa_saida = ns.model("CadastroEmpresaSaida", {
    "id": fields.Integer, "tipo": fields.String, "nome": fields.String,
    "cnpj": fields.String, "cnpj_formatado": fields.String,
    "email": fields.String, "telefone": fields.String, "endereco": fields.String,
})
doador_saida = ns.model("CadastroDoadorSaida", {
    "id": fields.Integer, "tipo": fields.String, "nome": fields.String,
    "cpf_formatado": fields.String, "email": fields.String, "telefone": fields.String,
})
erro_model = ns.model("CadastroErro", {
    "codigo": fields.String, "mensagem": fields.String,
    "campos": fields.Raw, "motivos": fields.List(fields.Nested(motivo_model)),
})


def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


def _email(valor):
    if not isinstance(valor, str) or len(valor.strip()) > 100:
        return False
    email = valor.strip()
    if ".." in email or email.startswith(".") or ".@" in email:
        return False
    if re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", email) is None:
        return False
    return all(not parte.startswith("-") and not parte.endswith("-") for parte in email.split("@", 1)[1].split("."))


def _telefone(valor):
    if not isinstance(valor, str) or re.fullmatch(r"[+()0-9\s.\-]+", valor) is None:
        return None
    digitos = re.sub(r"\D", "", valor)
    return digitos if len(digitos) in (10, 11) else None


def _senha_valida(valor):
    return (isinstance(valor, str) and len(valor) >= 8 and
            any(caractere.isalpha() for caractere in valor) and
            any(caractere.isdigit() for caractere in valor))


def _cpf(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", valor.strip()):
        return None
    digitos = re.sub(r"\D", "", valor)
    if len(set(digitos)) == 1:
        return None
    for tamanho, pesos in ((9, range(10, 1, -1)), (10, range(11, 1, -1))):
        resto = sum(int(n) * peso for n, peso in zip(digitos[:tamanho], pesos)) % 11
        esperado = 0 if resto < 2 else 11 - resto
        if int(digitos[tamanho]) != esperado:
            return None
    return digitos


def _email_cadastrado(email):
    return (db.session.query(Estabelecimento.id).filter(func.lower(Estabelecimento.email) == email.lower()).first()
            or db.session.query(Doador.id).filter(func.lower(Doador.email) == email.lower()).first()) is not None


def _empresa_cadastrada(cnpj):
    return Estabelecimento.query.filter(
        Estabelecimento.cnpj.in_((cnpj, formatar_cnpj(cnpj)))).first() is not None


def _avaliar_empresa(dados):
    ja_cadastrado = _empresa_cadastrada(dados["cnpj"])
    motivos = []
    if not dados["ativo"]:
        motivos.append({"codigo": "CNPJ_INATIVO", "mensagem": f"CNPJ com situação {dados['situacao']}; a empresa precisa estar ativa."})
    if not dados["relacionado_alimentacao"]:
        motivos.append({"codigo": "SEM_RELACAO_ALIMENTAR", "mensagem": "As atividades da empresa não têm relação com alimentação ou doação de alimentos."})
    if ja_cadastrado:
        motivos.append({"codigo": "CNPJ_JA_CADASTRADO", "mensagem": "Este CNPJ já está cadastrado."})
    return {**dados, "ja_cadastrado": ja_cadastrado, "apto": not motivos, "motivos": motivos}


def _endereco_texto(endereco):
    logradouro = ", ".join(parte for parte in (endereco["logradouro"], endereco["numero"], endereco["complemento"]) if parte)
    local = ", ".join(parte for parte in (endereco["bairro"], endereco["municipio"]) if parte)
    if endereco["uf"]:
        local = f"{local}/{endereco['uf']}" if local else endereco["uf"]
    return " - ".join(parte for parte in (logradouro, local, endereco["cep"]) if parte) or "Não informado"


@ns.route("/cnpj/<path:cnpj>")
class ConsultaCNPJ(Resource):
    @ns.response(200, "Resultado da consulta", consulta_model)
    @ns.response(400, "CNPJ inválido", erro_model)
    @ns.response(404, "CNPJ não encontrado", erro_model)
    @ns.response(503, "Consulta indisponível", erro_model)
    def get(self, cnpj):
        """Consulta existência, situação e atividades do CNPJ."""
        try:
            return _avaliar_empresa(consultar_cnpj(cnpj)), 200
        except ConsultaCNPJError as erro:
            return _erro(erro.codigo, erro.mensagem, erro.status)


@ns.route("/empresa")
class CadastroEmpresa(Resource):
    @ns.expect(empresa_entrada)
    @ns.response(201, "Empresa cadastrada", empresa_saida)
    @ns.response(400, "Dados ou CNPJ inválidos", erro_model)
    @ns.response(404, "CNPJ não encontrado", erro_model)
    @ns.response(409, "CNPJ ou e-mail já cadastrado", erro_model)
    @ns.response(422, "Empresa não apta", erro_model)
    @ns.response(503, "Consulta indisponível", erro_model)
    def post(self):
        """Cadastra empresa ativa com atividade alimentar verificada na Receita."""
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        cnpj = validar_cnpj(corpo.get("cnpj"))
        if not cnpj:
            return _erro("CNPJ_INVALIDO", "Informe um CNPJ válido.", 400)
        campos = {}
        email = corpo.get("email")
        telefone = _telefone(corpo.get("telefone"))
        if not _email(email):
            campos["email"] = "Informe um e-mail válido de até 100 caracteres."
        if not telefone:
            campos["telefone"] = "Informe um telefone com DDD e 10 ou 11 dígitos."
        if not _senha_valida(corpo.get("senha")):
            campos["senha"] = "Use pelo menos 8 caracteres, com uma letra e um número."
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        email = email.strip().lower()
        try:
            dados = _avaliar_empresa(consultar_cnpj(cnpj))
        except ConsultaCNPJError as erro:
            return _erro(erro.codigo, erro.mensagem, erro.status)
        if dados["ja_cadastrado"]:
            return _erro("CNPJ_JA_CADASTRADO", "Este CNPJ já está cadastrado.", 409)
        if not dados["ativo"] or not dados["relacionado_alimentacao"]:
            return _erro("EMPRESA_NAO_APTA", "Esta empresa não atende aos critérios de cadastro.", 422, motivos=dados["motivos"])
        if _email_cadastrado(email):
            return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
        empresa = Estabelecimento(
            nome=(dados["nome_fantasia"] or dados["razao_social"])[:100],
            cnpj=cnpj, email=email, telefone=telefone,
            endereco=_endereco_texto(dados["endereco"]),
            senha_hash=generate_password_hash(corpo["senha"]),
        )
        db.session.add(empresa)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if _empresa_cadastrada(cnpj):
                return _erro("CNPJ_JA_CADASTRADO", "Este CNPJ já está cadastrado.", 409)
            return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
        iniciar_sessao("empresa", empresa.id)
        return {"id": empresa.id, "tipo": "empresa", "nome": empresa.nome,
                "cnpj": empresa.cnpj, "cnpj_formatado": formatar_cnpj(empresa.cnpj),
                "email": empresa.email, "telefone": empresa.telefone,
                "endereco": empresa.endereco}, 201


@ns.route("/doador")
class CadastroDoador(Resource):
    @ns.expect(doador_entrada)
    @ns.response(201, "Doador cadastrado", doador_saida)
    @ns.response(400, "Dados inválidos", erro_model)
    @ns.response(409, "CPF ou e-mail já cadastrado", erro_model)
    def post(self):
        """Cadastra pessoa física após verificar os dígitos do CPF."""
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        nome = corpo.get("nome")
        cpf = _cpf(corpo.get("cpf"))
        email = corpo.get("email")
        telefone = _telefone(corpo.get("telefone"))
        campos = {}
        if not isinstance(nome, str) or not 3 <= len(nome.strip()) <= 100:
            campos["nome"] = "Informe um nome entre 3 e 100 caracteres."
        if not cpf:
            campos["cpf"] = "Informe um CPF válido."
        if not _email(email):
            campos["email"] = "Informe um e-mail válido de até 100 caracteres."
        if not telefone:
            campos["telefone"] = "Informe um telefone com DDD e 10 ou 11 dígitos."
        if not _senha_valida(corpo.get("senha")):
            campos["senha"] = "Use pelo menos 8 caracteres, com uma letra e um número."
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        email = email.strip().lower()
        if Doador.query.filter_by(cpf=cpf).first():
            return _erro("CPF_JA_CADASTRADO", "Este CPF já está cadastrado.", 409)
        if _email_cadastrado(email):
            return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
        doador = Doador(nome=nome.strip(), cpf=cpf, email=email, telefone=telefone,
                        senha_hash=generate_password_hash(corpo["senha"]))
        db.session.add(doador)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if Doador.query.filter_by(cpf=cpf).first():
                return _erro("CPF_JA_CADASTRADO", "Este CPF já está cadastrado.", 409)
            return _erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
        iniciar_sessao("doador", doador.id)
        return {"id": doador.id, "tipo": "doador", "nome": doador.nome,
                "cpf_formatado": f"***.{cpf[3:6]}.{cpf[6:9]}-**",
                "email": doador.email, "telefone": doador.telefone}, 201
