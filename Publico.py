"""Dados públicos da Home, sem identificadores ou contatos privados."""

import re
from datetime import datetime
from decimal import Decimal

from flask import request
from flask_restx import Namespace, Resource, fields

from models import Doacao, Doador, Estabelecimento, Instituicao, ItemDoacao, db


ns = Namespace("publico", description="Resumo e doações disponíveis")

CATEGORIAS = ["Hortifrúti", "Padaria", "Laticínios", "Carnes e peixes",
              "Grãos e cereais", "Refeições prontas", "Bebidas não alcoólicas", "Outros"]
UNIDADES = ["kg", "g", "L", "unidade", "pacote", "caixa"]

resumo_model = ns.model("ResumoPublico", {
    "empresas": fields.Integer, "doadores": fields.Integer,
    "instituicoes": fields.Integer,
    "doacoes_disponiveis": fields.Integer, "itens_disponiveis": fields.Integer,
    "kg_disponiveis": fields.Float,
})
opcoes_model = ns.model("OpcoesDoacao", {
    "categorias": fields.List(fields.String), "unidades": fields.List(fields.String),
})
item_model = ns.model("ItemDoacaoPublico", {
    "nome": fields.String, "categoria": fields.String, "quantidade": fields.Float,
    "unidade_medida": fields.String, "validade": fields.String,
})
estabelecimento_model = ns.model("EstabelecimentoPublico", {
    "nome": fields.String, "municipio_uf": fields.String,
})
doacao_model = ns.model("DoacaoPublica", {
    "id": fields.Integer, "estabelecimento": fields.Nested(estabelecimento_model),
    "data_cadastro": fields.String, "data_limite_retirada": fields.String,
    "categorias": fields.List(fields.String), "itens": fields.List(fields.Nested(item_model)),
})


def _municipio_uf(endereco):
    for parte in (endereco or "").split(" - "):
        candidato = parte.rsplit(",", 1)[-1].strip()
        if re.fullmatch(r"[^,/]+/[A-Za-z]{2}", candidato):
            return candidato
    return None


def serializar_doacao(doacao, incluir_status=False):
    itens = [{"nome": item.nome, "categoria": item.categoria,
              "quantidade": float(item.quantidade), "unidade_medida": item.unidade_medida,
              "validade": item.validade.isoformat()}
             for item in doacao.itens]
    dados = {
        "id": doacao.id,
        "estabelecimento": {"nome": doacao.estabelecimento.nome,
                            "municipio_uf": _municipio_uf(doacao.estabelecimento.endereco)},
        "data_cadastro": doacao.data_cadastro.isoformat() if doacao.data_cadastro else None,
        "data_limite_retirada": doacao.data_limite_retirada.isoformat(),
        "categorias": list(dict.fromkeys(item["categoria"] for item in itens)),
        "itens": itens,
    }
    if incluir_status:
        dados["status"] = doacao.status
    return dados


def _disponiveis():
    return Doacao.query.filter(Doacao.status == "DISPONIVEL",
                               Doacao.data_limite_retirada > datetime.now())


@ns.route("/resumo")
class Resumo(Resource):
    @ns.response(200, "Contadores públicos", resumo_model)
    def get(self):
        """Contadores da plataforma e peso disponível em quilogramas."""
        doacoes = _disponiveis().all()
        itens = [item for doacao in doacoes for item in doacao.itens]
        peso = sum((Decimal(str(item.quantidade)) *
                    (Decimal("0.001") if item.unidade_medida == "g" else Decimal("1"))
                    for item in itens if item.unidade_medida in ("kg", "g")), Decimal("0"))
        return {
            "empresas": db.session.query(Estabelecimento.id).count(),
            "doadores": db.session.query(Doador.id).count(),
            "instituicoes": db.session.query(Instituicao.id).count(),
            "doacoes_disponiveis": len(doacoes),
            "itens_disponiveis": len(itens),
            "kg_disponiveis": float(peso),
        }, 200


@ns.route("/doacoes")
class DoacoesPublicas(Resource):
    @ns.response(200, "Doações disponíveis", [doacao_model])
    def get(self):
        """Lista doações disponíveis e futuras, sem dados de contato."""
        limite_raw = request.args.get("limite", "8")
        if not limite_raw.isascii() or not limite_raw.isdigit() or not 1 <= int(limite_raw) <= 100:
            return {"codigo": "DADOS_INVALIDOS", "mensagem": "Informe um limite entre 1 e 100.",
                    "campos": {"limite": "Use um número entre 1 e 100."}}, 400
        doacoes = _disponiveis().order_by(Doacao.data_cadastro.desc(), Doacao.id.desc()).limit(int(limite_raw)).all()
        return [serializar_doacao(doacao) for doacao in doacoes], 200


@ns.route("/opcoes")
class Opcoes(Resource):
    @ns.response(200, "Categorias e unidades aceitas", opcoes_model)
    def get(self):
        """Listas fixas usadas no formulário de doação."""
        return {"categorias": CATEGORIAS, "unidades": UNIDADES}, 200
