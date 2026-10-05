"""Consulta legada dos pedidos; a escrita exige o painel autenticado."""
from flask_restx import Namespace, Resource
from models import Doacao as DoacaoModel

ns = Namespace("doacoes", description="Consulta legada de pedidos")

def _resumo(pedido):
    return {"id": pedido.id, "estabelecimento_id": pedido.estabelecimento_id,
            "data_cadastro": pedido.data_cadastro.isoformat() if pedido.data_cadastro else None,
            "data_limite_retirada": pedido.data_limite_retirada.isoformat(),
            "status": pedido.status}

@ns.route("/")
class DoacaoList(Resource):
    def get(self):
        return [_resumo(p) for p in DoacaoModel.query.filter(
            DoacaoModel.estabelecimento_id.isnot(None)).all()], 200

@ns.route("/<int:id>")
class Doacao(Resource):
    def get(self, id):
        pedido = DoacaoModel.query.filter_by(id=id).filter(
            DoacaoModel.estabelecimento_id.isnot(None)).first()
        if not pedido:
            return {"message": "Pedido não encontrado"}, 404
        return _resumo(pedido), 200
