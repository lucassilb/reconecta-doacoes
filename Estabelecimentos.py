from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import IntegrityError
from crud_validacao import corpo_json, erro_campos, validar_contato
from models import db, Estabelecimento as EstabelecimentoModel # Importa o banco e o model

ns = Namespace(
    "estabelecimentos",
    description="Operações relacionadas aos estabelecimentos doadores"
)

estabelecimento_model = ns.model("Estabelecimento", {
    "id": fields.Integer(readonly=True, description="ID do estabelecimento"),
    "nome": fields.String(required=True, description="Nome do estabelecimento"),
    "cnpj": fields.String(required=True, description="CNPJ do estabelecimento"),
    "email": fields.String(required=True, description="Email do estabelecimento"),
    "telefone": fields.String(required=False, description="Telefone do estabelecimento"),
    "endereco": fields.String(required=True, description="Endereço do estabelecimento"),
})

@ns.route("/")
class EstabelecimentoList(Resource):

    @ns.doc("Listar todos os estabelecimentos")
    def get(self):
        """Listar todos os estabelecimentos cadastrados no banco"""
        estabelecimentos = EstabelecimentoModel.query.all()
        return [
            {
                "id": e.id,
                "nome": e.nome,
                "cnpj": e.cnpj,
                "email": e.email,
                "telefone": e.telefone,
                "endereco": e.endereco
            } for e in estabelecimentos
        ], 200

    @ns.expect(estabelecimento_model)
    @ns.doc("Criar um novo estabelecimento")
    def post(self):
        """Criar um novo estabelecimento e persistir no PostgreSQL"""
        data = corpo_json()
        campos = validar_contato(data, criar=True)
        if campos:
            return erro_campos(campos)
        novo_estabelecimento = EstabelecimentoModel(
            nome=data["nome"],
            cnpj=data["cnpj"],
            email=data["email"],
            telefone=data.get("telefone", ""),
            endereco=data["endereco"]
        )
        
    
        db.session.add(novo_estabelecimento)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return erro_campos({"cnpj": "CNPJ ou email já cadastrado.",
                                "email": "CNPJ ou email já cadastrado."})
        
        return {
            "id": novo_estabelecimento.id,
            "nome": novo_estabelecimento.nome,
            "cnpj": novo_estabelecimento.cnpj,
            "email": novo_estabelecimento.email,
            "telefone": novo_estabelecimento.telefone,
            "endereco": novo_estabelecimento.endereco
        }, 201


@ns.route("/<int:id>")
@ns.param("id", "ID do estabelecimento")
class Estabelecimento(Resource):

    @ns.doc("Obter um estabelecimento pelo ID")
    def get(self, id):
        """Obter um estabelecimento pelo ID direto do banco"""
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            return {
                "id": e.id,
                "nome": e.nome,
                "cnpj": e.cnpj,
                "email": e.email,
                "telefone": e.telefone,
                "endereco": e.endereco
            }, 200

        return {"message": "Estabelecimento não encontrado"}, 404

    @ns.expect(estabelecimento_model)
    @ns.doc("Atualizar um estabelecimento pelo ID")
    def put(self, id):
        """Atualizar um estabelecimento pelo ID no PostgreSQL"""
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            data = corpo_json()
            campos = validar_contato(data, criar=False)
            if campos:
                return erro_campos(campos)
            e.nome = data.get("nome", e.nome)
            e.cnpj = data.get("cnpj", e.cnpj)
            e.email = data.get("email", e.email)
            e.telefone = data.get("telefone", e.telefone)
            e.endereco = data.get("endereco", e.endereco)
            
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro_campos({"cnpj": "CNPJ ou email já cadastrado.",
                                    "email": "CNPJ ou email já cadastrado."})
            return {
                "id": e.id,
                "nome": e.nome,
                "cnpj": e.cnpj,
                "email": e.email,
                "telefone": e.telefone,
                "endereco": e.endereco
            }, 200

        return {"message": "Estabelecimento não encontrado"}, 404

    @ns.doc("Deletar um estabelecimento pelo ID")
    def delete(self, id):
        """Deletar um estabelecimento pelo ID no PostgreSQL"""
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            db.session.delete(e)
            db.session.commit()
            return {"message": "Estabelecimento deletado com sucesso"}, 200

        return {"message": "Estabelecimento não encontrado"}, 404
