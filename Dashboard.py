"""Indicadores agregados e públicos dos pedidos de doação."""

import csv
import json
import random
from threading import RLock
from pathlib import Path
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from flask import Flask, current_app, request
from flask_restx import Namespace, Resource
from sqlalchemy import extract, func, select
from sqlalchemy.pool import StaticPool

from fuso import BRASILIA, agora_brasilia, inicio_dia_utc, iso_evento, utc_para_brasilia
from models import (Contribuicao, Doacao, Doador, Estabelecimento,
                    Excedente, Instituicao, ItemDoacao, ItemExcedente, db)
from Publico import _municipio_uf

ns = Namespace("dashboard", description="Indicadores públicos agregados")


RAIZ = Path(__file__).resolve().parent
KG_POR_REFEICAO = Decimal("0.5")  # premissa declarada; não mede refeições servidas
MACROREGIOES = {
    "Norte": "AC AP AM PA RO RR TO".split(),
    "Nordeste": "AL BA CE MA PB PE PI RN SE".split(),
    "Centro-Oeste": "DF GO MT MS".split(),
    "Sudeste": "ES MG RJ SP".split(),
    "Sul": "PR RS SC".split(),
}
REGIAO_UF = {uf: regiao for regiao, ufs in MACROREGIOES.items() for uf in ufs}
_DEMO_APP = None
_DEMO_DIA = None
_DEMO_LOCK = RLock()


def conversoes_kg(caminho=None):
    caminho = caminho or RAIZ / "data" / "conversao_kg.csv"
    with open(caminho, encoding="utf-8", newline="") as arquivo:
        return {(r["categoria"], r["unidade_medida"]):
                (Decimal(r["kg_por_unidade"]), r["tipo"])
                for r in csv.DictReader(arquivo)}


def converter_kg(quantidade, categoria, unidade, tabela):
    regra = tabela.get((categoria, unidade)) or tabela.get(("*", unidade))
    if regra is None:
        return None
    return Decimal(str(quantidade)) * regra[0], regra[1]


def _uf(endereco):
    municipio = _municipio_uf(endereco)
    uf = municipio.rsplit("/", 1)[-1].upper() if municipio else None
    return uf if uf in REGIAO_UF else "Não informada"


def _minutos_sql(fim, inicio):
    """Diferença em minutos nos dois bancos suportados pelo projeto."""
    if db.session.get_bind().dialect.name == "sqlite":
        return (func.julianday(fim) - func.julianday(inicio)) * 1440
    return extract("epoch", fim - inicio) / 60


def _media_sql(media, amostras):
    return round(float(media), 2) if amostras else None


def _ler_json(caminho):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _resumo_sast():
    return (_ler_json(RAIZ / "relatorios" / "sast" / "resumo.json") or
            _ler_json(RAIZ / "data" / "resumo_sast.json"))


