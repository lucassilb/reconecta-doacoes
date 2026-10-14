from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_, false, true
from sqlalchemy.orm import foreign

db = SQLAlchemy()


def _utc_naive():
    """Datetime UTC sem fuso para colunas TIMESTAMP sem timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Estabelecimento(db.Model):
    __tablename__ = 'estabelecimentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(18), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    endereco = db.Column(db.Text, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=True)
    natureza_juridica_codigo = db.Column(db.String(4), nullable=True)
    sem_fins_lucrativos = db.Column(db.Boolean, nullable=False, default=False, server_default=false())
    atividade_alimentar = db.Column(db.Boolean, nullable=False, default=True, server_default=true())
    consentimento_versao = db.Column(db.String(20), nullable=True)
    consentimento_em = db.Column(db.DateTime, nullable=True)
    doacoes = db.relationship('Doacao', backref='estabelecimento', lazy=True)

class Doador(db.Model):
    __tablename__ = 'doadores'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    criado_em = db.Column(db.DateTime, default=_utc_naive, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=True)
    consentimento_versao = db.Column(db.String(20), nullable=True)
    consentimento_em = db.Column(db.DateTime, nullable=True)
    doacoes = db.relationship('Doacao', backref='doador', lazy=True)

class Instituicao(db.Model):
    __tablename__ = 'instituicoes'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(18), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    endereco = db.Column(db.Text, nullable=False)
    reservas = db.relationship('Reserva', backref='instituicao', lazy=True)

class Doacao(db.Model):
    __tablename__ = 'doacoes'
    __table_args__ = (
        db.CheckConstraint('(estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)',
                           name='ck_doacoes_uma_origem'),
        db.CheckConstraint("status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA')",
                           name='ck_doacoes_status'),
        db.Index('ix_doacoes_estabelecimento_id', 'estabelecimento_id'),
        db.Index('ix_doacoes_doador_id', 'doador_id'),
        db.Index('ix_doacoes_status_prazo', 'status', 'data_limite_retirada'))
    id = db.Column(db.Integer, primary_key=True)
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id', ondelete='RESTRICT'), nullable=True)
    doador_id = db.Column(db.Integer, db.ForeignKey('doadores.id', ondelete='RESTRICT'), nullable=True)
    retirada_endereco = db.Column(db.String(200), nullable=True)
    retirada_municipio = db.Column(db.String(80), nullable=True)
    retirada_uf = db.Column(db.String(2), nullable=True)
    data_cadastro = db.Column(db.DateTime, default=_utc_naive)
    data_limite_retirada = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='DISPONIVEL')
    itens = db.relationship('ItemDoacao', backref='doacao', cascade="all, delete-orphan", lazy=True)
    reservas = db.relationship('Reserva', backref='doacao', lazy=True)
    contribuicoes = db.relationship('Contribuicao', backref='doacao', lazy=True)

class ItemDoacao(db.Model):
    __tablename__ = 'itens_doacao'
    __table_args__ = (
        db.CheckConstraint('quantidade > 0', name='ck_itens_doacao_quantidade'),
        db.UniqueConstraint('id', 'doacao_id', name='uq_itens_doacao_id_doacao_id'),
        db.Index('ix_itens_doacao_doacao_id', 'doacao_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id', ondelete='CASCADE'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=True)
    contribuicoes = db.relationship(
        'Contribuicao',
        primaryjoin=lambda: and_(
            ItemDoacao.id == foreign(Contribuicao.item_doacao_id),
            ItemDoacao.doacao_id == Contribuicao.doacao_id),
        backref='item_doacao', lazy=True)

class Reserva(db.Model):
    __tablename__ = 'reservas'
    __table_args__ = (
        db.CheckConstraint("status IN ('ATIVA', 'CANCELADA', 'CONCLUIDA')",
                           name='ck_reservas_status'),
    )
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id', ondelete='RESTRICT'), nullable=False)
    instituicao_id = db.Column(db.Integer, db.ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False)
    data_reserva = db.Column(db.DateTime, default=_utc_naive)
    data_retirada = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='ATIVA')


class Contribuicao(db.Model):
    __tablename__ = 'contribuicoes'
    __table_args__ = (
        db.ForeignKeyConstraint(
            ['item_doacao_id', 'doacao_id'], ['itens_doacao.id', 'itens_doacao.doacao_id'],
            name='fk_contribuicoes_item_pedido', ondelete='RESTRICT'),
        db.CheckConstraint('(doador_id IS NOT NULL) <> (estabelecimento_id IS NOT NULL)',
                           name='ck_contribuicoes_uma_origem'),
        db.CheckConstraint('quantidade > 0', name='ck_contribuicoes_quantidade'),
        db.CheckConstraint("status IN ('ACEITA', 'ENTREGUE', 'CANCELADA')",
                           name='ck_contribuicoes_status'),
        db.Index('ix_contribuicoes_doacao_status', 'doacao_id', 'status'),
        db.Index('ix_contribuicoes_item_doacao_id', 'item_doacao_id'),
        db.Index('ix_contribuicoes_doador_id', 'doador_id'),
        db.Index('ix_contribuicoes_estabelecimento_id', 'estabelecimento_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id', ondelete='RESTRICT'), nullable=False)
    item_doacao_id = db.Column(db.Integer, nullable=False)
    doador_id = db.Column(db.Integer, db.ForeignKey('doadores.id', ondelete='RESTRICT'))
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id', ondelete='RESTRICT'))
    alimento = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=False)
    respostas = db.Column(db.Text, nullable=False)
    foto_arquivo = db.Column(db.String(80), nullable=False)
    foto_dados = db.Column(db.LargeBinary, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='ACEITA', server_default='ACEITA')
    criado_em = db.Column(db.DateTime, nullable=False, default=_utc_naive)
    doador = db.relationship('Doador', backref='contribuicoes')
    estabelecimento = db.relationship('Estabelecimento', backref='contribuicoes')


class Excedente(db.Model):
    __tablename__ = 'excedentes'
    __table_args__ = (
        db.CheckConstraint("status IN ('DISPONIVEL', 'RESERVADO', 'RETIRADO', 'CANCELADO', 'EXPIRADO')",
                           name='ck_excedentes_status'),
        db.CheckConstraint('length(observacao) <= 200', name='ck_excedentes_observacao'),
        db.CheckConstraint("(status IN ('RESERVADO', 'RETIRADO') AND reservado_por_id IS NOT NULL) OR "
                           "(status IN ('DISPONIVEL', 'CANCELADO', 'EXPIRADO') AND reservado_por_id IS NULL)",
                           name='ck_excedentes_reservante'),
        db.Index('ix_excedentes_status_prazo', 'status', 'retirar_ate'),
        db.Index('ix_excedentes_estabelecimento', 'estabelecimento_id'),
        db.Index('ix_excedentes_reservado_por', 'reservado_por_id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id', ondelete='RESTRICT'), nullable=False)
    retirar_ate = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='DISPONIVEL', server_default='DISPONIVEL')
    reservado_por_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id', ondelete='RESTRICT'))
    reservado_em = db.Column(db.DateTime)
    retirado_em = db.Column(db.DateTime)
    observacao = db.Column(db.String(200))
    criado_em = db.Column(db.DateTime, nullable=False, default=_utc_naive)
    publicador = db.relationship('Estabelecimento', foreign_keys=[estabelecimento_id])
    reservado_por = db.relationship('Estabelecimento', foreign_keys=[reservado_por_id])
    itens = db.relationship('ItemExcedente', backref='excedente', cascade='all, delete-orphan', lazy=True)


class ItemExcedente(db.Model):
    __tablename__ = 'itens_excedente'
    __table_args__ = (
        db.CheckConstraint('quantidade > 0', name='ck_itens_excedente_quantidade'),
        db.Index('ix_itens_excedente_excedente', 'excedente_id'),
        db.Index('ix_itens_excedente_categoria', 'categoria'),
    )
    id = db.Column(db.Integer, primary_key=True)
    excedente_id = db.Column(db.Integer, db.ForeignKey('excedentes.id', ondelete='CASCADE'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=False)
