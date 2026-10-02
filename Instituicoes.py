from flask import request
from flask_restx import Namespace, Resource, fields
from models import db, Instituicao as InstituicaoModel

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

@ns.route("/")
class InstituicaoList(Resource):

    @ns.doc("Listar todas as instituições")
    def get(self):
        """Listar todas as instituições cadastradas no PostgreSQL"""
        instituicoes = InstituicaoModel.query.all()
        return [
            {
                "id": i.id,
                "nome": i.nome,
                "cnpj": i.cnpj,
                "email": i.email,
                "telefone": i.telefone,
                "endereco": i.endereco
            } for i in instituicoes
        ], 200

    @ns.expect(instituicao_model)
    @ns.doc("Criar uma nova instituição")
    def post(self):
        """Criar uma nova instituição e persistir no PostgreSQL"""
        data = request.json
        nova_instituicao = InstituicaoModel(
            nome=data["nome"],
            cnpj=data["cnpj"],
            email=data["email"],
            telefone=data.get("telefone", ""),
            endereco=data["endereco"]
        )
        
    
        db.session.add(nova_instituicao)
        db.session.commit()
        
        return {
            "id": nova_instituicao.id,
            "nome": nova_instituicao.nome,
            "cnpj": nova_instituicao.cnpj,
            "email": nova_instituicao.email,
            "telefone": nova_instituicao.telefone,
            "endereco": nova_instituicao.endereco
        }, 201


@ns.route("/<int:id>")
@ns.param("id", "ID da instituição")
class Instituicao(Resource):

    @ns.doc("Obter uma instituição pelo ID")
    def get(self, id):
        """Obter uma instituição pelo ID direto do banco"""
        i = InstituicaoModel.query.get(id)
        if i:
            return {
                "id": i.id,
                "nome": i.nome,
                "cnpj": i.cnpj,
                "email": i.email,
                "telefone": i.telefone,
                "endereco": i.endereco
            }, 200

        return {"message": "Instituição não encontrada"}, 404

    @ns.expect(instituicao_model)
    @ns.doc("Atualizar uma instituição pelo ID")
    def put(self, id):
        """Atualizar uma instituição pelo ID no PostgreSQL"""
        i = InstituicaoModel.query.get(id)
        if i:
            data = request.json
            i.nome = data.get("nome", i.nome)
            i.cnpj = data.get("cnpj", i.cnpj)
            i.email = data.get("email", i.email)
            i.telefone = data.get("telefone", i.telefone)
            i.endereco = data.get("endereco", i.endereco)
            
            db.session.commit()
            return {
                "id": i.id,
                "nome": i.nome,
                "cnpj": i.cnpj,
                "email": i.email,
                "telefone": i.telefone,
                "endereco": i.endereco
            }, 200

        return {"message": "Instituição não encontrada"}, 404

    @ns.doc("Deletar uma instituição pelo ID")
    def delete(self, id):
        """Deletar uma instituição pelo ID no PostgreSQL"""
        i = InstituicaoModel.query.get(id)
        if i:
            db.session.delete(i)
            db.session.commit()
            return {"message": "Instituição deletada com sucesso"}, 200

        return {"message": "Instituição não encontrada"}, 404