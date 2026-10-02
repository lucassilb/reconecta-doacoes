from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Estabelecimento(db.Model):
    __tablename__ = 'estabelecimentos'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnpj = db.Column(db.String(18), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    endereco = db.Column(db.Text, nullable=False)
    doacoes = db.relationship('Doacao', backref='estabelecimento', lazy=True)

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
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
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
    data_reserva = db.Column(db.DateTime, default=datetime.utcnow)
    data_retirada = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='ATIVA')