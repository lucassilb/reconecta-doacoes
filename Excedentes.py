"""Publicação e resgate de excedentes alimentares.

Publica quem tem alimento sobrando: empresa de alimentos (CNPJ) ou pessoa física (CPF),
que informa o endereço de retirada. Só ONGs reservam; quem publicou confirma a retirada.
"""

import re
import threading
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from flask import current_app, request
from flask_restx import Namespace, Resource, fields
from sqlalchemy import or_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

import geo
from Auth import registrar_auditoria, usuario_atual
from conexao import casar
from eventos import emitir as _emitir
from Publico import CATEGORIAS, UNIDADES, _inteiro_positivo, _municipio_uf
from fuso import agora_brasilia_sem_fuso, hoje_brasilia, iso_evento, iso_prazo, utc_para_brasilia
from models import Estabelecimento, Excedente, ItemExcedente, _utc_naive, db
from risco_descarte import prever as prever_risco, PERECIVEIS

ns = Namespace("excedentes", description="Excedentes para reserva e retirada por ONGs")
item_entrada = ns.model("ItemExcedenteEntrada", {
    "nome": fields.String(required=True), "categoria": fields.String(required=True),
    "quantidade": fields.Float(required=True), "unidade_medida": fields.String(required=True),
    "validade": fields.String(required=True, description="Data AAAA-MM-DD"),
})
entrada = ns.model("ExcedenteEntrada", {
    "retirar_ate": fields.String(required=True, description="Data e hora ISO local de Brasília, sem offset"),
    "itens": fields.List(fields.Nested(item_entrada), required=True),
    "observacao": fields.String(description="Até 200 caracteres"),
    "dentro_validade": fields.Boolean(required=True),
    "embalagem_ok": fields.Boolean(required=True),
    "armazenado_ok": fields.Boolean(required=True),
    "nao_caseiro": fields.Boolean(description="Obrigatório para pessoa física: não é comida feita em casa"),
    "retirada": fields.Raw(description="Obrigatório para pessoa física: {logradouro, numero, bairro, "
                                       "municipio, uf, cep}; só a ONG que reservar vê o endereço"),
})
saida = ns.model("ExcedenteSaida", {
    "id": fields.Integer, "empresa": fields.Raw, "retirar_ate": fields.String,
    "itens": fields.List(fields.Raw), "status": fields.String,
    "pode_reservar": fields.Boolean, "motivo_bloqueio": fields.String,
    "retirada": fields.Raw, "reservado_por": fields.Raw,
    "prioridade": fields.Raw,
})
erro_model = ns.model("ExcedenteErro", {
    "codigo": fields.String, "mensagem": fields.String, "campos": fields.Raw,
})

_cotas = {}
_cotas_lock = threading.Lock()
JANELA = 3600
LIMITES = {"publicar": 20, "reservar": 30}


def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


# Avisos de excedente: ONGs com pedido compatível na mesma UF ou a até RAIO_AVISO_KM,
# das mais próximas para as mais distantes, no máximo MAX_AVISOS.
RAIO_AVISO_KM = 50
MAX_AVISOS = 10


def _ongs_compativeis(itens, uf, publicador_id, origem=None):
    """Destinatários dos avisos, das ONGs mais próximas para as mais distantes."""
    return tuple(("empresa", id_) for id_, _, _ in
                 _ongs_proximas(itens, uf, publicador_id, origem))