def _refeicoes_mensal(tabela):
    """kg confirmados por mês civil de Brasília, convertidos com a mesma premissa."""
    mensal = defaultdict(Decimal)
    ano = extract("year", Contribuicao.criado_em)
    mes = extract("month", Contribuicao.criado_em)
    dia = extract("day", Contribuicao.criado_em)
    entregues = (db.session.query(ano, mes, dia, Contribuicao.categoria,
                 Contribuicao.unidade_medida, func.sum(Contribuicao.quantidade))
                 .filter(Contribuicao.status == "ENTREGUE",
                         Contribuicao.criado_em.isnot(None))
                 .group_by(ano, mes, dia, Contribuicao.categoria,
                           Contribuicao.unidade_medida).all())
    for a, m, d, categoria, unidade, quantidade in entregues:
        peso = converter_kg(quantidade, categoria, unidade, tabela)
        if peso is None:
            continue
        data = utc_para_brasilia(datetime(int(a), int(m), int(d))).date()
        mensal[(data.year, data.month)] += peso[0]

    ano = extract("year", Excedente.retirado_em)
    mes = extract("month", Excedente.retirado_em)
    dia = extract("day", Excedente.retirado_em)
    retirados = (db.session.query(ano, mes, dia, ItemExcedente.categoria,
                 ItemExcedente.unidade_medida, func.sum(ItemExcedente.quantidade))
                 .join(Excedente, Excedente.id == ItemExcedente.excedente_id)
                 .filter(Excedente.status == "RETIRADO",
                         Excedente.retirado_em.isnot(None))
                 .group_by(ano, mes, dia, ItemExcedente.categoria,
                           ItemExcedente.unidade_medida).all())
    for a, m, d, categoria, unidade, quantidade in retirados:
        peso = converter_kg(quantidade, categoria, unidade, tabela)
        if peso is None:
            continue
        data = utc_para_brasilia(datetime(int(a), int(m), int(d))).date()
        mensal[(data.year, data.month)] += peso[0]

    return [{"mes": f"{a:04d}-{m:02d}", "kg": round(float(kg), 3),
             "refeicoes": round(float(kg / KG_POR_REFEICAO))}
            for (a, m), kg in sorted(mensal.items())]


