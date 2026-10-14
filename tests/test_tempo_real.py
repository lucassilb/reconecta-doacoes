import json
import os
from datetime import timedelta

import pytest
import requests

os.environ["DATABASE_URL"] = "sqlite://"

from app import app, api  # noqa: E402
import IA  # noqa: E402
import TempoReal  # noqa: E402
from conexao import casar  # noqa: E402
from eventos import Evento, emitir  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from models import Doador, Doacao, Estabelecimento, ItemDoacao, db  # noqa: E402

if not any(n.name == "tempo_real" for n in api.namespaces):
    api.add_namespace(TempoReal.ns, path="/reconecta")


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setattr(requests.Session, "post",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            requests.ConnectionError("fora do ar")))
    IA._acessos.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    IA._acessos.clear()


def _criar_empresa(nome="ONG Esperança", uf="SP", alimentar=False):
    empresa = Estabelecimento(nome=nome, cnpj="12345678000195",
        email=f"{uf.lower()}@exemplo.com", telefone="11999998888",
        endereco=f"Rua Um, 10 - CENTRO, BARUERI/{uf}")
    # a coluna atividade_alimentar chega com a Frente A; antes do merge o teste
    # convive com a ausência dela
    if hasattr(empresa, "atividade_alimentar"):
        empresa.atividade_alimentar = alimentar
    db.session.add(empresa)
    db.session.commit()
    return empresa


def _cliente(tipo, usuario_id):
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["tipo"] = tipo
        sessao["usuario_id"] = usuario_id
    return cliente


def _pedido_aberto(empresa, nome_item="pães", categoria="Padaria", quantidade=100):
    pedido = Doacao(estabelecimento_id=empresa.id,
                    data_limite_retirada=agora_brasilia_sem_fuso() + timedelta(days=2),
                    status="DISPONIVEL")
    db.session.add(pedido)
    db.session.flush()
    db.session.add(ItemDoacao(doacao_id=pedido.id, nome=nome_item,
        categoria=categoria, quantidade=quantidade, unidade_medida="unidade"))
    db.session.commit()
    return pedido


# ---------------- emitir ----------------

def test_emitir_publico_e_destinatarios():
    with app.app_context():
        criados = emitir("pedido.publicado", {"pedido_id": 5}, publico=True,
                         destinatarios=[("empresa", 1), ("doador", 2)])
        db.session.commit()
        assert len(criados) == 3
        rows = Evento.query.order_by(Evento.id).all()
        assert [(r.publico, r.dest_tipo, r.dest_id) for r in rows] == [
            (True, None, None), (False, "empresa", 1), (False, "doador", 2)]
        assert json.loads(rows[0].dados)["pedido_id"] == 5


def test_emitir_privado_sem_publico_e_destino_invalido():
    with app.app_context():
        criados = emitir("doacao.entregue", {"pedido_id": 1}, publico=False,
                         destinatarios=[("doador", 9)])
        db.session.commit()
        assert len(criados) == 1 and criados[0].publico is False
        with pytest.raises(ValueError):
            emitir("x", {}, destinatarios=[("papel", 1)])


# ---------------- novidades ----------------

def test_novidades_sem_desde_so_ultimo_id():
    with app.app_context():
        emitir("pedido.publicado", {"pedido_id": 1})
        db.session.commit()
    resposta = app.test_client().get("/reconecta/novidades")
    assert resposta.status_code == 200
    assert resposta.json["ultimo_id"] >= 1 and resposta.json["eventos"] == []


def test_novidades_desde_zero_publicos_e_proprios():
    with app.app_context():
        emitir("pedido.publicado", {"pedido_id": 1})
        emitir("doacao.entregue", {"pedido_id": 1}, publico=False,
               destinatarios=[("doador", 1), ("doador", 2)])
        db.session.commit()
    anonimo = app.test_client().get("/reconecta/novidades?desde=0")
    assert [e["tipo"] for e in anonimo.json["eventos"]] == ["pedido.publicado"]
    with app.app_context():
        doador = Doador(nome="Ana", cpf="52998224725", email="ana@exemplo.com",
                        telefone="11988887777")
        db.session.add(doador)
        db.session.commit()
        doador_id = doador.id
    emitido = None
    with app.app_context():
        emitir("doacao.entregue", {"pedido_id": 1}, publico=False,
               destinatarios=[("doador", doador_id)])
        db.session.commit()
    cliente = _cliente("doador", doador_id)
    resposta = cliente.get("/reconecta/novidades?desde=0")
    tipos = [e["tipo"] for e in resposta.json["eventos"]]
    assert "pedido.publicado" in tipos and "doacao.entregue" in tipos
    # eventos destinados a outros doadores não vazam
    assert all(e["dados"].get("pedido_id") for e in resposta.json["eventos"])
    assert len([e for e in resposta.json["eventos"] if e["tipo"] == "doacao.entregue"]) == 2