def _ongs_proximas(itens, uf, publicador_id, origem=None):
    """Usa o mesmo casamento da IA; devolve [(ong_id, km ou None, aproximada)]."""
    if not itens or not (uf or origem is not None):
        return []
    from IA import _pedidos_abertos
    ongs = {id_ for (id_,) in db.session.query(Estabelecimento.id).filter(
        Estabelecimento.sem_fins_lucrativos.is_(True)).all()}
    categorias = {item["categoria"] for item in itens}
    ofertas = [{"nome": item["nome"], "categoria": item["categoria"],
               "quantidade": float(item["quantidade"]),
               "unidade_medida": item["unidade_medida"]} for item in itens]
    pedidos = [pedido for pedido in _pedidos_abertos()
               if pedido["estabelecimento_id"] in ongs and pedido["estabelecimento_id"] != publicador_id
               and any(item["categoria"] in categorias for item in pedido["itens"])]
    geo.anotar_distancias(pedidos, origem)
    achadas = {}
    for pedido in pedidos:
        id_ = pedido["estabelecimento_id"]
        local = (pedido.get("empresa") or {}).get("municipio_uf") or ""
        km = pedido.get("distancia_km")
        perto = km is not None and km <= RAIO_AVISO_KM
        if not (perto or (uf and local.upper().endswith(f"/{uf}"))):
            continue
        if id_ not in achadas and casar(ofertas, [pedido], uf):
            achadas[id_] = (km, pedido.get("distancia_aproximada"))
    ordem = sorted(achadas.items(), key=lambda par: (par[1][0] is None, par[1][0] or 0, par[0]))
    return [(id_, km, aproximada) for id_, (km, aproximada) in ordem[:MAX_AVISOS]]


def _empresa():
    atual = usuario_atual()
    if not atual:
        return None, _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
    if atual[0] != "empresa":
        return None, _erro("APENAS_EMPRESAS", "Use um cadastro com CNPJ.", 403)
    return atual[1], None


def _sessao():
    """(tipo, usuario) de quem pode publicar e gerenciar: empresa ou pessoa física."""
    atual = usuario_atual()
    if not atual:
        return None, _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
    return atual, None


def _dono(excedente):
    """Quem publicou, no formato dos destinatários de eventos."""
    if excedente.doador_id is not None:
        return ("doador", excedente.doador_id)
    return ("empresa", excedente.estabelecimento_id)


def _eh_dono(excedente, atual):
    return bool(atual) and _dono(excedente) == (atual[0], atual[1].id)


def nome_publicador(excedente):
    # pessoa física não tem o nome exposto: aparece só como "Pessoa física"
    return excedente.publicador.nome if excedente.publicador else "Pessoa física"


def endereco_retirada(excedente):
    return excedente.publicador.endereco if excedente.publicador else excedente.retirada_endereco


def _filtro_dono(atual):
    if atual[0] == "doador":
        return Excedente.doador_id == atual[1].id
    return Excedente.estabelecimento_id == atual[1].id


def _validar_retirada(bruto):
    """Endereço de retirada da pessoa física, no mesmo formato do cadastro das organizações."""
    campos = {}
    bruto = bruto if isinstance(bruto, dict) else {}

    def texto(chave, minimo, maximo):
        valor = bruto.get(chave)
        valor = valor.strip() if isinstance(valor, str) else ""
        return valor if minimo <= len(valor) <= maximo else None

    logradouro = texto("logradouro", 3, 100)
    numero = texto("numero", 1, 10)
    bairro = texto("bairro", 0, 60)
    municipio = texto("municipio", 2, 60)
    uf = (bruto.get("uf") or "").strip().upper() if isinstance(bruto.get("uf"), str) else ""
    cep = re.sub(r"\D", "", str(bruto.get("cep") or ""))
    if logradouro is None:
        campos["retirada.logradouro"] = "Informe a rua ou avenida."
    if numero is None:
        campos["retirada.numero"] = "Informe o número (ou S/N)."
    if bairro is None:
        campos["retirada.bairro"] = "Use até 60 caracteres."
    if municipio is None or not re.fullmatch(r"[A-Z]{2}", uf) or geo.centroide(municipio, uf) is None:
        campos["retirada.municipio"] = "Informe a cidade e a UF (ex.: Campinas e SP)."
    if cep and len(cep) != 8:
        campos["retirada.cep"] = "Informe o CEP com 8 números ou deixe em branco."
    if campos:
        return None, campos
    local = ", ".join(p for p in (bairro, municipio) if p) + f"/{uf}"
    endereco = " - ".join(p for p in (f"{logradouro}, {numero}", local, cep) if p)
    return endereco[:200], {}


