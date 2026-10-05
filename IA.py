"""Sugestões locais para pedidos e leitura agregada do dashboard."""

import threading
import time
from collections import deque

from flask import request
from flask_restx import Namespace, Resource, fields

from Auth import usuario_atual
from Dashboard import montar_dashboard
from llm_service import interpretar_pedido, resumir_dashboard

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

_acessos = {}
_acessos_lock = threading.Lock()
JANELA_SEGUNDOS = 60
LIMITE_POR_IP = 10


def _permitir_resumo(ip):
    agora = time.monotonic()
    with _acessos_lock:
        # Evita acumular IPs antigos em um processo de longa duração.
        if len(_acessos) > 2048:
            for chave in list(_acessos):
                if not _acessos[chave] or agora - _acessos[chave][-1] >= JANELA_SEGUNDOS:
                    del _acessos[chave]
        acessos = _acessos.setdefault(ip, deque())
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
        return interpretar_pedido(texto.strip()), 200


@ns.route("/resumo-dashboard")
class ResumoDashboard(Resource):
    @ns.response(200, "Resumo dos indicadores", resumo_model)
    def post(self):
        if not _permitir_resumo(request.remote_addr or "desconhecido"):
            return {"codigo": "LIMITE_IA", "mensagem": "Limite de 10 resumos por minuto atingido."}, 429, {
                "Retry-After": "60"}
        # O corpo do cliente é ignorado: só os agregados calculados aqui seguem ao modelo.
        return resumir_dashboard(montar_dashboard()), 200
