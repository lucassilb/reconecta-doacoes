"""Pedidos públicos de empresas e indicadores sem dados de contato."""
import re
from decimal import Decimal
from flask import request
from flask_restx import Namespace, Resource, fields
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from Auth import usuario_atual
from fuso import agora_brasilia_sem_fuso, iso_evento, iso_prazo
from models import Contribuicao, Doacao, Doador, Estabelecimento, Instituicao, ItemDoacao, db

ns = Namespace("publico", description="Resumo e pedidos disponíveis")
CATEGORIAS = ["Hortifrúti", "Padaria", "Laticínios", "Carnes e peixes",
              "Grãos e cereais", "Refeições prontas", "Bebidas não alcoólicas", "Outros"]
UNIDADES = ["kg", "g", "L", "unidade", "pacote", "caixa"]
resumo_model = ns.model("ResumoPublico", {
    "empresas": fields.Integer, "doadores": fields.Integer,
    "instituicoes": fields.Integer, "doacoes_disponiveis": fields.Integer,
    "itens_disponiveis": fields.Integer, "kg_disponiveis": fields.Float,
    "doacoes_recebidas": fields.Integer,
})
opcoes_model = ns.model("OpcoesDoacao", {
    "categorias": fields.List(fields.String), "unidades": fields.List(fields.String),
})
item_model = ns.model("ItemPedidoPublico", {
    "id": fields.Integer, "nome": fields.String, "categoria": fields.String,
    "quantidade": fields.Float, "unidade_medida": fields.String,
    "recebido": fields.Float, "faltam": fields.Float,
})
empresa_model = ns.model("EmpresaPedidoPublico", {
    "nome": fields.String, "municipio_uf": fields.String,
})
doacao_model = ns.model("PedidoPublico", {
    "id": fields.Integer, "empresa": fields.Nested(empresa_model),
    "data_cadastro": fields.String, "receber_ate": fields.String,
    "itens": fields.List(fields.Nested(item_model)),
    "doacoes_recebidas": fields.Integer, "status": fields.String,
})

def _municipio_uf(endereco):
    for parte in (endereco or "").split(" - "):
        candidato = parte.rsplit(",", 1)[-1].strip()
        if re.fullmatch(r"[^,/]+/[A-Za-z]{2}", candidato):
            return candidato
    return None

def serializar_doacao(doacao, incluir_status=False, detalhe=False):
    aceitas = [c for c in doacao.contribuicoes if c.status == "ACEITA"]
    itens = []
    for item in doacao.itens:
        recebido = sum((c.quantidade for c in aceitas if c.item_doacao_id == item.id), Decimal("0"))
        meta = Decimal(str(item.quantidade))
        itens.append({"id": item.id, "nome": item.nome, "categoria": item.categoria,
                      "quantidade": float(meta), "unidade_medida": item.unidade_medida,
                      "recebido": float(recebido), "faltam": float(max(meta - recebido, 0))})
    dados = {
        "id": doacao.id,
        "empresa": {"nome": doacao.estabelecimento.nome,
                    "municipio_uf": _municipio_uf(doacao.estabelecimento.endereco)},
        "data_cadastro": iso_evento(doacao.data_cadastro),
        "receber_ate": iso_prazo(doacao.data_limite_retirada),
        "itens": itens, "doacoes_recebidas": len(aceitas),
    }
    if incluir_status or detalhe:
        dados["status"] = doacao.status
    if detalhe:
        atual = usuario_atual()
        if not atual:
            motivo = "Entre para doar"
        elif atual[0] == "empresa" and atual[1].id == doacao.estabelecimento_id:
            motivo = "Este é o seu próprio pedido"
        elif doacao.status != "DISPONIVEL" or doacao.data_limite_retirada <= agora_brasilia_sem_fuso():
            motivo = "Pedido encerrado"
        else:
            motivo = None
        dados["pode_doar"] = motivo is None
        dados["motivo_bloqueio"] = motivo
    return dados

def _disponiveis():
    return Doacao.query.filter(Doacao.estabelecimento_id.isnot(None),
                               Doacao.status == "DISPONIVEL",
                               Doacao.data_limite_retirada > agora_brasilia_sem_fuso())


def _com_relacionamentos(query):
    return query.options(selectinload(Doacao.estabelecimento),
                         selectinload(Doacao.itens),
                         selectinload(Doacao.contribuicoes))


def _inteiro_positivo(campo, padrao, maximo):
    valor = request.args.get(campo, str(padrao))
    if not valor.isascii() or not valor.isdigit() or not 1 <= int(valor) <= maximo:
        return None
    return int(valor)