def montar_impacto():
    """Conta somente entregas e retiradas; ofertas abertas não são impacto."""
    tabela = conversoes_kg()
    total = defaultdict(Decimal)
    por_uf = defaultdict(lambda: defaultdict(Decimal))
    sem_conversao = 0
    calor = [[0] * 24 for _ in range(7)]

    tempos_pedido = (db.session.query(
        func.avg(_minutos_sql(Contribuicao.criado_em, Doacao.data_cadastro)),
        func.count(Contribuicao.id))
        .join(Doacao, Doacao.id == Contribuicao.doacao_id)
        .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")),
                Contribuicao.criado_em >= Doacao.data_cadastro).one())
    tempos_excedente = (db.session.query(
        func.avg(_minutos_sql(Excedente.reservado_em, Excedente.criado_em)),
        func.count(Excedente.id))
        .filter(Excedente.status.in_(("RESERVADO", "RETIRADO")),
                Excedente.reservado_em >= Excedente.criado_em).one())

    ano = extract("year", Contribuicao.criado_em)
    mes = extract("month", Contribuicao.criado_em)
    dia = extract("day", Contribuicao.criado_em)
    hora = extract("hour", Contribuicao.criado_em)
    horarios = (db.session.query(ano, mes, dia, hora, func.count(Contribuicao.id))
                .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")),
                        Contribuicao.criado_em.isnot(None))
                .group_by(ano, mes, dia, hora).all())
    for ano_utc, mes_utc, dia_utc, hora_utc, contagem in horarios:
        local = utc_para_brasilia(datetime(ano_utc, mes_utc, dia_utc, hora_utc))
        calor[local.weekday()][local.hour] += contagem

    contribuicoes = (db.session.query(
        Contribuicao.categoria, Contribuicao.unidade_medida,
        Estabelecimento.endereco,
        func.sum(Contribuicao.quantidade).label("quantidade"),
        func.count(Contribuicao.id).label("itens"))
        .join(Doacao, Doacao.id == Contribuicao.doacao_id)
        .join(Estabelecimento, Estabelecimento.id == Doacao.estabelecimento_id)
        .filter(Contribuicao.status == "ENTREGUE")
        .group_by(Contribuicao.categoria, Contribuicao.unidade_medida,
                  Estabelecimento.id, Estabelecimento.endereco).all())
    for c in contribuicoes:
        peso = converter_kg(c.quantidade, c.categoria, c.unidade_medida, tabela)
        if peso is None:
            sem_conversao += c.itens
            continue
        kg, tipo = peso
        total[tipo] += kg
        por_uf[_uf(c.endereco)][tipo] += kg

    retirados = (db.session.query(ItemExcedente.categoria,
                 ItemExcedente.unidade_medida, Estabelecimento.endereco,
                 func.sum(ItemExcedente.quantidade).label("quantidade"),
                 func.count(ItemExcedente.id).label("itens"))
                 .join(Excedente, Excedente.id == ItemExcedente.excedente_id)
                 .join(Estabelecimento, Estabelecimento.id == Excedente.reservado_por_id)
                 .filter(Excedente.status == "RETIRADO")
                 .group_by(ItemExcedente.categoria, ItemExcedente.unidade_medida,
                           Estabelecimento.id, Estabelecimento.endereco).all())
    for item in retirados:
        peso = converter_kg(item.quantidade, item.categoria, item.unidade_medida, tabela)
        if peso is None:
            sem_conversao += item.itens
            continue
        kg, tipo = peso
        total[tipo] += kg
        por_uf[_uf(item.endereco)][tipo] += kg

    def resumo_peso(valores):
        medido = valores.get("medido", Decimal(0))
        estimado = valores.get("estimado", Decimal(0))
        return {"kg_medido": round(float(medido), 3),
                "kg_estimado": round(float(estimado), 3),
                "refeicoes_estimadas": round(float((medido + estimado) / KG_POR_REFEICAO))}

    regioes = defaultdict(lambda: defaultdict(Decimal))
    for uf, valores in por_uf.items():
        for tipo, kg in valores.items():
            regioes[REGIAO_UF.get(uf, "Não informada")][tipo] += kg
    pedido_media, pedido_amostras = tempos_pedido
    excedente_media, excedente_amostras = tempos_excedente
    combinado_amostras = pedido_amostras + excedente_amostras
    combinado_media = ((pedido_media or 0) * pedido_amostras +
                       (excedente_media or 0) * excedente_amostras)
    combinado_media = combinado_media / combinado_amostras if combinado_amostras else None
    return {
        "peso": resumo_peso(total) | {"itens_sem_conversao": sem_conversao},
        "refeicoes": {"kg_por_refeicao": float(KG_POR_REFEICAO),
                       "premissa": "0,5 kg de alimento por refeição; projeção, não refeições servidas",
                       "por_uf": [{"uf": uf} | resumo_peso(v) for uf, v in sorted(por_uf.items())],
                       "por_regiao": [{"regiao": regiao} | resumo_peso(v)
                                      for regiao, v in sorted(regioes.items())]},
        "match": {"pedido_min": _media_sql(pedido_media, pedido_amostras),
                  "pedido_amostras": pedido_amostras,
                  "excedente_min": _media_sql(excedente_media, excedente_amostras),
                  "excedente_amostras": excedente_amostras,
                  "combinado_min": _media_sql(combinado_media, combinado_amostras),
                  "combinado_amostras": combinado_amostras},
        "calor_doacoes": {"periodo": "todo o histórico", "fuso": "America/Sao_Paulo",
                           "dias": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
                           "horas": list(range(24)), "valores": calor},
        "refeicoes_mensal": {"premissa": "kg confirmados ÷ 0,5 kg por refeição, por mês civil de Brasília",
                             "serie": _refeicoes_mensal(tabela)},
        "ia": {"metricas": _ler_json(RAIZ / "modelo" / "metricas.json"),
               "limiares": _ler_json(RAIZ / "modelo" / "limiares.json")},
    }