def _cota_esgotada(acao, usuario_id, tipo="empresa"):
    agora = time.monotonic()
    chave = (acao, tipo, usuario_id)
    with _cotas_lock:
        recentes = [instante for instante in _cotas.get(chave, ()) if agora - instante < JANELA]
        if len(recentes) >= LIMITES[acao]:
            _cotas[chave] = recentes
            return True
        recentes.append(agora)
        _cotas[chave] = recentes
    return False


def _data_hora(valor):
    if not isinstance(valor, str):
        return None
    try:
        data = datetime.fromisoformat(valor)
    except ValueError:
        return None
    return data if data.tzinfo is None else None


def _quantidade(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float, str, Decimal)):
        return None
    try:
        numero = Decimal(str(valor))
        return numero if numero.is_finite() and Decimal("0.01") <= numero <= Decimal("99999999.99") and numero == numero.quantize(Decimal("0.01")) else None
    except InvalidOperation:
        return None


def _validar(corpo):
    campos = {}
    prazo = _data_hora(corpo.get("retirar_ate"))
    if prazo is None or prazo <= agora_brasilia_sem_fuso():
        campos["retirar_ate"] = "Informe uma data e hora futuras de Brasília."
    observacao = corpo.get("observacao")
    if observacao is not None and (not isinstance(observacao, str) or len(observacao) > 200):
        campos["observacao"] = "Use até 200 caracteres."
    for declaracao in ("dentro_validade", "embalagem_ok", "armazenado_ok"):
        if corpo.get(declaracao) is not True:
            campos[declaracao] = "Confirme esta condição para publicar."
    origem = corpo.get("itens")
    if not isinstance(origem, list) or not origem:
        campos["itens"] = "Inclua pelo menos um item."
        return prazo, [], observacao, campos
    itens = []
    for indice, bruto in enumerate(origem):
        if not isinstance(bruto, dict):
            campos[f"itens[{indice}]"] = "Informe um item válido."
            continue
        nome = bruto.get("nome")
        categoria = bruto.get("categoria")
        quantidade = _quantidade(bruto.get("quantidade"))
        unidade = bruto.get("unidade_medida")
        try:
            validade = date.fromisoformat(bruto.get("validade", ""))
        except (ValueError, TypeError):
            validade = None
        prefixo = f"itens[{indice}]"
        if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 100:
            campos[f"{prefixo}.nome"] = "Informe um nome de até 100 caracteres."
        if categoria not in CATEGORIAS:
            campos[f"{prefixo}.categoria"] = "Selecione uma categoria da lista."
        if quantidade is None:
            campos[f"{prefixo}.quantidade"] = "Informe uma quantidade positiva com até duas casas decimais."
        if unidade not in UNIDADES:
            campos[f"{prefixo}.unidade_medida"] = "Selecione uma unidade da lista."
        if validade is None or validade < hoje_brasilia():
            campos[f"{prefixo}.validade"] = "Informe uma validade de hoje em diante."
        if (isinstance(nome, str) and 1 <= len(nome.strip()) <= 100 and
                categoria in CATEGORIAS and quantidade is not None and unidade in UNIDADES and
                validade is not None and validade >= hoje_brasilia()):
            itens.append(dict(nome=nome.strip(), categoria=categoria, quantidade=quantidade,
                              unidade_medida=unidade, validade=validade))
    if prazo is not None and itens and prazo.date() > min(item["validade"] for item in itens):
        campos["retirar_ate"] = "A retirada deve ocorrer até a primeira validade."
    return prazo, itens, observacao, campos


def status_efetivo(excedente, agora=None):
    if excedente.status in ("DISPONIVEL", "RESERVADO") and excedente.retirar_ate <= (agora or agora_brasilia_sem_fuso()):
        return "EXPIRADO"
    return excedente.status


def _bloqueio(excedente, atual):
    if not atual:
        return "Entre como ONG para reservar"
    if atual[0] != "empresa" or not atual[1].sem_fins_lucrativos:
        return "Apenas ONGs podem reservar"
    if _eh_dono(excedente, atual):
        return "Não é possível reservar o próprio excedente"
    if status_efetivo(excedente) != "DISPONIVEL":
        return "Excedente indisponível"
    return None


