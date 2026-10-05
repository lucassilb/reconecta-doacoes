from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

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
    __table_args__ = (db.CheckConstraint(
        '(estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)',
        name='ck_doacoes_uma_origem'),
        db.Index('ix_doacoes_estabelecimento_id', 'estabelecimento_id'),
        db.Index('ix_doacoes_doador_id', 'doador_id'),
        db.Index('ix_doacoes_status_prazo', 'status', 'data_limite_retirada'))
    id = db.Column(db.Integer, primary_key=True)
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id'), nullable=True)
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
    __table_args__ = (db.Index('ix_itens_doacao_doacao_id', 'doacao_id'),)
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=True)
    contribuicoes = db.relationship('Contribuicao', backref='item_doacao', lazy=True)

class Reserva(db.Model):
    __tablename__ = 'reservas'
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id'), nullable=False)
    instituicao_id = db.Column(db.Integer, db.ForeignKey('instituicoes.id'), nullable=False)
    data_reserva = db.Column(db.DateTime, default=_utc_naive)
    data_retirada = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='ATIVA')


class Contribuicao(db.Model):
    __tablename__ = 'contribuicoes'
    __table_args__ = (
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
    item_doacao_id = db.Column(db.Integer, db.ForeignKey('itens_doacao.id', ondelete='RESTRICT'), nullable=False)
    doador_id = db.Column(db.Integer, db.ForeignKey('doadores.id', ondelete='RESTRICT'))
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id', ondelete='RESTRICT'))
    alimento = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=False)
    respostas = db.Column(db.Text, nullable=False)
    foto_arquivo = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='ACEITA', server_default='ACEITA')
    criado_em = db.Column(db.DateTime, nullable=False, default=_utc_naive)
    doador = db.relationship('Doador', backref='contribuicoes')
    estabelecimento = db.relationship('Estabelecimento', backref='contribuicoes')
