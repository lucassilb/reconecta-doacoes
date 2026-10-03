"""Gestão das doações pelo titular autenticado."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import current_app, request
from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import SQLAlchemyError

from Auth import usuario_atual
from Publico import CATEGORIAS, UNIDADES, doacao_model, serializar_doacao
from models import Doacao, ItemDoacao, db


ns = Namespace("painel", description="Doações do titular autenticado")
item_entrada = ns.model("ItemDoacaoEntradaPainel", {
    "nome": fields.String(required=True), "categoria": fields.String(required=True),
    "quantidade": fields.Float(required=True), "unidade_medida": fields.String(required=True),
    "validade": fields.String(required=True, description="AAAA-MM-DD"),
})
retirada_entrada = ns.model("RetiradaEntradaPainel", {
    "endereco": fields.String(required=True),
    "municipio": fields.String(required=True),
    "uf": fields.String(required=True),
})
doacao_entrada = ns.model("DoacaoEntradaPainel", {
    "data_limite_retirada": fields.String(required=True, description="Data e hora ISO local"),
    "itens": fields.List(fields.Nested(item_entrada), required=True),
    "retirada": fields.Nested(retirada_entrada, description="Obrigatório para doador pessoa física"),
})
doacao_saida = ns.inherit("DoacaoPainel", doacao_model, {
    "status": fields.String, "retirada": fields.Nested(retirada_entrada),
})
erro_model = ns.model("PainelErro", {
    "codigo": fields.String, "mensagem": fields.String, "campos": fields.Raw,
})


def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


def _titular_autenticado():
    atual = usuario_atual()
    if not atual:
        return None, _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
    return atual, None


UFS = frozenset("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def _validar_retirada(corpo):
    retirada = corpo.get("retirada")
    retirada = retirada if isinstance(retirada, dict) else {}
    campos = {}
    for chave, minimo, maximo in (("endereco", 5, 200), ("municipio", 2, 80)):
        valor = retirada.get(chave)
        if not isinstance(valor, str) or not minimo <= len(valor.strip()) <= maximo:
            campos[f"retirada.{chave}"] = f"Informe entre {minimo} e {maximo} caracteres."
    uf = retirada.get("uf")
    if not isinstance(uf, str) or uf not in UFS:
        campos["retirada.uf"] = "Selecione uma UF válida."
    return ({chave: retirada[chave].strip() for chave in ("endereco", "municipio", "uf")}
            if not campos else None), campos


def _filtro_titular(tipo, usuario):
    return {"estabelecimento_id": usuario.id} if tipo == "empresa" else {"doador_id": usuario.id}


def _data_hora(valor):
    if not isinstance(valor, str):
        return None
    try:
        resultado = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return resultado if resultado.tzinfo is None else None


def _data(valor):
    if not isinstance(valor, str):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _quantidade(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return (numero if numero.is_finite() and Decimal("0.01") <= numero <= Decimal("99999999.99")
            and numero == numero.quantize(Decimal("0.01")) else None)


def _validar_doacao(corpo):
    campos = {}
    limite = _data_hora(corpo.get("data_limite_retirada"))
    if not limite or limite <= datetime.now():
        campos["data_limite_retirada"] = "Informe uma data e hora futuras."
    itens_raw = corpo.get("itens")
    if not isinstance(itens_raw, list) or not itens_raw:
        campos["itens"] = "Inclua pelo menos um item."
        return limite, [], campos
    itens = []
    for indice, item in enumerate(itens_raw):
        if not isinstance(item, dict):
            campos[f"itens[{indice}]"] = "Informe um item válido."
            continue
        nome = item.get("nome")
        if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 100:
            campos[f"itens[{indice}].nome"] = "Informe um nome de até 100 caracteres."
        categoria = item.get("categoria")
        if categoria not in CATEGORIAS:
            campos[f"itens[{indice}].categoria"] = "Selecione uma categoria da lista."
        quantidade = _quantidade(item.get("quantidade"))
        if quantidade is None:
            campos[f"itens[{indice}].quantidade"] = "Informe uma quantidade maior que zero, com até duas casas decimais."
        unidade = item.get("unidade_medida")
        if unidade not in UNIDADES:
            campos[f"itens[{indice}].unidade_medida"] = "Selecione uma unidade da lista."
        validade = _data(item.get("validade"))
        if validade is None or validade < date.today():
            campos[f"itens[{indice}].validade"] = "Informe uma validade igual ou posterior a hoje."
        elif limite and limite.date() > validade:
            campos[f"itens[{indice}].validade"] = "A validade deve ser igual ou posterior ao limite de retirada."
        if (isinstance(nome, str) and 1 <= len(nome.strip()) <= 100 and
                categoria in CATEGORIAS and quantidade is not None and
                unidade in UNIDADES and validade and validade >= date.today() and
                (not limite or limite.date() <= validade)):
            itens.append({"nome": nome.strip(), "categoria": categoria,
                          "quantidade": quantidade, "unidade_medida": unidade,
                          "validade": validade})
    return limite, itens, campos


@ns.route("/doacoes")
class DoacoesPainel(Resource):
    @ns.response(200, "Doações do titular", [doacao_saida])
    @ns.response(401, "Não autenticado", erro_model)
    def get(self):
        """Lista todas as doações do titular da sessão, inclusive encerradas."""
        titular, erro = _titular_autenticado()
        if erro:
            return erro
        tipo, usuario = titular
        doacoes = Doacao.query.filter_by(**_filtro_titular(tipo, usuario)).order_by(
            Doacao.data_cadastro.desc(), Doacao.id.desc()).all()
        return [serializar_doacao(doacao, incluir_status=True) for doacao in doacoes], 200

    @ns.expect(doacao_entrada)
    @ns.response(201, "Doação criada", doacao_saida)
    @ns.response(400, "Dados inválidos", erro_model)
    @ns.response(401, "Não autenticado", erro_model)
    def post(self):
        """Cria doação e itens juntos após validar quantidade, prazo e validade."""
        titular, erro = _titular_autenticado()
        if erro:
            return erro
        tipo, usuario = titular
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        limite, itens, campos = _validar_doacao(corpo)
        retirada = None
        if tipo == "doador":
            retirada, campos_retirada = _validar_retirada(corpo)
            campos.update(campos_retirada)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        doacao = Doacao(**_filtro_titular(tipo, usuario),
                        **({f"retirada_{chave}": valor for chave, valor in retirada.items()}
                           if retirada else {}),
                        data_limite_retirada=limite, status="DISPONIVEL")
        try:
            db.session.add(doacao)
            db.session.flush()
            db.session.add_all(ItemDoacao(doacao_id=doacao.id, **item) for item in itens)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao criar doação")
            return _erro("ERRO_INTERNO", "Não foi possível criar a doação.", 500)
        return serializar_doacao(doacao, incluir_status=True), 201


@ns.route("/doacoes/<int:doacao_id>")
class DoacaoPainel(Resource):
    @ns.response(204, "Doação removida")
    @ns.response(401, "Não autenticado", erro_model)
    @ns.response(404, "Não encontrada", erro_model)
    @ns.response(409, "Não removível", erro_model)
    def delete(self, doacao_id):
        """Remove apenas doação disponível, própria e sem reservas."""
        titular, erro = _titular_autenticado()
        if erro:
            return erro
        tipo, usuario = titular
        doacao = Doacao.query.filter_by(id=doacao_id, **_filtro_titular(tipo, usuario)).first()
        if not doacao:
            return _erro("DOACAO_NAO_ENCONTRADA", "Doação não encontrada.", 404)
        if doacao.status != "DISPONIVEL" or doacao.reservas:
            return _erro("DOACAO_NAO_REMOVIVEL", "Esta doação não pode ser removida.", 409)
        db.session.delete(doacao)
        db.session.commit()
        return "", 204
