import os
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from foto_oferta import com_foto  # noqa: E402
from cnpj_service import _normalizar_brasilapi, _normalizar_cnpjws, _normalizar_opencnpj  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from Excedentes import _ongs_compativeis  # noqa: E402
from eventos import Evento  # noqa: E402
from models import Contribuicao, Doacao, Estabelecimento, ItemDoacao, db  # noqa: E402
from migracoes import aplicar_migracoes  # noqa: E402


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def empresa(nome, cnpj, *, ong=False, alimentar=False):
    item = Estabelecimento(nome=nome, cnpj=cnpj, email=f"{cnpj}@exemplo.test",
                           telefone="11999999999", endereco="Rua Exemplo, 7 - Centro, São Paulo/SP - 01000000",
                           sem_fins_lucrativos=ong, atividade_alimentar=alimentar)
    db.session.add(item)
    db.session.flush()
    return item


def sessao(cliente, id_):
    with cliente.session_transaction() as sessao_atual:
        sessao_atual["tipo"] = "empresa"
        sessao_atual["usuario_id"] = id_


def anuncio():
    prazo = agora_brasilia_sem_fuso() + timedelta(hours=2)
    validade = prazo.date() + timedelta(days=1)
    return {"retirar_ate": prazo.isoformat(timespec="seconds"),
            "itens": [{"nome": "Pães", "categoria": "Padaria", "quantidade": 4,
                       "unidade_medida": "kg", "validade": validade.isoformat()}],
            "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True}


def test_migracao_perfis_legados_idempotente(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legado.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome TEXT)"))
        conexao.execute(text("INSERT INTO estabelecimentos VALUES (1, 'Mercado legado')"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    assert {"natureza_juridica_codigo", "sem_fins_lucrativos", "atividade_alimentar"} <= {
        coluna["name"] for coluna in inspect(engine).get_columns("estabelecimentos")}
    with engine.connect() as conexao:
        assert conexao.execute(text("""SELECT natureza_juridica_codigo,
            sem_fins_lucrativos, atividade_alimentar FROM estabelecimentos WHERE id=1""")).one() == (None, 0, 1)


def test_normalizacao_natureza_nas_tres_fontes():
    brasil = _normalizar_brasilapi({"codigo_natureza_juridica": 3999,
                                   "natureza_juridica": "Associação Privada"})
    aberto = _normalizar_opencnpj({"natureza_juridica": {"codigo": "3999", "descricao": "Associação Privada"}})
    ws = _normalizar_cnpjws({"natureza_juridica": {"id": "3999", "descricao": "Associação Privada"}})
    for dados in (brasil, aberto, ws):
        assert dados["natureza_juridica"] == {"codigo": "3999", "descricao": "Associação Privada"}


def test_fallback_prioriza_fonte_com_codigo_de_natureza(monkeypatch):
    import cnpj_service
    import requests
    chamadas = []

    class Resposta:
        status_code = 200

        def __init__(self, dados):
            self.dados = dados

        def raise_for_status(self):
            pass

        def json(self):
            return self.dados

    def get(url, timeout, allow_redirects):
        assert allow_redirects is False
        chamadas.append(url)
        if "brasilapi" in url:
            raise requests.Timeout()
        if "opencnpj" in url:
            return Resposta({"razao_social": "Associação", "situacao_cadastral": "Ativa",
                             "cnae_principal": "9499500", "natureza_juridica": "Associação Privada"})
        return Resposta({"razao_social": "Associação",
                         "natureza_juridica": {"id": "3999", "descricao": "Associação Privada"},
                         "estabelecimento": {"situacao_cadastral": "Ativa",
                                             "atividade_principal": {"id": "9499500", "descricao": "Associação"}}})

    cnpj_service._cache.clear()
    monkeypatch.setattr(cnpj_service.requests, "get", get)
    dados = cnpj_service.consultar_cnpj("47508411000156")
    assert dados["fonte"] == "cnpjws"
    assert dados["sem_fins_lucrativos"] is True
    assert len(chamadas) == 3
    cnpj_service._cache.clear()


def test_ong_sem_cnae_alimentar_pode_cadastrar_e_duplo_perfil(monkeypatch):
    import Cadastro
    base = {"cnpj": "12345678000195", "cnpj_formatado": "12.345.678/0001-95",
            "razao_social": "Associação Boa Mesa", "nome_fantasia": "",
            "situacao": "ATIVA", "ativo": True, "cnae_principal": {"codigo": "9499500", "descricao": "Associação"},
            "atividades_alimentares": [], "relacionado_alimentacao": False,
            "natureza_juridica": {"codigo": "3999", "descricao": "Associação Privada"},
            "sem_fins_lucrativos": True,
            "endereco": {"logradouro": "Rua A", "numero": "1", "complemento": "", "bairro": "Centro",
                         "municipio": "São Paulo", "uf": "SP", "cep": "01000000"},
            "email": None, "telefone": None, "fonte": "teste"}
    monkeypatch.setattr(Cadastro, "consultar_cnpj", lambda _cnpj: base)
    cliente = app.test_client()
    consulta = cliente.get("/reconecta/cadastro/cnpj/12345678000195")
    assert consulta.json["apto"] is True
    assert consulta.json["perfis"] == ["ong"]
    resposta = cliente.post("/reconecta/cadastro/empresa", json={
        "cnpj": base["cnpj"], "email": "ong@exemplo.test", "telefone": "11999999999",
        "senha": "Senha1234", "aceite_privacidade": True})
    assert resposta.status_code == 201, resposta.json
    assert cliente.get("/reconecta/auth/me").json["perfis"] == ["ong"]
    with app.app_context():
        assert Estabelecimento.query.first().natureza_juridica_codigo == "3999"
    # Uma entidade com CNAE alimentar possui os dois papéis no mesmo cadastro.
    with app.app_context():
        conta = Estabelecimento.query.first()
        conta.atividade_alimentar = True
        db.session.commit()
    assert cliente.get("/reconecta/auth/me").json["perfis"] == ["ong", "empresa_alimentos"]


def test_excedente_reserva_unica_endereco_privado_e_retirada():
    with app.app_context():
        mercado = empresa("Mercado", "12345678000195", alimentar=True)
        ong = empresa("ONG", "23456789000189", ong=True)
        outra = empresa("Outra ONG", "34567890000189", ong=True)
        ids = mercado.id, ong.id, outra.id
        db.session.commit()
    cliente = app.test_client()
    sessao(cliente, ids[0])
    criado = cliente.post("/reconecta/excedentes", data=com_foto(anuncio()))
    assert criado.status_code == 201, criado.json
    id_ = criado.json["id"]
    assert cliente.post(f"/reconecta/excedentes/{id_}/reservar").status_code == 403
    sessao(cliente, ids[1])
    assert "retirada" not in cliente.get(f"/reconecta/excedentes/{id_}").json
    reservado = cliente.post(f"/reconecta/excedentes/{id_}/reservar")
    assert reservado.status_code == 200, reservado.json
    assert "Rua Exemplo" in reservado.json["retirada"]["endereco"]
    sessao(cliente, ids[2])
    assert "retirada" not in cliente.get(f"/reconecta/excedentes/{id_}").json
    assert cliente.post(f"/reconecta/excedentes/{id_}/reservar").status_code == 409
    sessao(cliente, ids[1])
    assert cliente.post(f"/reconecta/excedentes/{id_}/cancelar-reserva").status_code == 200
    sessao(cliente, ids[2])
    assert cliente.post(f"/reconecta/excedentes/{id_}/reservar").status_code == 200
    sessao(cliente, ids[0])
    assert cliente.post(f"/reconecta/excedentes/{id_}/confirmar-retirada").json["status"] == "RETIRADO"
    assert cliente.post(f"/reconecta/excedentes/{id_}/confirmar-retirada").status_code == 409
    indicadores = cliente.get("/reconecta/dashboard").json["indicadores"]
    assert indicadores["excedentes_resgatados"] == 1
    assert indicadores["ongs"] == 2
    assert indicadores["empresas_alimentos"] == 1
    with app.app_context():
        eventos = Evento.query.order_by(Evento.id).all()
        publicados = [evento for evento in eventos if evento.tipo == "excedente.reservado" and evento.publico]
        privados = [evento for evento in eventos if evento.tipo == "excedente.reservado" and not evento.publico]
        assert len(publicados) == len(privados) == 2
        assert "ong" not in json.loads(publicados[0].dados)
        assert json.loads(privados[0].dados)["ong"] == "ONG"
        assert privados[0].dest_id == ids[0]
        assert any(evento.tipo == "excedente.retirado" and evento.dest_id == ids[2]
                   for evento in eventos)


def test_excedente_validacoes_e_expiracao_sem_job():
    with app.app_context():
        mercado = empresa("Mercado", "12345678000195", alimentar=True)
        ong = empresa("ONG", "23456789000189", ong=True)
        ids = mercado.id, ong.id
        db.session.commit()
    cliente = app.test_client()
    sessao(cliente, ids[1])
    assert cliente.post("/reconecta/excedentes", data=com_foto(anuncio())).status_code == 403
    sessao(cliente, ids[0])
    invalido = anuncio()
    invalido["embalagem_ok"] = False
    assert cliente.post("/reconecta/excedentes", json=invalido).status_code == 400
    criado = cliente.post("/reconecta/excedentes", data=com_foto(anuncio()))
    assert criado.status_code == 201
    id_ = criado.json["id"]
    with app.app_context():
        from models import Excedente
        item = db.session.get(Excedente, id_)
        item.retirar_ate = agora_brasilia_sem_fuso() - timedelta(seconds=1)
        db.session.commit()
    assert cliente.get("/reconecta/excedentes").json == []
    assert cliente.get(f"/reconecta/excedentes/{id_}").json["status"] == "EXPIRADO"
    sessao(cliente, ids[1])
    assert cliente.post(f"/reconecta/excedentes/{id_}/reservar").status_code == 409


def test_destinatarios_do_excedente_exigem_pedido_categoria_e_uf():
    with app.app_context():
        mercado = empresa("Mercado", "12345678000195", alimentar=True)
        ong = empresa("ONG", "23456789000189", ong=True)
        fora = empresa("ONG distante", "34567890000189", ong=True)
        fora.endereco = "Rua A, 1 - Centro, Campinas/RJ - 01000000"
        db.session.flush()
        for organizacao in (ong, fora):
            pedido = Doacao(estabelecimento_id=organizacao.id,
                            data_limite_retirada=agora_brasilia_sem_fuso() + timedelta(days=2))
            db.session.add(pedido)
            db.session.flush()
            db.session.add(ItemDoacao(doacao_id=pedido.id, nome="Pão", categoria="Padaria",
                                       quantidade=3, unidade_medida="kg"))
        db.session.commit()
        oferta = [{"nome": "Pão", "categoria": "Padaria", "quantidade": 3,
                   "unidade_medida": "kg"}]
        assert _ongs_compativeis(oferta, "SP", mercado.id) == (("empresa", ong.id),)
        assert _ongs_compativeis([{**oferta[0], "categoria": "Laticínios", "nome": "Leite"}],
                                 "SP", mercado.id) == ()
        mercado_id, ong_id, fora_id = mercado.id, ong.id, fora.id
    cliente = app.test_client()
    sessao(cliente, mercado_id)
    assert cliente.post("/reconecta/excedentes", data=com_foto(anuncio())).status_code == 201
    with app.app_context():
        privados = Evento.query.filter_by(tipo="excedente.publicado", publico=False).all()
        assert [(evento.dest_tipo, evento.dest_id) for evento in privados] == [("empresa", ong_id)]
        assert all(evento.dest_id != fora_id for evento in privados)


def test_dono_confirma_doacao_e_progresso_preserva_compromisso():
    with app.app_context():
        dona = empresa("ONG", "12345678000195", ong=True)
        outra = empresa("Outra", "23456789000189", ong=True)
        doadora = empresa("Doadora", "34567890000189", alimentar=True)
        db.session.flush()
        pedido = Doacao(estabelecimento_id=dona.id,
                        data_limite_retirada=agora_brasilia_sem_fuso() + timedelta(days=2))
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Pão", categoria="Padaria",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.flush()
        contribuicao = Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id,
                                    estabelecimento_id=doadora.id, alimento="Pão",
                                    categoria="Padaria", quantidade=4, unidade_medida="kg",
                                    validade=date.today() + timedelta(days=3), respostas="{}",
                                    foto_arquivo="a.jpg", status="ACEITA")
        db.session.add(contribuicao)
        db.session.commit()
        ids = dona.id, outra.id, pedido.id, contribuicao.id, item.id, doadora.id
    cliente = app.test_client()
    url = f"/reconecta/painel/contribuicoes/{ids[3]}"
    sessao(cliente, ids[1])
    assert cliente.post(url + "/receber").status_code == 404
    sessao(cliente, ids[0])
    assert cliente.post(url + "/receber").json["status"] == "ENTREGUE"
    assert cliente.post(url + "/nao-recebida").status_code == 409
    detalhe = cliente.get(f"/reconecta/publico/doacoes/{ids[2]}").json
    assert detalhe["itens"][0]["recebido"] == 4
    assert detalhe["itens"][0]["entregue"] == 4
    with app.app_context():
        aviso = Evento.query.filter_by(tipo="doacao.entregue", publico=False).one()
        publico = Evento.query.filter_by(tipo="doacao.entregue", publico=True).one()
        assert publico.dest_tipo is None
        assert json.loads(publico.dados) == {"pedido_id": ids[2], "item": "Pão"}
        assert (aviso.dest_tipo, aviso.dest_id) == ("empresa", ids[5])
        assert json.loads(aviso.dados) == {"pedido_id": ids[2], "item": "Pão"}
    assert cliente.get("/reconecta/dashboard").json["indicadores"]["doacoes_entregues"] == 1
    with app.app_context():
        outra_doacao = Contribuicao(doacao_id=ids[2], item_doacao_id=ids[4],
                                    estabelecimento_id=ids[5], alimento="Pão", categoria="Padaria",
                                    quantidade=3, unidade_medida="kg",
                                    validade=date.today() + timedelta(days=3), respostas="{}",
                                    foto_arquivo="b.jpg", status="ACEITA")
        db.session.add(outra_doacao)
        db.session.commit()
        outra_id = outra_doacao.id
    assert cliente.post(f"/reconecta/painel/contribuicoes/{outra_id}/nao-recebida").json["status"] == "CANCELADA"
    detalhe = cliente.get(f"/reconecta/publico/doacoes/{ids[2]}").json
    assert detalhe["itens"][0]["recebido"] == 4
    assert detalhe["itens"][0]["entregue"] == 4


def test_nome_do_item_nao_leva_a_validade_dita_depois():
    from llm_service import _pedido_regras

    itens = _pedido_regras("sobraram 30 pães e 5 kg de tomate, vencem amanhã", False)["itens"]
    assert [(i["nome"], i["quantidade"]) for i in itens] == [("pães", 30), ("tomate", 5)]
    itens = _pedido_regras("10 kg de camarão congelado, vence em 3 dias", False)["itens"]
    assert itens[0]["nome"] == "camarão congelado"
    itens = _pedido_regras("20 caixas de leite com validade longa", False)["itens"]
    assert itens[0]["nome"] == "leite"
