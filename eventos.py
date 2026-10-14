"""Fonte única de eventos: alimenta o tempo real (SSE), as notificações e o histórico.

`emitir` grava na mesma transação de quem chama (não faz commit): se a operação
falhar depois, o evento some junto e nada fica anunciado pela metade.

Um evento público gera uma linha com `dest_tipo`/`dest_id` NULL; cada destinatário
ganha uma linha privada (visível só para ele no tempo real e nas notificações).
`dados` é JSON em texto e nunca deve carregar dado pessoal (nome, e-mail,
documento, endereço): só ids e rótulos públicos.
"""

import json

from models import db, _utc_naive

DEST_TIPOS = ("empresa", "doador")


class Evento(db.Model):
    __tablename__ = 'eventos'
    __table_args__ = (
        db.CheckConstraint("dest_tipo IN ('empresa','doador') OR dest_tipo IS NULL",
                           name='ck_eventos_dest_tipo'),
        db.CheckConstraint("(dest_tipo IS NULL) = (dest_id IS NULL)",
                           name='ck_eventos_dest_par'),
        db.Index('ix_eventos_publico_id', 'publico', 'id'),
        db.Index('ix_eventos_destino', 'dest_tipo', 'dest_id', 'id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(40), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=_utc_naive)
    publico = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    dest_tipo = db.Column(db.String(10), nullable=True)
    dest_id = db.Column(db.Integer, nullable=True)
    dados = db.Column(db.Text, nullable=False, default='{}')


def emitir(tipo, dados=None, *, publico=True, destinatarios=()):
    """Registra o evento na sessão atual; devolve as linhas criadas (sem commit)."""
    criados = []
    texto = json.dumps(dados or {}, ensure_ascii=False, separators=(",", ":"))
    if publico:
        criados.append(Evento(tipo=tipo, publico=True, dados=texto))
    for dest_tipo, dest_id in destinatarios:
        if dest_tipo not in DEST_TIPOS:
            raise ValueError(f"dest_tipo inválido: {dest_tipo!r}")
        criados.append(Evento(tipo=tipo, publico=False,
                              dest_tipo=dest_tipo, dest_id=int(dest_id), dados=texto))
    db.session.add_all(criados)
    return criados