@lru_cache(maxsize=1)
def _tabela_conversoes():
    from Dashboard import conversoes_kg
    return conversoes_kg()


def _prioridade_excedente(excedente):
    """Usa apenas campos já publicados; temperatura e distância ficam ausentes."""
    from Dashboard import converter_kg

    itens = list(excedente.itens)
    if not itens:
        return {"probabilidade": None, "nivel": "indisponivel", "motivos": [],
                "selo": None, "base": "simulacao"}
    tabela = _tabela_conversoes()
    kg = sum((converter_kg(item.quantidade, item.categoria,
                           item.unidade_medida, tabela) or (0, None))[0]
             for item in itens)
    mais_urgente = min(itens, key=lambda item: item.validade)
    publicado = utc_para_brasilia(excedente.criado_em)
    municipio_uf = _municipio_uf(endereco_retirada(excedente)) or ""
    uf = municipio_uf.rsplit("/", 1)[-1] if "/" in municipio_uf else "NA"
    lote = {"categoria": mais_urgente.categoria,
            "perecivel": mais_urgente.categoria in PERECIVEIS,
            "dias_validade": max(0, (mais_urgente.validade - hoje_brasilia()).days),
            "quantidade_kg": max(.01, min(100000, float(kg))),
            "temperatura_c": None, "armazenamento": "nao_informado",
            "dia_semana": publicado.weekday(), "hora_publicacao": publicado.hour,
            "uf": uf, "distancia_ong_km": None}
    try:
        resultado = prever_risco(lote)
    except (OSError, ValueError):
        return {"probabilidade": None, "nivel": "indisponivel", "motivos": [],
                "selo": None, "base": "simulacao"}
    resultado["selo"] = "Prioridade alta" if resultado["nivel"] == "alto" else None
    return resultado


def serializar_excedente(excedente, *, detalhe=False, atual=None, prioridade=None):
    prioridade = prioridade if prioridade is not None else _prioridade_excedente(excedente)
    dados = {
        "id": excedente.id,
        "empresa": {"nome": nome_publicador(excedente),
                    "municipio_uf": _municipio_uf(endereco_retirada(excedente)),
                    "pessoa_fisica": excedente.doador_id is not None},
        "retirar_ate": iso_prazo(excedente.retirar_ate),
        "itens": [{"nome": item.nome, "categoria": item.categoria,
                   "quantidade": float(item.quantidade), "unidade_medida": item.unidade_medida,
                   "validade": item.validade.isoformat()} for item in excedente.itens],
        "status": status_efetivo(excedente),
        "prioridade": prioridade,
    }
    if detalhe:
        motivo = _bloqueio(excedente, atual)
        dados.update(pode_reservar=motivo is None, motivo_bloqueio=motivo,
                     observacao=excedente.observacao,
                     criado_em=iso_evento(excedente.criado_em))
        dados["meu"] = _eh_dono(excedente, atual)
        if atual and atual[0] == "empresa" and not dados["meu"]:
            km, aproximada = geo.distancia(geo.localizar(atual[1].endereco),
                                           geo.localizar(endereco_retirada(excedente)))
            if km is not None:
                dados["distancia_km"] = round(km, 1)
                dados["distancia"] = geo.texto_distancia(km, aproximada)
        if atual and atual[0] == "empresa" and atual[1].id == excedente.reservado_por_id:
            dados["retirada"] = {"endereco": endereco_retirada(excedente),
                                 "retirar_ate": iso_prazo(excedente.retirar_ate)}
        if dados["meu"] and excedente.reservado_por:
            dados["reservado_por"] = {"id": excedente.reservado_por_id,
                                      "nome": excedente.reservado_por.nome}
        if dados["meu"] and excedente.doador_id is not None:
            dados["retirada_informada"] = excedente.retirada_endereco
    return dados


def _consulta():
    return Excedente.query.options(selectinload(Excedente.itens),
                                   selectinload(Excedente.publicador),
                                   selectinload(Excedente.reservado_por))