def montar_seguranca():
    """Configuração comprovável e relatórios estáticos, nunca telemetria simulada."""
    return {
        "sast": _resumo_sast(),
        "controles": {
            "cabecalhos": ["Content-Security-Policy", "X-Content-Type-Options",
                           "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"],
            "hsts_condicional": bool(current_app.config["SESSION_COOKIE_SECURE"]),
            "cotas": "Login, IA, doações, excedentes e reservas: limites em memória por processo.",
            "falhas_login": "Não medidas em contador persistente; eventos apenas no log de auditoria.",
            "bloqueios_login": "Não medidos em contador persistente."},
    }


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
        .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")))
        .group_by(Contribuicao.doacao_id).subquery())
    recebidas_item = (db.session.query(
        Contribuicao.item_doacao_id.label("item_id"),
        func.sum(Contribuicao.quantidade).label("total"))
        .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")))
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
    cobertura_total = Decimal(0)
    itens_com_meta = 0
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
            itens_com_meta += 1
            cobertura_total += min(recebido / meta, Decimal(1))
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
                   .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")),
                           Contribuicao.criado_em >= inicio_dia_utc(inicio),
                           Contribuicao.criado_em < inicio_dia_utc(hoje + timedelta(days=1)))
                   .group_by(ano, mes, dia, hora).all())
    contagem_dias = defaultdict(int)
    for linha in por_dia_sql:
        horario_utc = datetime(int(linha.ano), int(linha.mes), int(linha.dia),
                               int(linha.hora), tzinfo=timezone.utc)
        contagem_dias[utc_para_brasilia(horario_utc).date().isoformat()] += linha.total

    retiradas_dias = defaultdict(int)
    retiradas = (db.session.query(Excedente.retirado_em)
                .filter(Excedente.status == "RETIRADO",
                        Excedente.retirado_em >= inicio_dia_utc(inicio),
                        Excedente.retirado_em < inicio_dia_utc(hoje + timedelta(days=1))).all())
    for linha in retiradas:
        retiradas_dias[utc_para_brasilia(linha.retirado_em).date().isoformat()] += 1
    if db.engine.dialect.name == "sqlite":
        minutos = (func.julianday(Excedente.reservado_em) -
                   func.julianday(Excedente.criado_em)) * 1440
    else:
        minutos = extract("epoch", Excedente.reservado_em - Excedente.criado_em) / 60
    novos = db.session.query(
        select(func.count(Contribuicao.id)).where(
            Contribuicao.status == "ENTREGUE").scalar_subquery().label("doacoes_entregues"),
        select(func.count(Excedente.id)).where(
            Excedente.status == "DISPONIVEL",
            Excedente.retirar_ate > agora_local).scalar_subquery().label("excedentes_disponiveis"),
        select(func.count(Excedente.id)).where(
            Excedente.status == "RETIRADO").scalar_subquery().label("excedentes_resgatados"),
        select(func.count(Estabelecimento.id)).where(
            Estabelecimento.sem_fins_lucrativos.is_(True)).scalar_subquery().label("ongs"),
        select(func.count(Estabelecimento.id)).where(
            Estabelecimento.atividade_alimentar.is_(True)).scalar_subquery().label("empresas_alimentos"),
        select(func.avg(minutos)).where(
            Excedente.reservado_em.isnot(None)).scalar_subquery().label("tempo_reserva")
    ).one()

    pedidos_empresa = (db.session.query(Doacao.estabelecimento_id.label("empresa_id"),
                       func.count(Doacao.id).label("total"))
                      .filter(Doacao.estabelecimento_id.isnot(None))
                      .group_by(Doacao.estabelecimento_id).subquery())
    recebidas_empresa = (db.session.query(Doacao.estabelecimento_id.label("empresa_id"),
                         func.count(Contribuicao.id).label("total"))
                        .join(Contribuicao, Contribuicao.doacao_id == Doacao.id)
                        .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")))
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
              .filter(Contribuicao.status.in_(("ACEITA", "ENTREGUE")))
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
                Contribuicao.status.in_(("ACEITA", "ENTREGUE"))).scalar(),
            "doacoes_entregues": novos.doacoes_entregues,
            "excedentes_disponiveis": novos.excedentes_disponiveis,
            "excedentes_resgatados": novos.excedentes_resgatados,
            "ongs": novos.ongs,
            "empresas_alimentos": novos.empresas_alimentos,
            "tempo_medio_reserva_min": round(float(novos.tempo_reserva), 2) if novos.tempo_reserva is not None else None,
            "itens_pedidos": len(itens), "itens_atendidos": itens_atendidos,
            "percentual_atendimento": round(float(cobertura_total / itens_com_meta * 100), 2)
            if itens_com_meta else 0.0,
        },
        "por_categoria": [{"categoria": nome, "pedido": float(valores[0]),
                           "recebido": float(valores[1])}
                          for nome, valores in sorted(categorias.items())],
        "por_dia": [{"data": (inicio + timedelta(days=i)).isoformat(),
                     "doacoes": contagem_dias.get((inicio + timedelta(days=i)).isoformat(), 0),
                     "excedentes_resgatados": retiradas_dias.get((inicio + timedelta(days=i)).isoformat(), 0)}
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


def _semear_demonstracao(dados, dia):
    """Cria fatos fictícios de forma reprodutível no app SQLite isolado."""
    sorteio = random.Random(dados["semente"])
    agora = datetime.combine(dia, time.min, BRASILIA)
    agora_utc = agora.astimezone(timezone.utc).replace(tzinfo=None)
    prazo_atual = (agora + timedelta(days=7)).replace(tzinfo=None)
    validade = agora.date() + timedelta(days=14)
    ongs = []
    for numero, local in enumerate(dados["organizacoes_ficticias"], 1):
        ong = Estabelecimento(
            nome=f"ONG Exemplo {local['cidade']} {numero} (fictícia)",
            cnpj=f"DEMO-CNPJ-{numero:05d}", email=f"ong{numero}@example.invalid",
            telefone="00000000000",
            endereco=f"Rua Demonstração, {numero} - Centro, {local['cidade']}/{local['uf']} - 00000000",
            sem_fins_lucrativos=True, atividade_alimentar=False)
        db.session.add(ong)
        ongs.append(ong)
    empresas = []
    for numero in range(1, dados["empresas_ficticias"] + 1):
        empresa = Estabelecimento(
            nome=f"Mercado Exemplo {numero} (fictício)", cnpj=f"DEMO-MERC-{numero:05d}",
            email=f"mercado{numero}@example.invalid", telefone="00000000000",
            endereco=f"Rua Demonstração, {numero} - Centro, Cidade Exemplo/SP - 00000000",
            sem_fins_lucrativos=False, atividade_alimentar=True)
        db.session.add(empresa)
        empresas.append(empresa)
    doadores = []
    for numero in range(1, dados["doadores_ficticios"] + 1):
        doador = Doador(nome=f"Pessoa Exemplo {numero} (fictícia)",
                       cpf=f"DEMO{numero:07d}", email=f"pessoa{numero}@example.invalid",
                       telefone="00000000000")
        db.session.add(doador)
        doadores.append(doador)
    db.session.flush()

    catalogo = dados["alimentos_ficticios"]
    periodo = dados["dias_historico"]
    for indice in range(dados["pedidos"]):
        ong = ongs[indice % len(ongs)]
        alimento = catalogo[sorteio.randrange(len(catalogo))]
        criado = agora_utc - timedelta(days=1 + indice % periodo,
                                        hours=sorteio.randrange(24))
        pedido = Doacao(estabelecimento_id=ong.id, data_cadastro=criado,
                        data_limite_retirada=prazo_atual,
                        status="DISPONIVEL" if indice % periodo < 5 else "RETIRADA")
        db.session.add(pedido)
        db.session.flush()
        quantidade = sorteio.randrange(8, 65)
        item = ItemDoacao(doacao_id=pedido.id, nome=alimento["nome"],
                          categoria=alimento["categoria"], quantidade=quantidade,
                          unidade_medida=alimento["unidade"], validade=validade)
        db.session.add(item)
        db.session.flush()
        status = ("ENTREGUE" if indice % 10 < 7 else
                  "ACEITA" if indice % 10 < 9 else "CANCELADA")
        db.session.add(Contribuicao(
            doacao_id=pedido.id, item_doacao_id=item.id,
            doador_id=doadores[indice % len(doadores)].id,
            alimento=alimento["nome"], categoria=alimento["categoria"],
            quantidade=sorteio.randrange(2, quantidade + 1),
            unidade_medida=alimento["unidade"], validade=validade,
            respostas="{}", foto_arquivo="exemplo-sem-foto.jpg", status=status,
            criado_em=criado + timedelta(minutes=sorteio.randrange(10, 600))))

    for indice in range(dados["excedentes"]):
        ong = ongs[(indice * 7) % len(ongs)]
        empresa = empresas[indice % len(empresas)]
        alimento = catalogo[sorteio.randrange(len(catalogo))]
        criado = agora_utc - timedelta(days=1 + indice % periodo,
                                        hours=sorteio.randrange(24))
        status = "RETIRADO" if indice % 10 < 7 else "RESERVADO" if indice % 10 < 9 else "DISPONIVEL"
        reservado = status in ("RETIRADO", "RESERVADO")
        excedente = Excedente(
            estabelecimento_id=empresa.id, reservado_por_id=ong.id if reservado else None,
            retirar_ate=prazo_atual, status=status, criado_em=criado,
            reservado_em=criado + timedelta(minutes=sorteio.randrange(5, 360)) if reservado else None,
            retirado_em=criado + timedelta(hours=8) if status == "RETIRADO" else None)
        excedente.itens = [ItemExcedente(
            nome=alimento["nome"], categoria=alimento["categoria"],
            quantidade=sorteio.randrange(2, 30), unidade_medida=alimento["unidade"],
            validade=validade)]
        db.session.add(excedente)
    db.session.commit()


def _aplicacao_demonstracao():
    global _DEMO_APP, _DEMO_DIA
    dia = agora_brasilia().date()
    if _DEMO_APP is None or _DEMO_DIA != dia:
        dados = _ler_json(RAIZ / "data" / "demonstracao.json")
        app_demo = Flask("reconecta_dashboard_demonstracao")
        app_demo.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={"poolclass": StaticPool,
                                       "connect_args": {"check_same_thread": False}},
        )
        db.init_app(app_demo)
        with app_demo.app_context():
            db.create_all()
            _semear_demonstracao(dados, dia)
        _DEMO_APP, _DEMO_DIA = app_demo, dia
    return _DEMO_APP


