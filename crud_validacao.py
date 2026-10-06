"""Validação de entrada para os CRUDs legados, sem alterar respostas de sucesso."""

from datetime import datetime

from flask import request

import cnpj_service
from models import Estabelecimento, db


def corpo_json():
    dado = request.get_json(silent=True)
    return dado if isinstance(dado, dict) else None


def erro_campos(campos):
    return {"codigo": "DADOS_INVALIDOS", "mensagem": "Corrija os campos indicados.",
            "campos": campos}, 400


def erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


def verificar_cnpj(valor, *, alimentar):
    """Aplica a mesma consulta e os mesmos critérios de aptidão do cadastro."""
    digitos = cnpj_service.validar_cnpj(valor)
    if not digitos:
        return None, erro("CNPJ_INVALIDO", "Informe um CNPJ válido.", 400)
    try:
        dados = cnpj_service.consultar_cnpj(digitos)
    except cnpj_service.ConsultaCNPJError as falha:
        return None, erro(falha.codigo, falha.mensagem, falha.status)
    motivos = []
    if not dados.get("ativo"):
        motivos.append({"codigo": "CNPJ_INATIVO",
                        "mensagem": f"CNPJ com situação {dados.get('situacao')}; a empresa precisa estar ativa."})
    if alimentar and not dados.get("relacionado_alimentacao"):
        motivos.append({"codigo": "SEM_RELACAO_ALIMENTAR",
                        "mensagem": "As atividades da empresa não têm relação com alimentação ou doação de alimentos."})
    if motivos:
        tipo = "EMPRESA_NAO_APTA" if alimentar else "INSTITUICAO_NAO_APTA"
        return None, erro(tipo, "Este CNPJ não atende aos critérios de cadastro.",
                          422, motivos=motivos)
    return digitos, None


def validar_contato(dado, *, criar):
    from Cadastro import _email, _telefone

    if dado is None:
        return {"corpo": "Envie um objeto JSON."}
    campos = {}
    for nome, tamanho in (("nome", 100), ("cnpj", 18), ("email", 100),
                          ("telefone", 20), ("endereco", None)):
        if nome not in dado:
            if criar and nome != "telefone":
                campos[nome] = "Campo obrigatório."
            continue
        valor = dado[nome]
        if not isinstance(valor, str) or (nome != "telefone" and not valor.strip()) or (
                nome != "email" and tamanho is not None and len(valor) > tamanho):
            campos[nome] = "Informe um texto válido."
        elif nome == "email" and not _email(valor):
            campos[nome] = "Informe um email válido."
        elif nome == "telefone" and valor and not _telefone(valor):
            campos[nome] = "Informe um telefone com DDD e 10 ou 11 dígitos."
    return campos


def validar_doacao(dado, *, criar):
    if dado is None:
        return {"corpo": "Envie um objeto JSON."}, None
    campos = {}
    prazo = None
    for nome in ("estabelecimento_id", "data_limite_retirada"):
        if criar and nome not in dado:
            campos[nome] = "Campo obrigatório."
    if "estabelecimento_id" in dado:
        ident = dado["estabelecimento_id"]
        if isinstance(ident, bool) or not isinstance(ident, int) or ident <= 0:
            campos["estabelecimento_id"] = "Informe um ID inteiro positivo."
        elif db.session.get(Estabelecimento, ident) is None:
            campos["estabelecimento_id"] = "Estabelecimento não encontrado."
    if "data_limite_retirada" in dado:
        valor = dado["data_limite_retirada"]
        try:
            if not isinstance(valor, str):
                raise ValueError
            prazo = datetime.fromisoformat(valor)
            if prazo.tzinfo is not None:
                raise ValueError
        except ValueError:
            campos["data_limite_retirada"] = "Informe uma data e hora ISO sem fuso."
    if "status" in dado and (not isinstance(dado["status"], str) or
                              dado["status"] not in ("DISPONIVEL", "RESERVADA",
                                                     "RETIRADA")):
        campos["status"] = "Informe um status válido."
    return campos, prazo