def test_novidades_desde_ignora_antigos():
    with app.app_context():
        emitir("pedido.publicado", {"pedido_id": 1})
        db.session.commit()
        ultimo = db.session.query(Evento.id).scalar()
        emitir("pedido.publicado", {"pedido_id": 2})
        db.session.commit()
    resposta = app.test_client().get(f"/reconecta/novidades?desde={ultimo}")
    assert [e["dados"]["pedido_id"] for e in resposta.json["eventos"]] == [2]


# ---------------- SSE ----------------

def test_tempo_real_entrega_evento_em_sse():
    with app.app_context():
        emitir("pedido.publicado", {"pedido_id": 7, "categorias": ["Padaria"]})
        db.session.commit()
    resposta = app.test_client().get("/reconecta/tempo-real", buffered=False)
    assert resposta.status_code == 200
    assert resposta.mimetype == "text/event-stream"
    assert resposta.headers["Cache-Control"] == "no-cache"
    assert resposta.headers["X-Accel-Buffering"] == "no"
    trecho = b""
    for pedaco in resposta.response:
        trecho += pedaco
        if b"id: " in trecho and b"\n\n" in trecho.split(b"id: ", 1)[1]:
            break
    resposta.close()
    assert trecho.startswith(b": conectado")
    assert b"id: " in trecho and b'"pedido.publicado"' in trecho
    assert b'"pedido_id": 7' in trecho


def test_tempo_real_lotado_503():
    TempoReal._conexoes = TempoReal.MAX_CONEXOES
    try:
        resposta = app.test_client().get("/reconecta/tempo-real")
        assert resposta.status_code == 503
        assert resposta.json["codigo"] == "TEMPO_REAL_LOTADO"
    finally:
        TempoReal._conexoes = 0


# ---------------- notificações ----------------

def test_notificacoes_exigem_login_e_marcam_lidas():
    assert app.test_client().get("/reconecta/notificacoes").status_code == 401
    assert app.test_client().post("/reconecta/notificacoes/lidas",
                                  json={"ate_id": 1}).status_code == 401
    with app.app_context():
        doador = Doador(nome="Ana", cpf="52998224725", email="ana@exemplo.com",
                        telefone="11988887777")
        db.session.add(doador)
        db.session.commit()
        emitir("doacao.entregue", {"pedido_id": 3, "item": "Pães"},
               publico=False, destinatarios=[("doador", doador.id)])
        emitir("pedido.publicado", {"pedido_id": 9})  # público não é notificação
        db.session.commit()
        doador_id = doador.id
    cliente = _cliente("doador", doador_id)
    resposta = cliente.get("/reconecta/notificacoes")
    assert resposta.status_code == 200
    lista = resposta.json["notificacoes"]
    assert len(lista) == 1 and lista[0]["tipo"] == "doacao.entregue"
    assert lista[0]["lida"] is False
    ultimo = lista[0]["id"]
    marcado = cliente.post("/reconecta/notificacoes/lidas", json={"ate_id": ultimo})
    assert marcado.status_code == 200 and marcado.json["lido_ate"] == ultimo
    assert cliente.get("/reconecta/notificacoes").json["notificacoes"][0]["lida"] is True
    assert cliente.post("/reconecta/notificacoes/lidas",
                        json={"ate_id": "abc"}).status_code == 400


# ---------------- casar (função pura) ----------------

def _pedido_dicionario(pid=1, categoria="Padaria", nome="pães", faltam=70,
                       quantidade=100, uf="SP", dias=2, unidade="unidade"):
    return {"id": pid, "estabelecimento_id": pid + 100,
            "empresa": {"nome": f"ONG {pid}", "municipio_uf": f"BARUERI/{uf}"},
            "receber_ate": (agora_brasilia_sem_fuso() + timedelta(days=dias)).isoformat(),
            "itens": [{"id": pid * 10, "nome": nome, "categoria": categoria,
                       "quantidade": quantidade, "unidade_medida": unidade,
                       "recebido": quantidade - faltam, "faltam": faltam}]}


