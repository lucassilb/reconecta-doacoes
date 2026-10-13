"""Publicação e resgate de excedentes alimentares entre CNPJs cadastrados."""

import re
import threading
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import current_app, request
from flask_restx import Namespace, Resource, fields
from sqlalchemy import or_, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from Auth import registrar_auditoria, usuario_atual
from eventos import emitir as _emitir
from Publico import CATEGORIAS, UNIDADES, _inteiro_positivo, _municipio_uf
from fuso import agora_brasilia_sem_fuso, hoje_brasilia, iso_evento, iso_prazo
from models import Doacao, Estabelecimento, Excedente, ItemDoacao, ItemExcedente, _utc_naive, db

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
})
saida = ns.model("ExcedenteSaida", {
    "id": fields.Integer, "empresa": fields.Raw, "retirar_ate": fields.String,
    "itens": fields.List(fields.Raw), "status": fields.String,
    "pode_reservar": fields.Boolean, "motivo_bloqueio": fields.String,
    "retirada": fields.Raw, "reservado_por": fields.Raw,
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


def _ongs_compativeis(categorias, uf, publicador_id):
    """Seleciona ONGs com pedido aberto na mesma UF e categoria."""
    if not uf or not categorias:
        return ()
    ids = (db.session.query(Estabelecimento.id)
           .join(Doacao, Doacao.estabelecimento_id == Estabelecimento.id)
           .filter(Estabelecimento.sem_fins_lucrativos.is_(True),
                   Estabelecimento.id != publicador_id,
                   Doacao.status == "DISPONIVEL",
                   Doacao.data_limite_retirada > agora_brasilia_sem_fuso(),
                   Doacao.itens.any(ItemDoacao.categoria.in_(categorias)),
                   or_(Estabelecimento.endereco.ilike(f"%/{uf} - %"),
                       Estabelecimento.endereco.ilike(f"%/{uf}")))
           .distinct().all())
    return tuple(("empresa", id_) for (id_,) in ids)


def _empresa():
    atual = usuario_atual()
    if not atual:
        return None, _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
    if atual[0] != "empresa":
        return None, _erro("APENAS_EMPRESAS", "Use um cadastro com CNPJ.", 403)
    return atual[1], None


def _cota_esgotada(acao, empresa_id):
    agora = time.monotonic()
    chave = (acao, empresa_id)
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
    if atual[1].id == excedente.estabelecimento_id:
        return "Não é possível reservar o próprio excedente"
    if status_efetivo(excedente) != "DISPONIVEL":
        return "Excedente indisponível"
    return None


def serializar_excedente(excedente, *, detalhe=False, atual=None):
    dados = {
        "id": excedente.id,
        "empresa": {"nome": excedente.publicador.nome,
                    "municipio_uf": _municipio_uf(excedente.publicador.endereco)},
        "retirar_ate": iso_prazo(excedente.retirar_ate),
        "itens": [{"nome": item.nome, "categoria": item.categoria,
                   "quantidade": float(item.quantidade), "unidade_medida": item.unidade_medida,
                   "validade": item.validade.isoformat()} for item in excedente.itens],
        "status": status_efetivo(excedente),
    }
    if detalhe:
        motivo = _bloqueio(excedente, atual)
        dados.update(pode_reservar=motivo is None, motivo_bloqueio=motivo,
                     observacao=excedente.observacao,
                     criado_em=iso_evento(excedente.criado_em))
        if atual and atual[0] == "empresa":
            usuario_id = atual[1].id
            if usuario_id == excedente.reservado_por_id:
                dados["retirada"] = {"endereco": excedente.publicador.endereco,
                                     "retirar_ate": iso_prazo(excedente.retirar_ate)}
            if usuario_id == excedente.estabelecimento_id and excedente.reservado_por:
                dados["reservado_por"] = {"id": excedente.reservado_por_id,
                                          "nome": excedente.reservado_por.nome}
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
            query = query.join(Excedente.publicador).filter(or_(
                Estabelecimento.endereco.ilike(f"%/{uf} - %"),
                Estabelecimento.endereco.ilike(f"%/{uf}")))
        total = query.count()
        anuncios = query.order_by(Excedente.criado_em.desc(), Excedente.id.desc()).offset((pagina - 1) * tamanho).limit(tamanho).all()
        return [serializar_excedente(item) for item in anuncios], 200, {
            "X-Total-Count": str(total), "X-Pagina": str(pagina), "X-Por-Pagina": str(tamanho)}

    @ns.expect(entrada)
    @ns.response(201, "Excedente publicado", saida)
    @ns.response(429, "Cota de 20 publicações por hora")
    def post(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        if not empresa.atividade_alimentar:
            return _erro("PERFIL_SEM_ATIVIDADE_ALIMENTAR", "Este CNPJ não pode publicar excedentes.", 403)
        if _cota_esgotada("publicar", empresa.id):
            return _erro("MUITAS_TENTATIVAS", "Aguarde antes de publicar outro excedente.", 429)
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        prazo, itens, observacao, campos = _validar(corpo)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        excedente = Excedente(estabelecimento_id=empresa.id, retirar_ate=prazo,
                              observacao=observacao.strip() if observacao else None)
        try:
            db.session.add(excedente)
            db.session.flush()
            db.session.add_all(ItemExcedente(excedente_id=excedente.id, **item) for item in itens)
            categorias = sorted({item["categoria"] for item in itens})
            _emitir("excedente.publicado", {
                "excedente_id": excedente.id, "organizacao": empresa.nome,
                "municipio_uf": _municipio_uf(empresa.endereco),
                "categorias": categorias,
                "retirar_ate": iso_prazo(prazo)},
                destinatarios=_ongs_compativeis(categorias,
                                                (_municipio_uf(empresa.endereco) or "").rsplit("/", 1)[-1],
                                                empresa.id))
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception("Falha ao criar excedente")
            return _erro("ERRO_INTERNO", "Não foi possível publicar o excedente.", 500)
        registrar_auditoria("excedente_publicado", "ok", tipo="empresa", ator_id=empresa.id)
        return serializar_excedente(excedente, detalhe=True, atual=("empresa", empresa)), 201


@ns.route("/meus")
class MeusExcedentes(Resource):
    def get(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        anuncios = _consulta().filter_by(estabelecimento_id=empresa.id).order_by(Excedente.criado_em.desc(), Excedente.id.desc()).all()
        return [serializar_excedente(item, detalhe=True, atual=("empresa", empresa)) for item in anuncios], 200


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
        empresa, erro = _empresa()
        if erro:
            return erro
        excedente = db.session.get(Excedente, excedente_id)
        if not excedente or excedente.estabelecimento_id != empresa.id:
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
                destinatarios=(("empresa", empresa.id),))
        db.session.commit()
        registrar_auditoria("excedente_cancelado", "ok", tipo="empresa", ator_id=empresa.id)
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
        if _cota_esgotada("reservar", empresa.id):
            return _erro("MUITAS_TENTATIVAS", "Aguarde antes de fazer outra reserva.", 429)
        excedente = _consulta().filter_by(id=excedente_id).first()
        if not excedente:
            return _erro("EXCEDENTE_NAO_ENCONTRADO", "Excedente não encontrado.", 404)
        if empresa.id == excedente.estabelecimento_id:
            return _erro("EXCEDENTE_PROPRIO", "Não é possível reservar o próprio excedente.", 409)
        if status_efetivo(excedente) != "DISPONIVEL":
            return _erro("EXCEDENTE_INDISPONIVEL", "Excedente indisponível.", 409)
        resultado = db.session.execute(update(Excedente).where(
            Excedente.id == excedente_id, Excedente.status == "DISPONIVEL",
            Excedente.reservado_por_id.is_(None), Excedente.retirar_ate > agora_brasilia_sem_fuso(),
            Excedente.estabelecimento_id != empresa.id).values(
                status="RESERVADO", reservado_por_id=empresa.id,
                reservado_em=_utc_naive()))
        if resultado.rowcount != 1:
            db.session.rollback()
            return _erro("EXCEDENTE_INDISPONIVEL", "Excedente indisponível.", 409)
        _emitir("excedente.reservado", {"excedente_id": excedente_id})
        _emitir("excedente.reservado", {"excedente_id": excedente_id, "ong": empresa.nome},
                publico=False, destinatarios=(("empresa", excedente.estabelecimento_id),))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_reservado", "ok", tipo="empresa", ator_id=empresa.id)
        return serializar_excedente(excedente, detalhe=True, atual=("empresa", empresa)), 200


@ns.route("/<int:excedente_id>/cancelar-reserva")
class CancelarReserva(Resource):
    def post(self, excedente_id):
        empresa, erro = _empresa()
        if erro:
            return erro
        excedente = _consulta().filter_by(id=excedente_id).first()
        if not excedente or empresa.id not in (excedente.estabelecimento_id, excedente.reservado_por_id):
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
                destinatarios=(("empresa", excedente.estabelecimento_id),
                               ("empresa", reservante_id)))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_reserva_cancelada", "ok", tipo="empresa", ator_id=empresa.id)
        return serializar_excedente(excedente, detalhe=True, atual=("empresa", empresa)), 200


@ns.route("/<int:excedente_id>/confirmar-retirada")
class ConfirmarRetirada(Resource):
    def post(self, excedente_id):
        empresa, erro = _empresa()
        if erro:
            return erro
        excedente = _consulta().filter_by(id=excedente_id, estabelecimento_id=empresa.id).first()
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
                destinatarios=(("empresa", excedente.estabelecimento_id),
                               ("empresa", excedente.reservado_por_id)))
        db.session.commit()
        db.session.refresh(excedente)
        registrar_auditoria("excedente_retirado", "ok", tipo="empresa", ator_id=empresa.id)
        return serializar_excedente(excedente, detalhe=True, atual=("empresa", empresa)), 200
