"""Sugestões locais para pedidos e leitura agregada do dashboard."""

import threading
import time
from collections import deque

from flask import request
from flask_restx import Namespace, Resource, fields

from sqlalchemy.orm import selectinload

import geo
from Auth import usuario_atual
from conexao import casar
from Dashboard import montar_dashboard
from fuso import agora_brasilia_sem_fuso
from llm_service import interpretar_pedido, resumir_dashboard
from models import Doacao
from Publico import _municipio_uf, serializar_doacao
from risco_descarte import prever as prever_risco

ns = Namespace("ia", description="Sugestões com modelo local e regras de fallback")

item_model = ns.model("ItemSugeridoIA", {
    "nome": fields.String, "categoria": fields.String,
    "quantidade": fields.Float, "unidade_medida": fields.String,
})
pedido_model = ns.model("PedidoSugeridoIA", {
    "itens": fields.List(fields.Nested(item_model)), "receber_ate": fields.String,
    "observacoes": fields.String, "fonte": fields.String, "modelo": fields.String,
})
resumo_model = ns.model("ResumoDashboardIA", {
    "resumo": fields.String, "recomendacoes": fields.List(fields.String),
    "fonte": fields.String, "modelo": fields.String, "gerado_em": fields.String,
})
risco_model = ns.model("LoteRiscoDescarteIA", {
    "categoria": fields.String(required=True), "dias_validade": fields.Integer(required=True),
    "quantidade_kg": fields.Float(required=True), "perecivel": fields.Boolean,
    "temperatura_c": fields.Float, "armazenamento": fields.String,
    "dia_semana": fields.Integer, "hora_publicacao": fields.Integer,
    "uf": fields.String, "distancia_ong_km": fields.Float,
})

_acessos = {}
_acessos_lock = threading.Lock()
JANELA_SEGUNDOS = 60
LIMITE_POR_IP = 10


def _permitir(chave):
    """Janela deslizante em memória (por processo): até LIMITE_POR_IP chamadas por minuto."""
    agora = time.monotonic()
    with _acessos_lock:
        # Evita acumular IPs antigos em um processo de longa duração.
        if len(_acessos) > 2048:
            for chave in list(_acessos):
                if not _acessos[chave] or agora - _acessos[chave][-1] >= JANELA_SEGUNDOS:
                    del _acessos[chave]
        acessos = _acessos.setdefault(chave, deque())
        while acessos and agora - acessos[0] >= JANELA_SEGUNDOS:
            acessos.popleft()
        if len(acessos) >= LIMITE_POR_IP:
            return False
        acessos.append(agora)
        return True


@ns.route("/interpretar-pedido")
class InterpretarPedido(Resource):
    @ns.expect(ns.model("TextoPedidoIA", {"texto": fields.String(required=True)}))
    @ns.response(200, "Sugestão para revisão", pedido_model)
    @ns.response(429, "Limite de 10 interpretações por minuto por empresa")
    def post(self):
        atual = usuario_atual()
        if not atual:
            return {"codigo": "NAO_AUTENTICADO", "mensagem": "Entre para continuar."}, 401
        if atual[0] != "empresa":
            return {"codigo": "APENAS_EMPRESAS",
                    "mensagem": "Somente empresas podem interpretar pedidos."}, 403
        corpo = request.get_json(silent=True)
        texto = corpo.get("texto") if isinstance(corpo, dict) else None
        if not isinstance(texto, str) or not 5 <= len(texto.strip()) <= 600:
            return {"codigo": "DADOS_INVALIDOS", "mensagem": "Corrija os campos indicados.",
                    "campos": {"texto": "Informe de 5 a 600 caracteres."}}, 400
        # A chamada pode ocupar o modelo local por até 90 s: limite por empresa logada.
        if not _permitir(f"empresa:{atual[1].id}"):
            return {"codigo": "MUITAS_TENTATIVAS",
                    "mensagem": "Limite de 10 interpretações por minuto atingido. "
                                "Tente de novo em instantes."}, 429, {"Retry-After": "60"}
        return interpretar_pedido(texto.strip()), 200


@ns.route("/resumo-dashboard")
class ResumoDashboard(Resource):
    @ns.response(200, "Resumo dos indicadores", resumo_model)
    def post(self):
        if not _permitir(f"ip:{request.remote_addr or 'desconhecido'}"):
            return {"codigo": "LIMITE_IA", "mensagem": "Limite de 10 resumos por minuto atingido."}, 429, {
                "Retry-After": "60"}
        # O corpo do cliente é ignorado: só os agregados calculados aqui seguem ao modelo.
        return resumir_dashboard(montar_dashboard()), 200