def test_casar_prioriza_categoria_uf_e_prazo():
    itens = [{"nome": "pães", "categoria": "Padaria", "quantidade": 30,
              "unidade_medida": "unidade"}]
    pedidos = [_pedido_dicionario(1, uf="SP", dias=2),
               _pedido_dicionario(2, uf="RJ", dias=30),
               _pedido_dicionario(3, categoria="Carnes e peixes", nome="frango", uf="SP")]
    sugestoes = casar(itens, pedidos, uf="SP")
    assert sugestoes[0]["pedido_id"] == 1
    assert sugestoes[0]["pontuacao"] > sugestoes[1]["pontuacao"]
    assert "mesma UF" in sugestoes[0]["motivos"]
    assert any("faltam 70" in m for m in sugestoes[0]["motivos"])
    assert sugestoes[0]["quantidade_sugerida"] == 30
    assert sugestoes[0]["item_id"] == 10
    assert sugestoes[0]["estabelecimento_id"] == 101


def test_casar_sem_compatibilidade_devolve_vazio():
    itens = [{"nome": "pão", "categoria": "Padaria", "quantidade": 10,
              "unidade_medida": "unidade"}]
    pedidos = [_pedido_dicionario(1, categoria="Carnes e peixes", nome="sardinha")]
    assert casar(itens, pedidos) == []


def test_casar_limita_a_cinco_sugestoes():
    itens = [{"nome": "arroz", "categoria": "Grãos e cereais", "quantidade": 10,
              "unidade_medida": "kg"}]
    pedidos = [_pedido_dicionario(i, categoria="Grãos e cereais", nome="arroz",
                                  faltam=50, quantidade=50, unidade="kg")
               for i in range(1, 8)]
    assert len(casar(itens, pedidos)) == 5


# ---------------- /ia/sugerir-destino ----------------

def test_sugerir_destino_auth_e_validacao():
    anonimo = app.test_client().post("/reconecta/ia/sugerir-destino",
                                     json={"texto": "sobraram 30 pães"})
    assert anonimo.status_code == 401
    with app.app_context():
        empresa = _criar_empresa()
        empresa_id = empresa.id
    cliente = _cliente("empresa", empresa_id)
    for corpo in ({}, {"texto": "oi"}, {"texto": "x" * 601}):
        assert cliente.post("/reconecta/ia/sugerir-destino", json=corpo).status_code == 400


def test_sugerir_destino_sugere_pedido_que_combina():
    with app.app_context():
        ong = _criar_empresa("ONG Esperança", "SP")
        _pedido_aberto(ong, nome_item="pães", categoria="Padaria", quantidade=100)
        empresa = Estabelecimento(nome="Padaria Sol", cnpj="22345678000195",
            email="sol@exemplo.com", telefone="11999997777",
            endereco="Rua Dois, 20 - CENTRO, BARUERI/SP")
        # com a coluna da Frente A, empresa de alimentos pode publicar excedente
        alimentar = hasattr(empresa, "atividade_alimentar")
        if alimentar:
            empresa.atividade_alimentar = True
        db.session.add(empresa)
        db.session.commit()
        empresa_id = empresa.id
    cliente = _cliente("empresa", empresa_id)
    resposta = cliente.post("/reconecta/ia/sugerir-destino",
                            json={"texto": "sobraram 30 pães"})
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "regras"  # Ollama fora do ar nos testes
    assert resposta.json["itens"] and resposta.json["sugestoes"]
    topo = resposta.json["sugestoes"][0]
    assert topo["organizacao"] == "ONG Esperança"
    # com endereço localizável, a distância (geo.py) substitui a regra de mesma UF
    assert "na mesma cidade" in topo["motivos"]
    assert topo["quantidade_sugerida"] == 30
    assert resposta.json["pode_publicar_excedente"] is alimentar


def test_sugerir_destino_limite_por_usuario():
    with app.app_context():
        doador = Doador(nome="Ana", cpf="52998224725", email="ana@exemplo.com",
                        telefone="11988887777")
        db.session.add(doador)
        db.session.commit()
        doador_id = doador.id
    cliente = _cliente("doador", doador_id)
    for _ in range(10):
        assert cliente.post("/reconecta/ia/sugerir-destino",
                            json={"texto": "sobraram 10 pães"}).status_code == 200
    bloqueado = cliente.post("/reconecta/ia/sugerir-destino",
                             json={"texto": "sobraram 10 pães"})
    assert bloqueado.status_code == 429 and bloqueado.json["codigo"] == "MUITAS_TENTATIVAS"
