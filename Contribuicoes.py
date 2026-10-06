"""Contribuições a pedidos, com foto privada e validação alimentar."""

import json
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, request, send_from_directory
from flask_restx import Namespace, Resource
from sqlalchemy.exc import SQLAlchemyError

from Auth import usuario_atual
from fuso import agora_brasilia_sem_fuso, hoje_brasilia, iso_evento, iso_prazo
from models import Contribuicao, Doacao, ItemDoacao, db

ns = Namespace("contribuicoes", description="Fotos privadas das doações recebidas")
MAX_FOTO = 5 * 1024 * 1024
PERGUNTAS = ("dentro_validade", "embalagem_ok", "armazenado_ok", "nao_caseiro")
MOTIVOS_NAO = {
    "dentro_validade": ("ALIMENTO_VENCIDO", "Alimento vencido não pode ser doado."),
    "embalagem_ok": ("EMBALAGEM_INADEQUADA", "Alimento com embalagem danificada não pode ser doado."),
    "armazenado_ok": ("ARMAZENAMENTO_INADEQUADO", "Alimento mal armazenado não pode ser doado."),
    "nao_caseiro": ("COMIDA_CASEIRA", "Comida feita em casa não pode ser doada."),
}
MIMES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def _erro(codigo, mensagem, status, **extras):
    return {"codigo": codigo, "mensagem": mensagem, **extras}, status


def _extensao_foto(dados):
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


def _quantidade(valor):
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError):
        return None
    if not numero.is_finite() or abs(numero) > Decimal("99999999.99"):
        return None
    try:
        duas_casas = numero.quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    if numero != duas_casas:
        return None
    return numero


def foto_url(contribuicao):
    return f"/reconecta/contribuicoes/{contribuicao.id}/foto"


def serializar_contribuicao(contribuicao, *, entrega=False):
    dados = {
        "id": contribuicao.id,
        "doacao_id": contribuicao.doacao_id,
        "item_id": contribuicao.item_doacao_id,
        "alimento": contribuicao.item_doacao.nome,
        "categoria": contribuicao.item_doacao.categoria,
        "quantidade": float(contribuicao.quantidade),
        "unidade_medida": contribuicao.item_doacao.unidade_medida,
        "validade": contribuicao.validade.isoformat(),
        "status": contribuicao.status,
        "quem": (contribuicao.doador.nome.split()[0] if contribuicao.doador_id
                 else contribuicao.estabelecimento.nome),
        "criado_em": iso_evento(contribuicao.criado_em),
        "foto_url": foto_url(contribuicao),
    }
    if entrega:
        dados["pedido"] = {"id": contribuicao.doacao_id,
                           "empresa": contribuicao.doacao.estabelecimento.nome}
        dados["entrega"] = {
            "endereco": contribuicao.doacao.estabelecimento.endereco,
            "receber_ate": iso_prazo(contribuicao.doacao.data_limite_retirada),
        }
    return dados