@ns.route("")
class Excedentes(Resource):
    @ns.response(200, "Excedentes disponíveis", [saida])
    def get(self):
        pagina = _inteiro_positivo("pagina", 1, 1000000)
        campo_tamanho = "por_pagina" if "por_pagina" in request.args else "limite"
        tamanho = _inteiro_positivo(campo_tamanho, 8, 50 if campo_tamanho == "por_pagina" else 100)
        categoria = request.args.get("categoria", "").strip()
        uf = request.args.get("uf", "").strip().upper()
        campos = {}
        if pagina is None:
            campos["pagina"] = "Use um número inteiro positivo."
        if tamanho is None:
            campos[campo_tamanho] = "Use um número entre 1 e 50." if campo_tamanho == "por_pagina" else "Use um número entre 1 e 100."
        if categoria and categoria not in CATEGORIAS:
            campos["categoria"] = "Selecione uma categoria da lista."
        if uf and not re.fullmatch(r"[A-Z]{2}", uf):
            campos["uf"] = "Informe a UF com duas letras."
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os filtros indicados.", 400, campos=campos)
        query = _consulta().filter(Excedente.status == "DISPONIVEL",
                                   Excedente.retirar_ate > agora_brasilia_sem_fuso())
        if categoria:
            query = query.filter(Excedente.itens.any(categoria=categoria))
        if uf:
            query = query.outerjoin(Excedente.publicador).filter(or_(
                Estabelecimento.endereco.ilike(f"%/{uf} - %"),
                Estabelecimento.endereco.ilike(f"%/{uf}"),
                Excedente.retirada_endereco.ilike(f"%/{uf} - %"),
                Excedente.retirada_endereco.ilike(f"%/{uf}")))
        pontuados = [(item, _prioridade_excedente(item)) for item in query.all()]
        total = len(pontuados)
        pontuados.sort(key=lambda par: (
            par[1]["probabilidade"] if par[1]["probabilidade"] is not None else -1,
            par[0].criado_em or datetime.min, par[0].id), reverse=True)
        inicio = (pagina - 1) * tamanho
        anuncios = pontuados[inicio:inicio + tamanho]
        return [serializar_excedente(item, prioridade=prioridade)
                for item, prioridade in anuncios], 200, {
            "X-Total-Count": str(total), "X-Pagina": str(pagina), "X-Por-Pagina": str(tamanho)}

    @ns.expect(entrada)
    @ns.response(201, "Excedente publicado", saida)
    @ns.response(429, "Cota de 20 publicações por hora")
    def post(self):
        atual, erro = _sessao()
        if erro:
            return erro
        tipo, usuario = atual
        if tipo == "empresa" and not usuario.atividade_alimentar:
            return _erro("PERFIL_SEM_ATIVIDADE_ALIMENTAR", "Este CNPJ não pode publicar excedentes.", 403)
        if _cota_esgotada("publicar", usuario.id, tipo):
            return _erro("MUITAS_TENTATIVAS", "Aguarde antes de publicar outro excedente.", 429)
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        prazo, itens, observacao, campos = _validar(corpo)
        retirada = None
        if tipo == "doador":
            # pessoa física: comida caseira não entra e o endereço de retirada é obrigatório
            if corpo.get("nao_caseiro") is not True:
                campos["nao_caseiro"] = "Confirme que não é comida feita em casa."
            retirada, campos_retirada = _validar_retirada(corpo.get("retirada"))
            campos.update(campos_retirada)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        if tipo == "doador":
            excedente = Excedente(doador_id=usuario.id, retirada_endereco=retirada)
            endereco, publicador_id, nome = retirada, None, "Pessoa física"
        else:
            excedente = Excedente(estabelecimento_id=usuario.id)
            endereco, publicador_id, nome = usuario.endereco, usuario.id, usuario.nome
        excedente.retirar_ate = prazo
        excedente.observacao = observacao.strip() if observacao else None
        try:
            db.session.add(excedente)
            db.session.flush()
            db.session.add_all(ItemExcedente(excedente_id=excedente.id, **item) for item in itens)
            categorias = sorted({item["categoria"] for item in itens})
            aviso = {"excedente_id": excedente.id, "organizacao": nome,
                     "municipio_uf": _municipio_uf(endereco),
                     "categorias": categorias, "retirar_ate": iso_prazo(prazo)}
            _emitir("excedente.publicado", aviso)
            # cada ONG recebe o aviso com a própria distância, das mais próximas para as mais distantes
            for ong_id, km, aproximada in _ongs_proximas(
                    itens, (_municipio_uf(endereco) or "").rsplit("/", 1)[-1],
                    publicador_id, geo.localizar(endereco)):
                privado = dict(aviso)
                if km is not None:
                    privado.update(distancia_km=round(km, 1),
                                   distancia=geo.texto_distancia(km, aproximada))
                _emitir("excedente.publicado", privado, publico=False,
                        destinatarios=(("empresa", ong_id),))
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao criar excedente")
            return _erro("ERRO_INTERNO", "Não foi possível publicar o excedente.", 500)
        registrar_auditoria("excedente_publicado", "ok", tipo=tipo, ator_id=usuario.id)
        return serializar_excedente(excedente, detalhe=True, atual=atual), 201


