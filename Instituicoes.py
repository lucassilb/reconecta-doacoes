import re

from flask_restx import Namespace, Resource, fields
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from cnpj_service import formatar_cnpj
from crud_admin import exigir_admin, token_admin_valido
from crud_validacao import corpo_json, erro, erro_campos, validar_contato, verificar_cnpj
from models import Reserva, db, Instituicao as InstituicaoModel

ns = Namespace(
    "instituicoes",
    description="Operações relacionadas às instituições receptoras"
)

instituicao_model = ns.model("Instituicao", {
    "id": fields.Integer(readonly=True, description="ID da instituição"),
    "nome": fields.String(required=True, description="Nome da instituição"),
    "cnpj": fields.String(required=True, description="CNPJ da instituição"),
    "email": fields.String(required=True, description="Email da instituição"),
    "telefone": fields.String(required=False, description="Telefone da instituição"),
    "endereco": fields.String(required=True, description="Endereço da instituição"),
})


def _resposta(i):
    dados = {"id": i.id, "nome": i.nome, "cnpj": i.cnpj,
             "email": i.email, "telefone": i.telefone, "endereco": i.endereco}
    if not token_admin_valido():
        dados["cnpj"] = re.sub(r"\D", "", i.cnpj)
        dados.pop("email")
        dados.pop("telefone")
    return dados


def _duplicado(cnpj, email, *, ignorar_id=None):
    instituicao = InstituicaoModel.query.filter(
        InstituicaoModel.cnpj.in_((cnpj, formatar_cnpj(cnpj))))
    if ignorar_id is not None:
        instituicao = instituicao.filter(InstituicaoModel.id != ignorar_id)
    if instituicao.first():
        return erro("CNPJ_JA_CADASTRADO", "Este CNPJ já está cadastrado.", 409)
    instituicao = InstituicaoModel.query.filter(func.lower(InstituicaoModel.email) == email)
    if ignorar_id is not None:
        instituicao = instituicao.filter(InstituicaoModel.id != ignorar_id)
    if instituicao.first():
        return erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
    return None


def _contato(data, atual=None):
    campos = validar_contato(data, criar=atual is None)
    if campos:
        return None, erro_campos(campos)
    cnpj, falha = verificar_cnpj(data.get("cnpj", atual.cnpj if atual else None),
                                 alimentar=False)
    if falha:
        return None, falha
    email = data.get("email", atual.email if atual else "").strip().lower()
    falha = _duplicado(cnpj, email, ignorar_id=atual.id if atual else None)
    if falha:
        return None, falha
    telefone = data.get("telefone", atual.telefone if atual else "")
    if telefone:
        telefone = re.sub(r"\D", "", telefone)
    return {"cnpj": cnpj, "email": email, "telefone": telefone}, None

@ns.route("/")
class InstituicaoList(Resource):

    @ns.doc("Listar todas as instituições",
            description="Sem token: id, nome, CNPJ (dígitos) e endereço. Com X-Admin-Token válido: registro completo.")
    def get(self):
        """Listar todas as instituições cadastradas no PostgreSQL"""
        instituicoes = InstituicaoModel.query.all()
        return [_resposta(i) for i in instituicoes], 200

    @ns.expect(instituicao_model)
    @ns.doc("Criar uma nova instituição", security="AdminToken")
    def post(self):
        """Criar uma nova instituição e persistir no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        data = corpo_json()
        contato, falha = _contato(data)
        if falha:
            return falha
        nova_instituicao = InstituicaoModel(
            nome=data["nome"],
            **contato,
            endereco=data["endereco"]
        )
        
    
        db.session.add(nova_instituicao)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return erro("CADASTRO_DUPLICADO", "CNPJ ou e-mail já cadastrado.", 409)

        return _resposta(nova_instituicao), 201


@ns.route("/<int:id>")
@ns.param("id", "ID da instituição")
class Instituicao(Resource):

    @ns.doc("Obter uma instituição pelo ID",
            description="Sem token: id, nome, CNPJ (dígitos) e endereço. Com X-Admin-Token válido: registro completo.")
    def get(self, id):
        """Obter uma instituição pelo ID direto do banco"""
        i = db.session.get(InstituicaoModel, id)
        if i:
            return _resposta(i), 200

        return {"message": "Instituição não encontrada"}, 404

    @ns.expect(instituicao_model)
    @ns.doc("Atualizar uma instituição pelo ID", security="AdminToken")
    def put(self, id):
        """Atualizar uma instituição pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        i = db.session.get(InstituicaoModel, id)
        if i:
            data = corpo_json()
            contato, falha = _contato(data, i)
            if falha:
                return falha
            i.nome = data.get("nome", i.nome)
            i.cnpj = contato["cnpj"]
            i.email = contato["email"]
            i.telefone = contato["telefone"]
            i.endereco = data.get("endereco", i.endereco)
            
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro("CADASTRO_DUPLICADO", "CNPJ ou e-mail já cadastrado.", 409)
            return _resposta(i), 200

        return {"message": "Instituição não encontrada"}, 404

    @ns.doc("Deletar uma instituição pelo ID", security="AdminToken")
    def delete(self, id):
        """Deletar uma instituição pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        i = db.session.get(InstituicaoModel, id)
        if i:
            if Reserva.query.filter_by(instituicao_id=id).first():
                return erro("REGISTROS_DEPENDENTES",
                            "Instituição possui reservas vinculadas.", 409)
            db.session.delete(i)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro("REGISTROS_DEPENDENTES",
                            "Instituição possui registros vinculados.", 409)
            return {"message": "Instituição deletada com sucesso"}, 200

        return {"message": "Instituição não encontrada"}, 404