@ns.route("/resumo")
class Resumo(Resource):
    @ns.response(200, "Contadores públicos", resumo_model)
    def get(self):
        doacoes = _disponiveis().options(selectinload(Doacao.itens)).all()
        itens = [item for doacao in doacoes for item in doacao.itens]
        peso = sum((Decimal(str(item.quantidade)) *
                    (Decimal("0.001") if item.unidade_medida == "g" else Decimal("1"))
                    for item in itens if item.unidade_medida in ("kg", "g")), Decimal("0"))
        return {
            "empresas": db.session.query(Estabelecimento.id).count(),
            "doadores": db.session.query(Doador.id).count(),
            "instituicoes": db.session.query(Instituicao.id).count(),
            "doacoes_disponiveis": len(doacoes),
            "itens_disponiveis": len(itens), "kg_disponiveis": float(peso),
            "doacoes_recebidas": Contribuicao.query.filter_by(status="ACEITA").count(),
        }, 200

@ns.route("/doacoes")
class DoacoesPublicas(Resource):
    @ns.response(200, "Pedidos disponíveis", [doacao_model])
    def get(self):
        pagina = _inteiro_positivo("pagina", 1, 1000000)
        campo_tamanho = "por_pagina" if "por_pagina" in request.args else "limite"
        tamanho = _inteiro_positivo(campo_tamanho, 8, 50 if campo_tamanho == "por_pagina" else 100)
        campos = {}
        if pagina is None:
            campos["pagina"] = "Use um número inteiro positivo."
        if tamanho is None:
            campos[campo_tamanho] = ("Use um número entre 1 e 50." if campo_tamanho == "por_pagina"
                                     else "Use um número entre 1 e 100.")
        categoria = request.args.get("categoria", "").strip()
        uf = request.args.get("uf", "").strip().upper()
        busca = request.args.get("busca", "").strip()
        if categoria and categoria not in CATEGORIAS:
            campos["categoria"] = "Selecione uma categoria da lista."
        if uf and not re.fullmatch(r"[A-Z]{2}", uf):
            campos["uf"] = "Informe a sigla da UF com duas letras."
        if len(busca) > 100:
            campos["busca"] = "Use até 100 caracteres."
        if campos:
            return {"codigo": "DADOS_INVALIDOS", "mensagem": "Corrija os filtros indicados.",
                    "campos": campos}, 400
        query = _disponiveis()
        if categoria:
            query = query.filter(Doacao.itens.any(categoria=categoria))
        if uf or busca:
            query = query.join(Doacao.estabelecimento)
        if uf:
            query = query.filter(or_(Estabelecimento.endereco.ilike(f"%/{uf} - %"),
                                     Estabelecimento.endereco.ilike(f"%/{uf}")))
        if busca:
            termo = busca.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            padrao = f"%{termo}%"
            query = query.filter(or_(Estabelecimento.nome.ilike(padrao, escape="\\"),
                                     Doacao.itens.any(ItemDoacao.nome.ilike(padrao, escape="\\"))))
        total = query.count()
        doacoes = (_com_relacionamentos(query)
                   .order_by(Doacao.data_cadastro.desc(), Doacao.id.desc())
                   .offset((pagina - 1) * tamanho).limit(tamanho).all())
        return [serializar_doacao(doacao) for doacao in doacoes], 200, {
            "X-Total-Count": str(total), "X-Pagina": str(pagina),
            "X-Por-Pagina": str(tamanho)}

@ns.route("/doacoes/<int:doacao_id>")
class PedidoPublico(Resource):
    def get(self, doacao_id):
        doacao = _com_relacionamentos(Doacao.query).filter_by(id=doacao_id).first()
        if not doacao or doacao.estabelecimento_id is None:
            return {"codigo": "PEDIDO_NAO_ENCONTRADO", "mensagem": "Pedido não encontrado."}, 404
        return serializar_doacao(doacao, detalhe=True), 200

@ns.route("/doacoes/<int:doacao_id>/contribuicoes")
class Contribuir(Resource):
    def post(self, doacao_id):
        doacao = db.session.get(Doacao, doacao_id)
        if not doacao or doacao.estabelecimento_id is None:
            return {"codigo": "PEDIDO_NAO_ENCONTRADO", "mensagem": "Pedido não encontrado."}, 404
        from Contribuicoes import criar_contribuicao
        return criar_contribuicao(doacao)

@ns.route("/opcoes")
class Opcoes(Resource):
    @ns.response(200, "Categorias e unidades aceitas", opcoes_model)
    def get(self):
        return {"categorias": CATEGORIAS, "unidades": UNIDADES}, 200
