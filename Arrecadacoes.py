"""Ações de arrecadação e contribuições verificadas de usuários cadastrados."""

import json
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app, request, send_from_directory
from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import SQLAlchemyError

from Auth import usuario_atual
from Publico import CATEGORIAS, UNIDADES, _municipio_uf
from models import Arrecadacao, Contribuicao, db


ns = Namespace("arrecadacoes", description="Ações de arrecadação e contribuições")

MAX_FOTO = 5 * 1024 * 1024
PERGUNTAS = ("dentro_validade", "embalagem_ok", "armazenado_ok", "nao_caseiro")
MOTIVOS_NAO = {
    "dentro_validade": ("ALIMENTO_VENCIDO", "Alimento vencido não pode ser doado."),
    "embalagem_ok": ("EMBALAGEM_INADEQUADA", "Alimento com embalagem danificada ou sinais de estrago não pode ser doado."),
    "armazenado_ok": ("ARMAZENAMENTO_INADEQUADO", "Alimento guardado fora das condições adequadas não pode ser doado."),
    "nao_caseiro": ("COMIDA_CASEIRA", "Comida feita em casa não pode ser doada por segurança."),
}
MIMES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}

acao_entrada = ns.model("ArrecadacaoEntrada", {
    "titulo": fields.String(required=True), "descricao": fields.String(required=True),
    "categorias": fields.List(fields.String, required=True),
    "meta_descricao": fields.String, "entrega_endereco": fields.String,
    "data_inicio": fields.String(required=True), "data_fim": fields.String(required=True),
})
erro_model = ns.model("ArrecadacaoErro", {
    "codigo": fields.String, "mensagem": fields.String,
    "campos": fields.Raw, "motivos": fields.List(fields.Raw),
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
        return None, _erro("APENAS_EMPRESAS", "Somente empresas podem criar e gerenciar ações.", 403)
    return atual[1], None


def _data(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _texto(valor, minimo, maximo):
    return valor.strip() if isinstance(valor, str) and minimo <= len(valor.strip()) <= maximo else None


def _serializar_acao(acao, *, detalhe=False):
    dados = {
        "id": acao.id, "titulo": acao.titulo, "descricao": acao.descricao,
        "categorias": acao.categorias.split(";"), "meta_descricao": acao.meta_descricao,
        "empresa": {"nome": acao.estabelecimento.nome,
                    "municipio_uf": _municipio_uf(acao.estabelecimento.endereco)},
        "entrega": {"municipio_uf": _municipio_uf(acao.entrega_endereco)},
        "data_inicio": acao.data_inicio.isoformat(), "data_fim": acao.data_fim.isoformat(),
        "contribuicoes_aceitas": sum(c.status == "ACEITA" for c in acao.contribuicoes),
    }
    if detalhe:
        dados["status"] = acao.status
        atual = usuario_atual()
        if not atual:
            motivo = "Entre para doar"
        elif atual[0] == "empresa" and atual[1].id == acao.estabelecimento_id:
            motivo = "Esta é a sua própria ação"
        elif acao.status != "ATIVA" or not acao.data_inicio <= date.today() <= acao.data_fim:
            motivo = "Ação encerrada"
        else:
            motivo = None
        dados["pode_contribuir"] = motivo is None
        dados["motivo_bloqueio"] = motivo
    return dados


def _validar_acao(corpo, empresa):
    campos = {}
    titulo = _texto(corpo.get("titulo"), 5, 80)
    if titulo is None:
        campos["titulo"] = "Informe um título entre 5 e 80 caracteres."
    descricao = _texto(corpo.get("descricao"), 10, 500)
    if descricao is None:
        campos["descricao"] = "Informe uma descrição entre 10 e 500 caracteres."
    categorias = corpo.get("categorias")
    if (not isinstance(categorias, list) or not categorias or
            any(not isinstance(c, str) or c not in CATEGORIAS for c in categorias) or
            len(set(categorias)) != len(categorias) or len(";".join(categorias)) > 300):
        campos["categorias"] = "Selecione uma ou mais categorias da lista, sem repetir."
    inicio = _data(corpo.get("data_inicio"))
    fim = _data(corpo.get("data_fim"))
    if inicio is None or inicio < date.today():
        campos["data_inicio"] = "Informe uma data inicial igual ou posterior a hoje."
    if fim is None or (inicio is not None and fim < inicio):
        campos["data_fim"] = "Informe uma data final igual ou posterior à inicial."
    meta = corpo.get("meta_descricao")
    if meta is not None and (not isinstance(meta, str) or len(meta.strip()) > 120):
        campos["meta_descricao"] = "Use até 120 caracteres."
    endereco = corpo.get("entrega_endereco")
    if endereco is None:
        endereco = empresa.endereco
    endereco = _texto(endereco, 5, 200)
    if endereco is None:
        campos["entrega_endereco"] = "Informe um endereço entre 5 e 200 caracteres."
    if campos:
        return None, campos
    return {
        "titulo": titulo, "descricao": descricao, "categorias": ";".join(categorias),
        "meta_descricao": meta.strip() if meta is not None else None,
        "entrega_endereco": endereco, "data_inicio": inicio, "data_fim": fim,
    }, {}


def _quantidade(valor):
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError):
        return None
    return numero if numero.is_finite() and numero <= Decimal("99999999.99") and numero == numero.quantize(Decimal("0.01")) else None


def _extensao_foto(dados):
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "webp"
    return None


def _validar_contribuicao(acao):
    formulario = request.form
    campos = {}
    motivos = []
    alimento = _texto(formulario.get("alimento"), 2, 100)
    if alimento is None:
        campos["alimento"] = "Informe o alimento em até 100 caracteres."
    categoria = _texto(formulario.get("categoria"), 1, 50)
    if categoria is None:
        campos["categoria"] = "Selecione uma categoria."
    quantidade = _quantidade(formulario.get("quantidade"))
    if quantidade is None:
        campos["quantidade"] = "Informe um número com até duas casas decimais."
    unidade = formulario.get("unidade_medida")
    if unidade not in UNIDADES:
        campos["unidade_medida"] = "Selecione uma unidade da lista."
    validade = _data(formulario.get("validade"))
    if validade is None:
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
        return None, campos, []
    dados_foto = foto.read(MAX_FOTO + 1)
    extensao = _extensao_foto(dados_foto)
    if len(dados_foto) > MAX_FOTO:
        campos["foto"] = "A foto deve ter até 5 MB."
    elif not extensao:
        campos["foto"] = "Envie uma foto JPEG, PNG ou WebP válida."
    if campos:
        return None, campos, []
    if quantidade <= 0:
        motivos.append({"codigo": "QUANTIDADE_INVALIDA", "mensagem": "A quantidade deve ser maior que zero."})
    if categoria not in acao.categorias.split(";"):
        motivos.append({"codigo": "CATEGORIA_NAO_ACEITA",
                        "mensagem": f"Esta ação não recebe a categoria {categoria}."})
    if validade < date.today():
        motivos.append({"codigo": "ALIMENTO_VENCIDO", "mensagem": "Alimento vencido não pode ser doado."})
    for pergunta, resposta in respostas.items():
        if resposta == "nao":
            codigo, mensagem = MOTIVOS_NAO[pergunta]
            if not any(motivo["codigo"] == codigo for motivo in motivos):
                motivos.append({"codigo": codigo, "mensagem": mensagem})
    return {
        "alimento": alimento, "categoria": categoria, "quantidade": quantidade,
        "unidade_medida": unidade, "validade": validade,
        "respostas": json.dumps(respostas, ensure_ascii=False),
        "foto_dados": dados_foto, "foto_extensao": extensao,
    }, {}, motivos


def _filtro_contribuinte(tipo, usuario):
    return {"doador_id": usuario.id} if tipo == "doador" else {"estabelecimento_id": usuario.id}


def _foto_url(contribuicao):
    return f"/reconecta/arrecadacoes/contribuicoes/{contribuicao.id}/foto"


@ns.route("/")
class Acoes(Resource):
    def get(self):
        """Lista pública das ações abertas dentro do período."""
        hoje = date.today()
        acoes = Arrecadacao.query.filter(
            Arrecadacao.status == "ATIVA", Arrecadacao.data_inicio <= hoje,
            Arrecadacao.data_fim >= hoje).order_by(
                Arrecadacao.criado_em.desc(), Arrecadacao.id.desc()).all()
        return [_serializar_acao(acao) for acao in acoes], 200

    @ns.expect(acao_entrada)
    @ns.response(400, "Dados inválidos", erro_model)
    @ns.response(403, "Apenas empresas", erro_model)
    def post(self):
        """Cria uma ação, somente para empresa cadastrada e autenticada."""
        empresa, erro = _empresa()
        if erro:
            return erro
        corpo = request.get_json(silent=True)
        corpo = corpo if isinstance(corpo, dict) else {}
        dados, campos = _validar_acao(corpo, empresa)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        acao = Arrecadacao(estabelecimento_id=empresa.id, **dados)
        db.session.add(acao)
        db.session.commit()
        return _serializar_acao(acao, detalhe=True), 201


@ns.route("/minhas")
class MinhasAcoes(Resource):
    def get(self):
        empresa, erro = _empresa()
        if erro:
            return erro
        acoes = Arrecadacao.query.filter_by(estabelecimento_id=empresa.id).order_by(
            Arrecadacao.criado_em.desc(), Arrecadacao.id.desc()).all()
        resultado = []
        for acao in acoes:
            dados = _serializar_acao(acao, detalhe=True)
            dados["entrega_endereco"] = acao.entrega_endereco
            dados["contribuicoes"] = [{
                "id": c.id, "alimento": c.alimento, "categoria": c.categoria,
                "quantidade": float(c.quantidade), "unidade_medida": c.unidade_medida,
                "validade": c.validade.isoformat(), "status": c.status,
                "quem": c.doador.nome.split()[0] if c.doador_id else c.estabelecimento.nome,
                "criado_em": c.criado_em.isoformat(), "foto_url": _foto_url(c),
            } for c in acao.contribuicoes]
            resultado.append(dados)
        return resultado, 200


@ns.route("/minhas-contribuicoes")
class MinhasContribuicoes(Resource):
    def get(self):
        atual, erro = _usuario()
        if erro:
            return erro
        tipo, usuario = atual
        contribuicoes = Contribuicao.query.filter_by(**_filtro_contribuinte(tipo, usuario)).order_by(
            Contribuicao.criado_em.desc(), Contribuicao.id.desc()).all()
        return [{
            "id": c.id, "alimento": c.alimento, "categoria": c.categoria,
            "quantidade": float(c.quantidade), "unidade_medida": c.unidade_medida,
            "validade": c.validade.isoformat(), "status": c.status,
            "criado_em": c.criado_em.isoformat(), "foto_url": _foto_url(c),
            "arrecadacao": {"id": c.arrecadacao.id, "titulo": c.arrecadacao.titulo,
                            "empresa": {"nome": c.arrecadacao.estabelecimento.nome}},
            "entrega": {"endereco": c.arrecadacao.entrega_endereco,
                        "data_fim": c.arrecadacao.data_fim.isoformat()},
        } for c in contribuicoes], 200


@ns.route("/<int:acao_id>")
class AcaoDetalhe(Resource):
    def get(self, acao_id):
        acao = db.session.get(Arrecadacao, acao_id)
        if not acao:
            return _erro("ACAO_NAO_ENCONTRADA", "Ação não encontrada.", 404)
        return _serializar_acao(acao, detalhe=True), 200


@ns.route("/<int:acao_id>/encerrar")
class EncerrarAcao(Resource):
    def post(self, acao_id):
        empresa, erro = _empresa()
        if erro:
            return erro
        acao = Arrecadacao.query.filter_by(id=acao_id, estabelecimento_id=empresa.id).first()
        if not acao:
            return _erro("ACAO_NAO_ENCONTRADA", "Ação não encontrada.", 404)
        acao.status = "ENCERRADA"
        db.session.commit()
        return _serializar_acao(acao, detalhe=True), 200


@ns.route("/<int:acao_id>/contribuicoes")
class Contribuir(Resource):
    def post(self, acao_id):
        atual, erro = _usuario()
        if erro:
            return erro
        tipo, usuario = atual
        acao = db.session.get(Arrecadacao, acao_id)
        if not acao:
            return _erro("ACAO_NAO_ENCONTRADA", "Ação não encontrada.", 404)
        if tipo == "empresa" and usuario.id == acao.estabelecimento_id:
            return _erro("PROPRIA_ACAO", "Sua empresa não pode contribuir para a própria ação.", 409)
        if acao.status != "ATIVA" or not acao.data_inicio <= date.today() <= acao.data_fim:
            return _erro("CONTRIBUICAO_RECUSADA", "Esta ação não está recebendo alimentos.", 422,
                         motivos=[{"codigo": "ACAO_INDISPONIVEL", "mensagem": "Esta ação está encerrada ou fora do período."}])
        dados, campos, motivos = _validar_contribuicao(acao)
        if campos:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400, campos=campos)
        if motivos:
            return _erro("CONTRIBUICAO_RECUSADA", "Este alimento não pôde ser aceito.", 422,
                         motivos=motivos)
        extensao = dados.pop("foto_extensao")
        foto_dados = dados.pop("foto_dados")
        nome = f"{secrets.token_hex(16)}.{extensao}"
        pasta = Path(current_app.instance_path) / "uploads" / "contribuicoes"
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / nome
        try:
            with caminho.open("xb") as arquivo:
                arquivo.write(foto_dados)
            contribuicao = Contribuicao(arrecadacao_id=acao.id, foto_arquivo=nome,
                                        **_filtro_contribuinte(tipo, usuario), **dados)
            db.session.add(contribuicao)
            db.session.commit()
        except (OSError, SQLAlchemyError):
            db.session.rollback()
            caminho.unlink(missing_ok=True)
            current_app.logger.exception("Falha ao salvar contribuição")
            return _erro("ERRO_INTERNO", "Não foi possível salvar a contribuição.", 500)
        return {"id": contribuicao.id, "status": "ACEITA",
                "entrega": {"endereco": acao.entrega_endereco,
                            "data_fim": acao.data_fim.isoformat()}}, 201


@ns.route("/contribuicoes/<int:contribuicao_id>/foto")
class FotoContribuicao(Resource):
    def get(self, contribuicao_id):
        atual = usuario_atual()
        contribuicao = db.session.get(Contribuicao, contribuicao_id)
        if not atual or not contribuicao:
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        tipo, usuario = atual
        autorizado = (tipo == "doador" and contribuicao.doador_id == usuario.id) or (
            tipo == "empresa" and (contribuicao.estabelecimento_id == usuario.id or
                                    contribuicao.arrecadacao.estabelecimento_id == usuario.id))
        if not autorizado or not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", contribuicao.foto_arquivo):
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        pasta = Path(current_app.instance_path) / "uploads" / "contribuicoes"
        caminho = pasta / contribuicao.foto_arquivo
        if not caminho.is_file():
            return _erro("FOTO_NAO_ENCONTRADA", "Foto não encontrada.", 404)
        tipo_mime = MIMES[contribuicao.foto_arquivo.rsplit(".", 1)[1]]
        resposta = send_from_directory(pasta, contribuicao.foto_arquivo, mimetype=tipo_mime)
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["Cache-Control"] = "private, no-store"
        return resposta
