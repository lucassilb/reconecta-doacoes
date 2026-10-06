import re

from flask_restx import Namespace, Resource, fields
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from cnpj_service import formatar_cnpj
from crud_admin import exigir_admin, token_admin_valido
from crud_validacao import corpo_json, erro, erro_campos, validar_contato, verificar_cnpj
from models import Contribuicao, Doacao, Doador, db, Estabelecimento as EstabelecimentoModel

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


def _resposta(e):
    dados = {"id": e.id, "nome": e.nome, "cnpj": e.cnpj,
             "email": e.email, "telefone": e.telefone, "endereco": e.endereco}
    if not token_admin_valido():
        dados["cnpj"] = re.sub(r"\D", "", e.cnpj)
        dados.pop("email")
        dados.pop("telefone")
    return dados


def _duplicado(cnpj, email, *, ignorar_id=None):
    empresa = EstabelecimentoModel.query.filter(
        EstabelecimentoModel.cnpj.in_((cnpj, formatar_cnpj(cnpj))))
    if ignorar_id is not None:
        empresa = empresa.filter(EstabelecimentoModel.id != ignorar_id)
    if empresa.first():
        return erro("CNPJ_JA_CADASTRADO", "Este CNPJ já está cadastrado.", 409)
    empresa = EstabelecimentoModel.query.filter(func.lower(EstabelecimentoModel.email) == email)
    if ignorar_id is not None:
        empresa = empresa.filter(EstabelecimentoModel.id != ignorar_id)
    if empresa.first() or Doador.query.filter(func.lower(Doador.email) == email).first():
        return erro("EMAIL_JA_CADASTRADO", "Este e-mail já está cadastrado.", 409)
    return None


def _contato(data, atual=None):
    campos = validar_contato(data, criar=atual is None)
    if campos:
        return None, erro_campos(campos)
    cnpj, falha = verificar_cnpj(data.get("cnpj", atual.cnpj if atual else None),
                                 alimentar=True)
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
class EstabelecimentoList(Resource):

    @ns.doc("Listar todos os estabelecimentos",
            description="Sem token: id, nome, CNPJ (dígitos) e endereço. Com X-Admin-Token válido: registro completo.")
    def get(self):
        """Listar todos os estabelecimentos cadastrados no banco"""
        estabelecimentos = EstabelecimentoModel.query.all()
        return [_resposta(e) for e in estabelecimentos], 200

    @ns.expect(estabelecimento_model)
    @ns.doc("Criar um novo estabelecimento", security="AdminToken")
    def post(self):
        """Criar um novo estabelecimento e persistir no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        data = corpo_json()
        contato, falha = _contato(data)
        if falha:
            return falha
        novo_estabelecimento = EstabelecimentoModel(
            nome=data["nome"],
            **contato,
            endereco=data["endereco"]
        )
        
    
        db.session.add(novo_estabelecimento)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return erro("CADASTRO_DUPLICADO", "CNPJ ou e-mail já cadastrado.", 409)

        return _resposta(novo_estabelecimento), 201


@ns.route("/<int:id>")
@ns.param("id", "ID do estabelecimento")
class Estabelecimento(Resource):

    @ns.doc("Obter um estabelecimento pelo ID",
            description="Sem token: id, nome, CNPJ (dígitos) e endereço. Com X-Admin-Token válido: registro completo.")
    def get(self, id):
        """Obter um estabelecimento pelo ID direto do banco"""
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            return _resposta(e), 200

        return {"message": "Estabelecimento não encontrado"}, 404

    @ns.expect(estabelecimento_model)
    @ns.doc("Atualizar um estabelecimento pelo ID", security="AdminToken")
    def put(self, id):
        """Atualizar um estabelecimento pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            data = corpo_json()
            contato, falha = _contato(data, e)
            if falha:
                return falha
            e.nome = data.get("nome", e.nome)
            e.cnpj = contato["cnpj"]
            e.email = contato["email"]
            e.telefone = contato["telefone"]
            e.endereco = data.get("endereco", e.endereco)
            
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro("CADASTRO_DUPLICADO", "CNPJ ou e-mail já cadastrado.", 409)
            return _resposta(e), 200

        return {"message": "Estabelecimento não encontrado"}, 404

    @ns.doc("Deletar um estabelecimento pelo ID", security="AdminToken")
    def delete(self, id):
        """Deletar um estabelecimento pelo ID no PostgreSQL"""
        bloqueio = exigir_admin()
        if bloqueio:
            return bloqueio
        e = db.session.get(EstabelecimentoModel, id)
        if e:
            if (Doacao.query.filter_by(estabelecimento_id=id).first() or
                    Contribuicao.query.filter_by(estabelecimento_id=id).first()):
                return erro("REGISTROS_DEPENDENTES",
                            "Estabelecimento possui pedidos ou contribuições vinculados.", 409)
            db.session.delete(e)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return erro("REGISTROS_DEPENDENTES",
                            "Estabelecimento possui registros vinculados.", 409)
            return {"message": "Estabelecimento deletado com sucesso"}, 200

        return {"message": "Estabelecimento não encontrado"}, 404
