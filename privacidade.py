"""Consentimento, exportação e anonimização de dados pessoais (LGPD).

A versão da política é gravada em cada cadastro: contas antigas ficam com
consentimento nulo até que a pessoa aceite a política vigente.
"""

from datetime import datetime, timezone

from fuso import iso_evento
from models import Contribuicao, Doacao, Excedente, db

POLITICA_VERSAO = "2026-10-14-r17"


def consentimento_registrado(usuario):
    return {"versao": usuario.consentimento_versao,
            "em": iso_evento(usuario.consentimento_em)}


def registrar_consentimento(usuario):
    usuario.consentimento_versao = POLITICA_VERSAO
    usuario.consentimento_em = datetime.now(timezone.utc).replace(tzinfo=None)


def _contribuicao(dados):
    return {"id": dados.id, "pedido_id": dados.doacao_id, "alimento": dados.alimento,
            "categoria": dados.categoria, "quantidade": float(dados.quantidade),
            "unidade_medida": dados.unidade_medida, "validade": dados.validade.isoformat(),
            "status": dados.status, "criado_em": iso_evento(dados.criado_em),
            "respostas": dados.respostas}


def _pedido(pedido):
    return {"id": pedido.id, "status": pedido.status,
            "data_cadastro": iso_evento(pedido.data_cadastro),
            "data_limite_retirada": iso_evento(pedido.data_limite_retirada),
            "itens": [{"nome": item.nome, "categoria": item.categoria,
                       "quantidade": float(item.quantidade),
                       "unidade_medida": item.unidade_medida,
                       "validade": item.validade.isoformat() if item.validade else None}
                      for item in pedido.itens]}


def _excedente(excedente):
    return {"id": excedente.id, "status": excedente.status,
            "criado_em": iso_evento(excedente.criado_em),
            "retirar_ate": iso_evento(excedente.retirar_ate),
            "reservado_em": iso_evento(excedente.reservado_em),
            "retirado_em": iso_evento(excedente.retirado_em),
            "observacao": excedente.observacao,
            "itens": [{"nome": item.nome, "categoria": item.categoria,
                       "quantidade": float(item.quantidade),
                       "unidade_medida": item.unidade_medida,
                       "validade": item.validade.isoformat()}
                      for item in excedente.itens]}


def _excedente_publicado(excedente):
    # a foto da validade é do titular: a exportação aponta o tipo e onde baixá-la
    dados = _excedente(excedente)
    dados["foto_validade"] = ({"tipo": excedente.foto_tipo,
                               "url": f"/reconecta/excedentes/{excedente.id}/foto"}
                              if excedente.foto_tipo else None)
    return dados


def exportar_dados(tipo, usuario):
    """Cópia dos dados pessoais e registros da conta, sem dados de terceiros."""
    dados = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "politica_versao": POLITICA_VERSAO,
             "titular": {"tipo": tipo, "id": usuario.id, "nome": usuario.nome,
                         "email": usuario.email, "telefone": usuario.telefone,
                         "consentimento": consentimento_registrado(usuario)}}
    if tipo == "doador":
        dados["titular"]["cpf"] = usuario.cpf
        dados["doacoes_feitas"] = [_contribuicao(c) for c in usuario.contribuicoes]
        dados["pedidos_publicados"] = [_pedido(d) for d in usuario.doacoes]
        dados["excedentes_publicados"] = [
            {**_excedente_publicado(e), "retirada_endereco": e.retirada_endereco} for e in
            Excedente.query.filter_by(doador_id=usuario.id).all()]
    else:
        dados["titular"].update(cnpj=usuario.cnpj, endereco=usuario.endereco)
        dados["pedidos_publicados"] = [_pedido(d) for d in usuario.doacoes]
        dados["doacoes_feitas"] = [_contribuicao(c) for c in usuario.contribuicoes]
        dados["excedentes_publicados"] = [
            _excedente_publicado(e) for e in
            Excedente.query.filter_by(estabelecimento_id=usuario.id).all()]
        dados["excedentes_reservados"] = [
            _excedente(e) for e in
            Excedente.query.filter_by(reservado_por_id=usuario.id).all()]
    return dados


def conta_removida(usuario):
    """Reconhece o marcador de anonimização sem depender de outros campos."""
    return usuario.email.endswith("@removido.invalid")


def anonimizar_conta(tipo, usuario):
    """Remove identificação mantendo os registros para a estatística agregada.

    Pedidos, doações e excedentes ficam com a referência ao titular anonimizado;
    endereços de retirada e fotos são apagados por precaução.
    """
    marcador = f"removido-{tipo}-{usuario.id}"
    usuario.nome = "Conta removida"
    usuario.email = f"{marcador}@removido.invalid"
    usuario.telefone = "0"
    usuario.senha_hash = None
    if tipo == "doador":
        usuario.cpf = f"REM{usuario.id:08d}"
        (Doacao.query.filter_by(doador_id=usuario.id)
         .update({"retirada_endereco": None, "retirada_municipio": None,
                  "retirada_uf": None}, synchronize_session=False))
        (Contribuicao.query.filter_by(doador_id=usuario.id)
         .update({"foto_dados": None, "foto_arquivo": "removida"},
                 synchronize_session=False))
        # a oferta da pessoa física guarda o endereço dela: some, e a oferta ainda aberta sai do ar
        (Excedente.query.filter_by(doador_id=usuario.id, status="DISPONIVEL")
         .update({"status": "CANCELADO"}, synchronize_session=False))
        (Excedente.query.filter_by(doador_id=usuario.id)
         .update({"retirada_endereco": "Endereço removido", "foto_tipo": None,
                  "foto_dados": None}, synchronize_session=False))
    else:
        usuario.cnpj = f"REMOVIDO-{usuario.id:08d}"
        usuario.endereco = "Endereço removido"
        (Doacao.query.filter_by(estabelecimento_id=usuario.id)
         .update({"retirada_endereco": None, "retirada_municipio": None,
                  "retirada_uf": None}, synchronize_session=False))
        (Contribuicao.query.filter_by(estabelecimento_id=usuario.id)
         .update({"foto_dados": None, "foto_arquivo": "removida"},
                 synchronize_session=False))
        (Excedente.query.filter_by(estabelecimento_id=usuario.id)
         .update({"foto_tipo": None, "foto_dados": None}, synchronize_session=False))
    db.session.commit()
    return marcador