def _consultar_demonstracao(calcular):
    # O bloqueio serializa o acesso à conexão SQLite compartilhada em memória.
    with _DEMO_LOCK:
        app_demo = _aplicacao_demonstracao()
        with app_demo.app_context():
            resposta = calcular()
        return resposta | {"modo": "demonstracao"}


def _modo_demonstracao():
    return request.args.get("modo") == "demonstracao"


@ns.route("")
class Dashboard(Resource):
    @ns.param("modo", "demonstracao: indicadores simulados em SQLite isolado", _in="query")
    def get(self):
        return (_consultar_demonstracao(montar_dashboard)
                if _modo_demonstracao() else montar_dashboard()), 200


@ns.route("/impacto")
class Impacto(Resource):
    @ns.response(200, "Kg medidos/estimados, refeições projetadas por região, match, IA e calor")
    @ns.param("modo", "demonstracao: impacto simulado em SQLite isolado", _in="query")
    def get(self):
        return (_consultar_demonstracao(montar_impacto)
                if _modo_demonstracao() else montar_impacto()), 200


@ns.route("/seguranca")
class Seguranca(Resource):
    @ns.response(200, "Relatórios SAST/STRIDE e controles verificáveis, sem dados pessoais")
    @ns.param("modo", "demonstracao: mesmo SAST e controles reais; origem sinalizada", _in="query")
    def get(self):
        resposta = montar_seguranca()
        if _modo_demonstracao():
            resposta["modo"] = "demonstracao"
        return resposta, 200