@ns.route("/risco-descarte")
class RiscoDescarte(Resource):
    @ns.expect(risco_model)
    @ns.response(200, "Probabilidade e prioridade estimadas em dados simulados")
    @ns.response(400, "Lote inválido")
    @ns.response(429, "Limite de 10 análises por minuto por IP")
    def post(self):
        if not _permitir(f"risco:{request.remote_addr or 'desconhecido'}"):
            return {"codigo": "LIMITE_IA", "mensagem": "Limite de 10 análises por minuto atingido."}, 429, {
                "Retry-After": "60"}
        try:
            return prever_risco(request.get_json(silent=True)), 200
        except ValueError as erro:
            return {"codigo": "DADOS_INVALIDOS", "mensagem": str(erro)}, 400
        except OSError:
            return {"codigo": "MODELO_INDISPONIVEL", "mensagem": "Modelo de risco indisponível."}, 503


def _pedidos_abertos():
    """Pedidos DISPONIVEL no prazo, serializados para o casamento."""
    pedidos = (Doacao.query.options(
        selectinload(Doacao.estabelecimento), selectinload(Doacao.itens),
        selectinload(Doacao.contribuicoes))
        .filter(Doacao.estabelecimento_id.isnot(None),
                Doacao.status == "DISPONIVEL",
                Doacao.data_limite_retirada > agora_brasilia_sem_fuso())
        .order_by(Doacao.data_limite_retirada).all())
    resultado = []
    for pedido in pedidos:
        dados = serializar_doacao(pedido, incluir_status=True)
        dados["estabelecimento_id"] = pedido.estabelecimento_id
        resultado.append(dados)
    return resultado


@ns.route("/sugerir-destino")
class SugerirDestino(Resource):
    @ns.expect(ns.model("TextoDestinoIA", {
        "texto": fields.String(required=True),
        "cep": fields.String(description="Opcional, só pessoa física: CEP para ordenar por distância"),
        "origem": fields.Raw(description="Opcional, só pessoa física: {latitude, longitude}; "
                                         "usado nesta consulta e não gravado")}))
    @ns.response(200, "Sugestões de destino para o excedente", pedido_model)
    def post(self):
        """Interpreta o que a pessoa tem e sugere os pedidos abertos que combinam."""
        atual = usuario_atual()
        if not atual:
            return {"codigo": "NAO_AUTENTICADO", "mensagem": "Entre para continuar."}, 401
        tipo, usuario = atual
        corpo = request.get_json(silent=True)
        texto = corpo.get("texto") if isinstance(corpo, dict) else None
        if not isinstance(texto, str) or not 5 <= len(texto.strip()) <= 600:
            return {"codigo": "DADOS_INVALIDOS", "mensagem": "Corrija os campos indicados.",
                    "campos": {"texto": "Descreva em 5 a 600 caracteres o que sobrou."}}, 400
        if not _permitir(f"sugerir:{tipo}:{usuario.id}"):
            return {"codigo": "MUITAS_TENTATIVAS",
                    "mensagem": "Limite de 10 sugestões por minuto atingido. "
                                "Tente de novo em instantes."}, 429, {"Retry-After": "60"}
        interpretado = interpretar_pedido(texto.strip())
        uf = None
        if tipo == "empresa":
            municipio_uf = _municipio_uf(usuario.endereco)
            uf = municipio_uf.rsplit("/", 1)[-1] if municipio_uf else None
            # distância a partir do endereço da organização (cache ou centróide; sem rede)
            origem = geo.localizar(usuario.endereco)
        else:
            # pessoa física: CEP opcional digitado no assistente (ou coordenada enviada por
            # outro cliente); nada fica ligado à pessoa
            origem = (geo.localizar_cep(corpo.get("cep")) if corpo.get("cep")
                      else geo.ponto_informado(corpo.get("origem")))
        pedidos = geo.anotar_distancias(_pedidos_abertos(), origem)
        sugestoes = casar(interpretado["itens"], pedidos, uf)
        return {"itens": interpretado["itens"], "sugestoes": sugestoes,
                "origem": {"precisao": origem.precisao} if origem is not None else None,
                "pode_publicar_excedente": bool(
                    tipo == "empresa" and getattr(usuario, "atividade_alimentar", False)),
                "fonte": interpretado.get("fonte"), "modelo": interpretado.get("modelo")}, 200
