from flask_restx import Namespace, Resource, fields
from sqlalchemy.exc import IntegrityError
from crud_admin import exigir_admin
from crud_validacao import corpo_json, erro, erro_campos, validar_doacao
from fuso import iso_evento, iso_prazo
from models import Contribuicao, ItemDoacao, Reserva, db, Doacao as DoacaoModel

ns = Namespace(
    "doacoes",
    description="Operações relacionadas às doações de alimentos"
)

doacao_model = ns.model("Doacao", {
    "id": fields.Integer(readonly=True, description="ID da doação"),
    "estabelecimento_id": fields.Integer(required=True, description="ID do estabelecimento doador"),
    "data_limite_retirada": fields.String(required=True, description="Entrada: hora local de Brasília sem offset (ex.: 2026-09-10T18:00:00); resposta: ISO com offset"),
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
                "data_cadastro": iso_evento(d.data_cadastro),
                "data_limite_retirada": iso_prazo(d.data_limite_retirada),
                "status": d.status
            } for d in doacoes
        ], 200

    @ns.expect(doacao_model)
    @ns.doc("Criar uma nova doação", security="AdminToken")
    def post(self):
        """Criar uma nova doação e salvar no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
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
            "data_cadastro": iso_evento(nova_doacao.data_cadastro),
            "data_limite_retirada": iso_prazo(nova_doacao.data_limite_retirada),
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
                "data_cadastro": iso_evento(d.data_cadastro),
                "data_limite_retirada": iso_prazo(d.data_limite_retirada),
                "status": d.status
            }, 200

        return {"message": "Doação não encontrada"}, 404

    @ns.expect(doacao_model)
    @ns.doc("Atualizar uma doação pelo ID", security="AdminToken")
    def put(self, id):
        """Atualizar uma doação pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
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
                "data_cadastro": iso_evento(d.data_cadastro),
                "data_limite_retirada": iso_prazo(d.data_limite_retirada),
                "status": d.status
            }, 200

        return {"message": "Doação não encontrada"}, 404

    @ns.doc("Deletar uma doação pelo ID", security="AdminToken")
    def delete(self, id):
        """Deletar uma doação pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        d = db.session.get(DoacaoModel, id)
        if d:
            if (ItemDoacao.query.filter_by(doacao_id=id).first() or
                    Contribuicao.query.filter_by(doacao_id=id).first() or
                    Reserva.query.filter_by(doacao_id=id).first()):
                return erro("REGISTROS_DEPENDENTES",
                            "Doação possui itens, contribuições ou reservas vinculados.", 409)
            db.session.delete(d)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro("REGISTROS_DEPENDENTES",
                            "Doação possui registros vinculados.", 409)
            return {"message": "Doação deletada com sucesso"}, 200

        return {"message": "Doação não encontrada"}, 404
