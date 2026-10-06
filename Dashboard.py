"""Indicadores agregados e públicos dos pedidos de doação."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from flask_restx import Namespace, Resource
from sqlalchemy import extract, func

from fuso import agora_brasilia, inicio_dia_utc, iso_evento, utc_para_brasilia
from models import (Contribuicao, Doacao, Doador, Estabelecimento,
                    Instituicao, ItemDoacao, db)
from Publico import _municipio_uf

ns = Namespace("dashboard", description="Indicadores públicos agregados")


def montar_dashboard() -> dict:
    """Produz um retrato agregado com um número fixo de consultas SQL."""
    agora = agora_brasilia()
    agora_local = agora.replace(tzinfo=None)
    agora_utc = agora.astimezone(timezone.utc).replace(tzinfo=None)
    hoje = agora.date()
    abertas = (Doacao.estabelecimento_id.isnot(None),
               Doacao.status == "DISPONIVEL",
               Doacao.data_limite_retirada > agora_local)
    contagem_aceitas = (db.session.query(
        Contribuicao.doacao_id.label("pedido_id"),
        func.count(Contribuicao.id).label("total"))
        .filter(Contribuicao.status == "ACEITA")
        .group_by(Contribuicao.doacao_id).subquery())
    recebidas_item = (db.session.query(
        Contribuicao.item_doacao_id.label("item_id"),
        func.sum(Contribuicao.quantidade).label("total"))
        .filter(Contribuicao.status == "ACEITA")
        .group_by(Contribuicao.item_doacao_id).subquery())

    pedidos = (db.session.query(Doacao.id, Doacao.data_cadastro,
                Doacao.data_limite_retirada,
                func.coalesce(contagem_aceitas.c.total, 0).label("doacoes"))
               .outerjoin(contagem_aceitas, contagem_aceitas.c.pedido_id == Doacao.id)
               .filter(*abertas).all())
    itens = (db.session.query(ItemDoacao.doacao_id, ItemDoacao.nome,
               ItemDoacao.categoria, ItemDoacao.quantidade,
               func.coalesce(recebidas_item.c.total, 0).label("recebido"))
             .join(Doacao, Doacao.id == ItemDoacao.doacao_id)
             .outerjoin(recebidas_item, recebidas_item.c.item_id == ItemDoacao.id)
             .filter(*abertas).all())

    categorias = defaultdict(lambda: [Decimal(0), Decimal(0)])
    meta_total = Decimal(0)
    atendido_total = Decimal(0)
    itens_atendidos = 0
    alertas = []
    for pedido in pedidos:
        if pedido.data_limite_retirada <= agora_local + timedelta(days=3):
            alertas.append({"tipo": "PRAZO_PROXIMO", "pedido_id": pedido.id,
                            "mensagem": f"O prazo do pedido {pedido.id} está próximo."})
        if (pedido.data_cadastro and
                pedido.data_cadastro <= agora_utc - timedelta(days=3) and
                pedido.doacoes == 0):
            alertas.append({"tipo": "SEM_DOACOES", "pedido_id": pedido.id,
                            "mensagem": f"O pedido {pedido.id} está há pelo menos 3 dias sem doações."})
    for item in itens:
        meta = Decimal(str(item.quantidade))
        recebido = Decimal(str(item.recebido))
        categorias[item.categoria][0] += meta
        categorias[item.categoria][1] += recebido
        if meta > 0:
            meta_total += meta
            atendido_total += min(recebido, meta)
            if recebido >= meta:
                itens_atendidos += 1
                tipo = "META_ATINGIDA"
                mensagem = f"A meta de {item.nome} no pedido {item.doacao_id} foi atingida."
            elif recebido >= meta * Decimal("0.8"):
                tipo = "QUASE_COMPLETO"
                mensagem = f"A meta de {item.nome} no pedido {item.doacao_id} está quase completa."
            else:
                continue
            alertas.append({"tipo": tipo, "pedido_id": item.doacao_id,
                            "mensagem": mensagem})

    inicio = hoje - timedelta(days=29)
    ano = extract("year", Contribuicao.criado_em)
    mes = extract("month", Contribuicao.criado_em)
    dia = extract("day", Contribuicao.criado_em)
    hora = extract("hour", Contribuicao.criado_em)
    por_dia_sql = (db.session.query(ano.label("ano"), mes.label("mes"),
                    dia.label("dia"), hora.label("hora"),
                    func.count(Contribuicao.id).label("total"))
                   .filter(Contribuicao.status == "ACEITA",
                           Contribuicao.criado_em >= inicio_dia_utc(inicio),
                           Contribuicao.criado_em < inicio_dia_utc(hoje + timedelta(days=1)))
                   .group_by(ano, mes, dia, hora).all())
    contagem_dias = defaultdict(int)
    for linha in por_dia_sql:
        horario_utc = datetime(int(linha.ano), int(linha.mes), int(linha.dia),
                               int(linha.hora), tzinfo=timezone.utc)
        contagem_dias[utc_para_brasilia(horario_utc).date().isoformat()] += linha.total

    pedidos_empresa = (db.session.query(Doacao.estabelecimento_id.label("empresa_id"),
                       func.count(Doacao.id).label("total"))
                      .filter(Doacao.estabelecimento_id.isnot(None))
                      .group_by(Doacao.estabelecimento_id).subquery())
    recebidas_empresa = (db.session.query(Doacao.estabelecimento_id.label("empresa_id"),
                         func.count(Contribuicao.id).label("total"))
                        .join(Contribuicao, Contribuicao.doacao_id == Doacao.id)
                        .filter(Contribuicao.status == "ACEITA")
                        .group_by(Doacao.estabelecimento_id).subquery())
    empresas = (db.session.query(Estabelecimento.nome, Estabelecimento.endereco,
                func.coalesce(pedidos_empresa.c.total, 0).label("pedidos"),
                func.coalesce(recebidas_empresa.c.total, 0).label("recebidas"))
                .join(pedidos_empresa, pedidos_empresa.c.empresa_id == Estabelecimento.id)
                .outerjoin(recebidas_empresa,
                           recebidas_empresa.c.empresa_id == Estabelecimento.id)
                .order_by(func.coalesce(recebidas_empresa.c.total, 0).desc(),
                          pedidos_empresa.c.total.desc(), Estabelecimento.nome)
                .limit(10).all())
    ultimas = (db.session.query(Contribuicao.criado_em, Contribuicao.alimento,
               Contribuicao.quantidade, Contribuicao.unidade_medida,
               Contribuicao.doador_id, Estabelecimento.nome)
              .join(Doacao, Doacao.id == Contribuicao.doacao_id)
              .join(Estabelecimento, Estabelecimento.id == Doacao.estabelecimento_id)
              .filter(Contribuicao.status == "ACEITA")
              .order_by(Contribuicao.criado_em.desc(), Contribuicao.id.desc())
              .limit(10).all())
    total_pedidos = (db.session.query(func.count(Doacao.id))
                     .filter(Doacao.estabelecimento_id.isnot(None)).scalar())
    return {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "indicadores": {
            "empresas": db.session.query(func.count(Estabelecimento.id)).scalar(),
            "doadores": db.session.query(func.count(Doador.id)).scalar(),
            "instituicoes": db.session.query(func.count(Instituicao.id)).scalar(),
            "pedidos_abertos": len(pedidos),
            "pedidos_encerrados": total_pedidos - len(pedidos),
            "doacoes_recebidas": db.session.query(func.count(Contribuicao.id)).filter(
                Contribuicao.status == "ACEITA").scalar(),
            "itens_pedidos": len(itens), "itens_atendidos": itens_atendidos,
            "percentual_atendimento": round(float(atendido_total / meta_total * 100), 2)
            if meta_total else 0.0,
        },
        "por_categoria": [{"categoria": nome, "pedido": float(valores[0]),
                           "recebido": float(valores[1])}
                          for nome, valores in sorted(categorias.items())],
        "por_dia": [{"data": (inicio + timedelta(days=i)).isoformat(),
                     "doacoes": contagem_dias.get((inicio + timedelta(days=i)).isoformat(), 0)}
                    for i in range(30)],
        "top_empresas": [{"nome": e.nome, "municipio_uf": _municipio_uf(e.endereco),
                          "pedidos": e.pedidos, "doacoes_recebidas": e.recebidas}
                         for e in empresas],
        "alertas": alertas,
        "ultimas_doacoes": [{"data": iso_evento(c.criado_em), "item": c.alimento,
                             "quantidade": float(c.quantidade),
                             "unidade_medida": c.unidade_medida, "empresa": c.nome,
                             "origem": "pessoa" if c.doador_id else "empresa"}
                            for c in ultimas],
    }


@ns.route("")
class Dashboard(Resource):
    def get(self):
        return montar_dashboard(), 200
