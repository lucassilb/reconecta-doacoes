"""Validação de entrada para os CRUDs legados, sem alterar respostas de sucesso."""

from datetime import datetime

from flask import request

from models import Estabelecimento, db


def corpo_json():
    dado = request.get_json(silent=True)
    return dado if isinstance(dado, dict) else None


def erro_campos(campos):
    return {"codigo": "DADOS_INVALIDOS", "mensagem": "Corrija os campos indicados.",
            "campos": campos}, 400


def validar_contato(dado, *, criar):
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
                tamanho is not None and len(valor) > tamanho):
            campos[nome] = "Informe um texto válido."
        elif nome == "email" and ("@" not in valor or valor.startswith("@") or valor.endswith("@")):
            campos[nome] = "Informe um email válido."
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
