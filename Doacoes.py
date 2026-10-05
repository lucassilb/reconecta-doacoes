from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import IntegrityError
from crud_validacao import corpo_json, erro_campos, validar_doacao
from models import db, Doacao as DoacaoModel

ns = Namespace(
    "doacoes",
    description="Operações relacionadas às doações de alimentos"
)

doacao_model = ns.model("Doacao", {
    "id": fields.Integer(readonly=True, description="ID da doação"),
    "estabelecimento_id": fields.Integer(required=True, description="ID do estabelecimento doador"),
    "data_limite_retirada": fields.String(required=True, description="Data limite para retirada (Ex: 2026-09-10T18:00:00)"),
    "status": fields.String(required=False, default="DISPONIVEL", description="Status (DISPONIVEL, RESERVADA, RETIRADA)")
})

@ns.route("/")
class DoacaoList(Resource):

    @ns.doc("Listar todas as doações")
    def get(self):
        """Listar todas as doações cadastradas no PostgreSQL"""
        doacoes = DoacaoModel.query.all()
        return [
            {
                "id": d.id,
                "estabelecimento_id": d.estabelecimento_id,
                "data_cadastro": d.data_cadastro.isoformat() if d.data_cadastro else None,
                "data_limite_retirada": d.data_limite_retirada.isoformat() if d.data_limite_retirada else None,
                "status": d.status
            } for d in doacoes
        ], 200

    @ns.expect(doacao_model)
    @ns.doc("Criar uma nova doação")
    def post(self):
        """Criar uma nova doação e salvar no PostgreSQL"""
        data = corpo_json()
        campos, data_limite = validar_doacao(data, criar=True)
        if campos:
            return erro_campos(campos)


        nova_doacao = DoacaoModel(
            estabelecimento_id=data["estabelecimento_id"],
            data_limite_retirada=data_limite,
            status=data.get("status", "DISPONIVEL")
        )

        db.session.add(nova_doacao)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return erro_campos({"estabelecimento_id": "Referência inválida."})

        return {
            "id": nova_doacao.id,
            "estabelecimento_id": nova_doacao.estabelecimento_id,
            "data_cadastro": nova_doacao.data_cadastro.isoformat() if nova_doacao.data_cadastro else None,
            "data_limite_retirada": nova_doacao.data_limite_retirada.isoformat(),
            "status": nova_doacao.status
        }, 201


@ns.route("/<int:id>")
@ns.param("id", "ID da doação")
class Doacao(Resource):

    @ns.doc("Obter uma doação pelo ID")
    def get(self, id):
        """Obter uma doação pelo ID direto do banco"""
        d = db.session.get(DoacaoModel, id)
        if d:
            return {
                "id": d.id,
                "estabelecimento_id": d.estabelecimento_id,
                "data_cadastro": d.data_cadastro.isoformat() if d.data_cadastro else None,
                "data_limite_retirada": d.data_limite_retirada.isoformat() if d.data_limite_retirada else None,
                "status": d.status
            }, 200

        return {"message": "Doação não encontrada"}, 404

    @ns.expect(doacao_model)
    @ns.doc("Atualizar uma doação pelo ID")
    def put(self, id):
        """Atualizar uma doação pelo ID no PostgreSQL"""
        d = db.session.get(DoacaoModel, id)
        if d:
            data = corpo_json()
            campos, data_limite = validar_doacao(data, criar=False)
            if campos:
                return erro_campos(campos)
            if "estabelecimento_id" in data:
                d.estabelecimento_id = data["estabelecimento_id"]
            if "data_limite_retirada" in data:
                d.data_limite_retirada = data_limite
            if "status" in data:
                d.status = data["status"]

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro_campos({"estabelecimento_id": "Referência inválida."})
            return {
                "id": d.id,
                "estabelecimento_id": d.estabelecimento_id,
                "data_cadastro": d.data_cadastro.isoformat() if d.data_cadastro else None,
                "data_limite_retirada": d.data_limite_retirada.isoformat(),
                "status": d.status
            }, 200

        return {"message": "Doação não encontrada"}, 404

    @ns.doc("Deletar uma doação pelo ID")
    def delete(self, id):
        """Deletar uma doação pelo ID no PostgreSQL"""
        d = db.session.get(DoacaoModel, id)
        if d:
            db.session.delete(d)
            db.session.commit()
            return {"message": "Doação deletada com sucesso"}, 200

        return {"message": "Doação não encontrada"}, 404