@ns.route("/meus")
class MeusExcedentes(Resource):
    def get(self):
        atual, erro = _sessao()
        if erro:
            return erro
        anuncios = _consulta().filter(_filtro_dono(atual)).order_by(Excedente.criado_em.desc(), Excedente.id.desc()).all()
        return [serializar_excedente(item, detalhe=True, atual=atual) for item in anuncios], 200


@ns.route("/reservas")
class ReservasExcedentes(Resource):
    def get(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        anuncios = _consulta().filter_by(reservado_por_id=empresa.id).order_by(Excedente.reservado_em.desc(), Excedente.id.desc()).all()
        return [serializar_excedente(item, detalhe=True, atual=("empresa", empresa)) for item in anuncios], 200


@ns.route("/<int:excedente_id>")
class ExcedenteDetalhe(Resource):
    @ns.response(200, "Detalhe do excedente", saida)
    def get(self, excedente_id):
        excedente = _consulta().filter_by(id=excedente_id).first()
        if not excedente:
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        return serializar_excedente(excedente, detalhe=True, atual=usuario_atual()), 200

    def delete(self, excedente_id):
        atual, erro = _sessao()
        if erro:
            return erro
        excedente = db.session.get(Excedente, excedente_id)
        if not excedente or not _eh_dono(excedente, atual):
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        if status_efetivo(excedente) != "DISPONIVEL":
            return _erro("EXCEDENTE_INDISPONIVEL", "Este excedente não pode ser cancelado.", 409)
        resultado = db.session.execute(update(Excedente).where(
            Excedente.id == excedente_id, Excedente.status == "DISPONIVEL",
            Excedente.retirar_ate > agora_brasilia_sem_fuso()).values(status="CANCELADO"))
        if resultado.rowcount != 1:
            db.session.rollback()
            return _erro("EXCEDENTE_INDISPONIVEL", "Este excedente não pode ser cancelado.", 409)
        _emitir("excedente.cancelado", {"excedente_id": excedente_id},
                destinatarios=(_dono(excedente),))
        db.session.commit()
        registrar_auditoria("excedente_cancelado", "ok", tipo=atual[0], ator_id=atual[1].id)
        return "", 204


@ns.route("/<int:excedente_id>/reservar")
class ReservarExcedente(Resource):
    @ns.response(429, "Cota de 30 reservas por hora")
    def post(self, excedente_id):
        empresa, erro = _empresa()
        if erro:
            return erro
        if not empresa.sem_fins_lucrativos:
            return _erro("APENAS_ONGS", "Apenas ONGs podem reservar excedentes.", 403)
        if _cota_esgotada("reservar", empresa.id, "empresa"):
            return _erro("MUITAS_TENTATIVAS", "Aguarde antes de fazer outra reserva.", 429)
        excedente = _consulta().filter_by(id=excedente_id).first()
        if not excedente:
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        if _eh_dono(excedente, ("empresa", empresa)):
            return _erro("EXCEDENTE_PROPRIO", "Não é possível reservar o próprio excedente.", 409)
        if status_efetivo(excedente) != "DISPONIVEL":
            return _erro("EXCEDENTE_INDISPONIVEL", "Excedente indisponível.", 409)
        resultado = db.session.execute(update(Excedente).where(
            Excedente.id == excedente_id, Excedente.status == "DISPONIVEL",
            Excedente.reservado_por_id.is_(None), Excedente.retirar_ate > agora_brasilia_sem_fuso(),
            # NULL (pessoa física) também é "outro publicador": NULL != id não seria verdadeiro no SQL
            or_(Excedente.estabelecimento_id.is_(None), Excedente.estabelecimento_id != empresa.id)).values(
                status="RESERVADO", reservado_por_id=empresa.id,
                reservado_em=_utc_naive()))
        if resultado.rowcount != 1:
            db.session.rollback()
            return _erro("EXCEDENTE_INDISPONIVEL", "Excedente indisponível.", 409)
        _emitir("excedente.reservado", {"excedente_id": excedente_id})
        _emitir("excedente.reservado", {"excedente_id": excedente_id, "ong": empresa.nome},
                publico=False, destinatarios=(_dono(excedente),))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_reservado", "ok", tipo="empresa", ator_id=empresa.id)
        return serializar_excedente(excedente, detalhe=True, atual=("empresa", empresa)), 200


@ns.route("/<int:excedente_id>/cancelar-reserva")
class CancelarReserva(Resource):
    def post(self, excedente_id):
        atual, erro = _sessao()
        if erro:
            return erro
        excedente = _consulta().filter_by(id=excedente_id).first()
        reservante = bool(excedente) and atual[0] == "empresa" and atual[1].id == excedente.reservado_por_id
        if not excedente or not (reservante or _eh_dono(excedente, atual)):
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        if status_efetivo(excedente) != "RESERVADO":
            return _erro("RESERVA_INDISPONIVEL", "Esta reserva não pode ser cancelada.", 409)
        reservante_id = excedente.reservado_por_id
        resultado = db.session.execute(update(Excedente).where(
            Excedente.id == excedente_id, Excedente.status == "RESERVADO",
            Excedente.retirar_ate > agora_brasilia_sem_fuso(),
            Excedente.reservado_por_id == reservante_id).values(
                status="DISPONIVEL", reservado_por_id=None, reservado_em=None))
        if resultado.rowcount != 1:
            db.session.rollback()
            return _erro("RESERVA_INDISPONIVEL", "Esta reserva não pode ser cancelada.", 409)
        _emitir("excedente.reserva_cancelada", {"excedente_id": excedente_id},
                destinatarios=(_dono(excedente), ("empresa", reservante_id)))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_reserva_cancelada", "ok", tipo=atual[0], ator_id=atual[1].id)
        return serializar_excedente(excedente, detalhe=True, atual=atual), 200


@ns.route("/<int:excedente_id>/confirmar-retirada")
class ConfirmarRetirada(Resource):
    def post(self, excedente_id):
        atual, erro = _sessao()
        if erro:
            return erro
        excedente = _consulta().filter(Excedente.id == excedente_id, _filtro_dono(atual)).first()
        if not excedente:
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        if status_efetivo(excedente) != "RESERVADO":
            return _erro("RETIRADA_INDISPONIVEL", "Não há reserva válida para confirmar.", 409)
        resultado = db.session.execute(update(Excedente).where(
            Excedente.id == excedente_id, Excedente.status == "RESERVADO",
            Excedente.retirar_ate > agora_brasilia_sem_fuso()).values(
                status="RETIRADO", retirado_em=_utc_naive()))
        if resultado.rowcount != 1:
            db.session.rollback()
            return _erro("RETIRADA_INDISPONIVEL", "Não há reserva válida para confirmar.", 409)
        _emitir("excedente.retirado", {"excedente_id": excedente_id},
                destinatarios=(_dono(excedente), ("empresa", excedente.reservado_por_id)))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_retirado", "ok", tipo=atual[0], ator_id=atual[1].id)
        return serializar_excedente(excedente, detalhe=True, atual=atual), 200
