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
    id = db.Column(db.Integer, primary_key=True)
    estabelecimento_id = db.Column(db.Integer, db.ForeignKey('estabelecimentos.id'), nullable=False)
    data_cadastro = db.Column(db.DateTime, default=_utc_naive)
    data_limite_retirada = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='DISPONIVEL')
    itens = db.relationship('ItemDoacao', backref='doacao', cascade="all, delete-orphan", lazy=True)
    reservas = db.relationship('Reserva', backref='doacao', lazy=True)

class ItemDoacao(db.Model):
    __tablename__ = 'itens_doacao'
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id'), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    quantidade = db.Column(db.Numeric(10, 2), nullable=False)
    unidade_medida = db.Column(db.String(20), nullable=False)
    validade = db.Column(db.Date, nullable=False)

class Reserva(db.Model):
    __tablename__ = 'reservas'
    id = db.Column(db.Integer, primary_key=True)
    doacao_id = db.Column(db.Integer, db.ForeignKey('doacoes.id'), nullable=False)
    instituicao_id = db.Column(db.Integer, db.ForeignKey('instituicoes.id'), nullable=False)
    data_reserva = db.Column(db.DateTime, default=_utc_naive)
    data_retirada = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='ATIVA')
