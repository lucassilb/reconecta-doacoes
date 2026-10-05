"""Pedidos criados por empresas e doações feitas por usuários autenticados."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import current_app, request
from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload
from Auth import usuario_atual
from Contribuicoes import serializar_contribuicao
from Publico import CATEGORIAS, UNIDADES, doacao_model, serializar_doacao
from models import Contribuicao, Doacao, ItemDoacao, db

ns = Namespace("painel", description="Pedidos e doações do usuário")
item_entrada = ns.model("ItemPedidoEntradaPainel", {
    "nome": fields.String(required=True), "categoria": fields.String(required=True),
    "quantidade": fields.Float(required=True), "unidade_medida": fields.String(required=True),
})
doacao_entrada = ns.model("PedidoEntradaPainel", {
    "receber_ate": fields.String(description="Data e hora ISO local"),
    "data_limite_retirada": fields.String(description="Alias anterior de receber_ate"),
    "itens": fields.List(fields.Nested(item_entrada), required=True),
})
doacao_saida = ns.inherit("PedidoPainel", doacao_model, {
    "contribuicoes": fields.List(fields.Raw),
})
erro_model = ns.model("PainelErro", {
    "codigo": fields.String, "mensagem": fields.String, "campos": fields.Raw,
})

def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status

def _usuario():
    atual = usuario_atual()
    if not atual:
        return None, _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
    return atual, None

def _empresa():
    atual, erro = _usuario()
    if erro:
        return None, erro
    if atual[0] != "empresa":
        return None, _erro("APENAS_EMPRESAS", "Somente empresas podem publicar pedidos.", 403)
    return atual[1], None

def _data_hora(valor):
    if not isinstance(valor, str):
        return None
    try:
        resultado = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return resultado if resultado.tzinfo is None else None

def _quantidade(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return (numero if numero.is_finite() and Decimal("0.01") <= numero <= Decimal("99999999.99")
            and numero == numero.quantize(Decimal("0.01")) else None)

def _validar_pedido(corpo):
    campos = {}
    limite = _data_hora(corpo.get("receber_ate", corpo.get("data_limite_retirada")))
    if not limite or limite <= datetime.now():
        campos["receber_ate"] = "Informe uma data e hora futuras."
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
        categoria = item.get("categoria")
        quantidade = _quantidade(item.get("quantidade"))
        unidade = item.get("unidade_medida")
        if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 100:
            campos[f"itens[{indice}].nome"] = "Informe um nome de até 100 caracteres."
        if categoria not in CATEGORIAS:
            campos[f"itens[{indice}].categoria"] = "Selecione uma categoria da lista."
        if quantidade is None:
            campos[f"itens[{indice}].quantidade"] = "Informe uma quantidade maior que zero, com até duas casas decimais."
        if unidade not in UNIDADES:
            campos[f"itens[{indice}].unidade_medida"] = "Selecione uma unidade da lista."
        if (isinstance(nome, str) and 1 <= len(nome.strip()) <= 100 and
                categoria in CATEGORIAS and quantidade is not None and unidade in UNIDADES):
            itens.append({"nome": nome.strip(), "categoria": categoria,
                          "quantidade": quantidade, "unidade_medida": unidade})
    return limite, itens, campos

@ns.route("/doacoes")
class DoacoesPainel(Resource):
    @ns.response(200, "Pedidos da empresa", [doacao_saida])
    def get(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        doacoes = Doacao.query.options(
            selectinload(Doacao.estabelecimento), selectinload(Doacao.itens),
            selectinload(Doacao.contribuicoes).selectinload(Contribuicao.item_doacao),
            selectinload(Doacao.contribuicoes).selectinload(Contribuicao.doador),
            selectinload(Doacao.contribuicoes).selectinload(Contribuicao.estabelecimento)
        ).filter_by(estabelecimento_id=empresa.id).order_by(
            Doacao.data_cadastro.desc(), Doacao.id.desc()).all()
        resultado = []
        for doacao in doacoes:
            dados = serializar_doacao(doacao, incluir_status=True)
            dados["contribuicoes"] = [serializar_contribuicao(c) for c in doacao.contribuicoes]
            resultado.append(dados)
        return resultado, 200

    @ns.expect(doacao_entrada)
    @ns.response(201, "Pedido criado", doacao_saida)
    def post(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        limite, itens, campos = _validar_pedido(corpo)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        pedido = Doacao(estabelecimento_id=empresa.id, data_limite_retirada=limite,
                         status="DISPONIVEL")
        try:
            db.session.add(pedido)
            db.session.flush()
            db.session.add_all(ItemDoacao(doacao_id=pedido.id, **item) for item in itens)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao criar pedido")
            return _erro("ERRO_INTERNO", "Não foi possível criar o pedido.", 500)
        dados = serializar_doacao(pedido, incluir_status=True)
        dados["contribuicoes"] = []
        return dados, 201

@ns.route("/doacoes/<int:doacao_id>")
class DoacaoPainel(Resource):
    def delete(self, doacao_id):
        empresa, erro = _empresa()
        if erro:
            return erro
        pedido = Doacao.query.filter_by(id=doacao_id, estabelecimento_id=empresa.id).first()
        if not pedido:
            return _erro("PEDIDO_NAO_ENCONTRADO", "Pedido não encontrado.", 404)
        if pedido.status != "DISPONIVEL" or pedido.reservas or pedido.contribuicoes:
            return _erro("PEDIDO_NAO_REMOVIVEL", "Este pedido não pode ser removido.", 409)
        db.session.delete(pedido)
        db.session.commit()
        return "", 204

@ns.route("/minhas-doacoes")
class MinhasDoacoes(Resource):
    def get(self):
        atual, erro = _usuario()
        if erro:
            return erro
        tipo, usuario = atual
        filtro = ({"doador_id": usuario.id} if tipo == "doador" else
                  {"estabelecimento_id": usuario.id})
        contribuicoes = Contribuicao.query.options(
            selectinload(Contribuicao.item_doacao), selectinload(Contribuicao.doador),
            selectinload(Contribuicao.estabelecimento),
            selectinload(Contribuicao.doacao).selectinload(Doacao.estabelecimento)
        ).filter_by(**filtro).order_by(
            Contribuicao.criado_em.desc(), Contribuicao.id.desc()).all()
        return [serializar_contribuicao(c, entrega=True) for c in contribuicoes], 200