def criar_contribuicao(doacao):
    atual = usuario_atual()
    if not atual:
        return _erro("NAO_AUTENTICADO", "Entre para doar.", 401)
    tipo, usuario = atual
    if tipo == "empresa" and usuario.id == doacao.estabelecimento_id:
        return _erro("PEDIDO_PROPRIO", "Sua empresa não pode doar para o próprio pedido.", 409)
    if (doacao.estabelecimento_id is None or doacao.status != "DISPONIVEL" or
            doacao.data_limite_retirada <= agora_brasilia_sem_fuso()):
        return _erro("CONTRIBUICAO_RECUSADA", "Este pedido não recebe mais doações.", 422,
                     motivos=[{"codigo": "PEDIDO_INDISPONIVEL", "mensagem": "Pedido encerrado."}])

    formulario = request.form
    campos = {}
    motivos = []
    item_raw = formulario.get("item_id")
    item_id = int(item_raw) if item_raw and item_raw.isascii() and item_raw.isdigit() else None
    item = db.session.get(ItemDoacao, item_id) if item_id else None
    if item_id is None:
        campos["item_id"] = "Selecione um item do pedido."
    elif not item or item.doacao_id != doacao.id:
        motivos.append({"codigo": "ITEM_NAO_ACEITO", "mensagem": "Este item não pertence ao pedido."})
    quantidade = _quantidade(formulario.get("quantidade"))
    if quantidade is None:
        campos["quantidade"] = "Informe um número com até duas casas decimais."
    elif quantidade <= 0:
        motivos.append({"codigo": "QUANTIDADE_INVALIDA", "mensagem": "A quantidade deve ser maior que zero."})
    try:
        validade = date.fromisoformat(formulario.get("validade", ""))
    except (ValueError, TypeError):
        validade = None
        campos["validade"] = "Informe uma data válida no formato AAAA-MM-DD."
    respostas = {}
    for pergunta in PERGUNTAS:
        resposta = formulario.get(pergunta)
        if resposta not in ("sim", "nao"):
            campos[pergunta] = "Responda sim ou não."
        else:
            respostas[pergunta] = resposta
    foto = request.files.get("foto")
    if foto is None:
        campos["foto"] = "Envie uma foto JPEG, PNG ou WebP."
    if campos:
        return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
    dados_foto = foto.read(MAX_FOTO + 1)
    extensao = _extensao_foto(dados_foto)
    if len(dados_foto) > MAX_FOTO:
        campos["foto"] = "A foto deve ter até 5 MB."
    elif not extensao:
        campos["foto"] = "Envie uma foto JPEG, PNG ou WebP válida."
    if campos:
        return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
    if item and formulario.get("categoria") and formulario["categoria"] != item.categoria:
        motivos.append({"codigo": "CATEGORIA_NAO_ACEITA", "mensagem": "Categoria diferente do item pedido."})
    if validade < hoje_brasilia():
        motivos.append({"codigo": "ALIMENTO_VENCIDO", "mensagem": "Alimento vencido não pode ser doado."})
    for pergunta, resposta in respostas.items():
        if resposta == "nao":
            codigo, mensagem = MOTIVOS_NAO[pergunta]
            if not any(motivo["codigo"] == codigo for motivo in motivos):
                motivos.append({"codigo": codigo, "mensagem": mensagem})
    if motivos:
        return _erro("CONTRIBUICAO_RECUSADA", "Este alimento não pôde ser aceito.", 422,
                     motivos=motivos)

    nome = f"{secrets.token_hex(16)}.{extensao}"
    pasta = Path(current_app.instance_path) / "uploads" / "contribuicoes"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome
    try:
        with caminho.open("xb") as arquivo:
            arquivo.write(dados_foto)
        contribuicao = Contribuicao(
            doacao_id=doacao.id, item_doacao_id=item.id,
            doador_id=usuario.id if tipo == "doador" else None,
            estabelecimento_id=usuario.id if tipo == "empresa" else None,
            alimento=item.nome, categoria=item.categoria, quantidade=quantidade,
            unidade_medida=item.unidade_medida, validade=validade,
            respostas=json.dumps(respostas, ensure_ascii=False), foto_arquivo=nome,
            status="ACEITA")
        db.session.add(contribuicao)
        db.session.commit()
    except (OSError, SQLAlchemyError):
        db.session.rollback()
        caminho.unlink(missing_ok=True)
        current_app.logger.exception("Falha ao salvar contribuição")
        return _erro("ERRO_INTERNO", "Não foi possível salvar a doação.", 500)
    return {"id": contribuicao.id, "status": "ACEITA",
            "entrega": {"endereco": doacao.estabelecimento.endereco,
                        "receber_ate": iso_prazo(doacao.data_limite_retirada)}}, 201


@ns.route("/<int:contribuicao_id>/foto")
class FotoContribuicao(Resource):
    def get(self, contribuicao_id):
        atual = usuario_atual()
        contribuicao = db.session.get(Contribuicao, contribuicao_id)
        if not atual or not contribuicao:
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        tipo, usuario = atual
        autorizado = ((tipo == "doador" and contribuicao.doador_id == usuario.id) or
                      (tipo == "empresa" and (contribuicao.estabelecimento_id == usuario.id or
                                              contribuicao.doacao.estabelecimento_id == usuario.id)))
        if not autorizado or not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", contribuicao.foto_arquivo):
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        pasta = Path(current_app.instance_path) / "uploads" / "contribuicoes"
        if not (pasta / contribuicao.foto_arquivo).is_file():
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        resposta = send_from_directory(pasta, contribuicao.foto_arquivo,
                                        mimetype=MIMES[contribuicao.foto_arquivo.rsplit(".", 1)[1]])
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["Cache-Control"] = "private, no-store"
        return resposta
