"""Tempo real por Server-Sent Events, novidades em JSON e notificações do usuário.

O fluxo SSE entrega eventos públicos e os destinados ao usuário logado, consultando
a tabela `eventos` a cada ~2 s. Cada consulta usa a sessão e a devolve ao pool
(`db.session.remove()`), então a conexão SSE não segura uma conexão do banco entre
uma consulta e outra. O navegador reconecta sozinho quando o fluxo encerra aos 5 min
(e reenvia Last-Event-ID) ou, em caso de 503, cai para `GET /reconecta/novidades`.
"""

import json
import threading
import time

from flask import Response, request, stream_with_context
from flask_restx import Namespace, Resource, fields
from sqlalchemy import and_, func, or_

from Auth import usuario_atual
from eventos import Evento
from fuso import iso_evento
from models import db

ns = Namespace("tempo_real", description="Eventos ao vivo, novidades e notificações")

INTERVALO_CONSULTA = 2.0
BATIMENTO_SEGUNDOS = 15.0
DURACAO_MAX = 300.0
MAX_CONEXOES = 20
MAX_NOVIDADES = 50
MAX_NOTIFICACOES = 30

_conexoes = 0
_conexoes_lock = threading.Lock()


class NotificacaoLeitura(db.Model):
    """Último id de evento marcado como lido por usuário."""
    __tablename__ = 'notificacao_leitura'
    tipo = db.Column(db.String(10), primary_key=True)
    usuario_id = db.Column(db.Integer, primary_key=True)
    ultimo_id = db.Column(db.Integer, nullable=False, default=0)


def _erro(codigo, mensagem, status):
    return {"codigo": codigo, "mensagem": mensagem}, status


def _destino():
    """("empresa"|"doador", id) do usuário logado, ou None."""
    atual = usuario_atual()
    return (atual[0], atual[1].id) if atual else None


def _visivel(chave):
    if chave is None:
        return Evento.publico.is_(True)
    return or_(Evento.publico.is_(True),
               and_(Evento.dest_tipo == chave[0], Evento.dest_id == chave[1]))


def _serializar(evento):
    try:
        dados = json.loads(evento.dados or "{}")
    except ValueError:
        dados = {}
    return {"id": evento.id, "tipo": evento.tipo,
            "criado_em": iso_evento(evento.criado_em), "dados": dados}


def _consultar(desde, chave, limite):
    try:
        return (Evento.query.filter(Evento.id > desde, _visivel(chave))
                .order_by(Evento.id).limit(limite).all())
    finally:
        db.session.remove()


def _ultimo_id():
    try:
        return db.session.query(func.max(Evento.id)).scalar() or 0
    finally:
        db.session.remove()


def _desde():
    valor = request.headers.get("Last-Event-ID") or request.args.get("desde")
    if valor and str(valor).isascii() and str(valor).isdigit():
        return int(valor)
    return 0


def _fluxo(desde, chave):
    ultimo_id = desde
    inicio = time.monotonic()
    ultimo_envio = inicio
    # comentário imediato: o navegador abre a conexão sem esperar o primeiro evento
    yield ": conectado\n\n"
    while time.monotonic() - inicio < DURACAO_MAX:
        for evento in _consultar(ultimo_id, chave, MAX_NOVIDADES):
            ultimo_id = evento.id
            ultimo_envio = time.monotonic()
            yield f"id: {evento.id}\ndata: {json.dumps(_serializar(evento), ensure_ascii=False)}\n\n"
        agora = time.monotonic()
        if agora - ultimo_envio >= BATIMENTO_SEGUNDOS:
            ultimo_envio = agora
            yield ": batimento\n\n"
        time.sleep(INTERVALO_CONSULTA)


@ns.route("/tempo-real")
class TempoReal(Resource):
    def get(self):
        """Fluxo SSE de eventos públicos e do usuário; encerra aos 5 min."""
        global _conexoes
        with _conexoes_lock:
            if _conexoes >= MAX_CONEXOES:
                return _erro("TEMPO_REAL_LOTADO",
                             "Tempo real lotado; tente de novo em instantes.", 503)
            _conexoes += 1

        def fluxo_limitado():
            try:
                yield from _fluxo(_desde(), _destino())
            finally:
                with _conexoes_lock:
                    global _conexoes
                    _conexoes -= 1

        return Response(stream_with_context(fluxo_limitado()),
                        mimetype="text/event-stream", headers={
                            "Cache-Control": "no-cache",
                            "X-Accel-Buffering": "no",
                        })


@ns.route("/novidades")
class Novidades(Resource):
    def get(self):
        """Eventos visíveis desde um id (máx. 50) e o último id global."""
        ultimo = _ultimo_id()
        desde = _desde()
        if "desde" not in request.args and not request.headers.get("Last-Event-ID"):
            return {"ultimo_id": ultimo, "eventos": []}, 200
        eventos = [_serializar(e) for e in _consultar(desde, _destino(), MAX_NOVIDADES)]
        return {"ultimo_id": ultimo, "eventos": eventos}, 200


def _leitura(chave):
    leitura = db.session.get(NotificacaoLeitura, (chave[0], chave[1]))
    return leitura.ultimo_id if leitura else 0


@ns.route("/notificacoes")
class Notificacoes(Resource):
    def get(self):
        """As 30 notificações mais recentes destinadas ao usuário, com `lida`."""
        chave = _destino()
        if chave is None:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        eventos = (Evento.query
                   .filter(Evento.dest_tipo == chave[0], Evento.dest_id == chave[1])
                   .order_by(Evento.id.desc()).limit(MAX_NOTIFICACOES).all())
        lido_ate = _leitura(chave)
        return {"notificacoes": [{**_serializar(e), "lida": e.id <= lido_ate}
                                 for e in eventos]}, 200


@ns.route("/notificacoes/lidas")
class NotificacoesLidas(Resource):
    entrada = ns.model("NotificacoesLidas", {
        "ate_id": fields.Integer(required=True, description="Último id de evento lido"),
    })

    @ns.expect(entrada)
    def post(self):
        """Marca como lidas as notificações até `ate_id`."""
        chave = _destino()
        if chave is None:
            return _erro("NAO_AUTENTICADO", "Entre para continuar.", 401)
        corpo = request.get_json(silent=True)
        ate_id = corpo.get("ate_id") if isinstance(corpo, dict) else None
        if not isinstance(ate_id, int) or isinstance(ate_id, bool) or ate_id < 0:
            return _erro("DADOS_INVALIDOS", "Corrija os campos indicados.", 400,
                         )
        leitura = db.session.get(NotificacaoLeitura, (chave[0], chave[1]))
        if leitura is None:
            leitura = NotificacaoLeitura(tipo=chave[0], usuario_id=chave[1],
                                         ultimo_id=ate_id)
            db.session.add(leitura)
        elif ate_id > leitura.ultimo_id:
            leitura.ultimo_id = ate_id
        db.session.commit()
        return {"lido_ate": leitura.ultimo_id}, 200
