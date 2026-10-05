import os
from datetime import datetime, timedelta
from time import perf_counter

import pytest
from sqlalchemy import event, inspect, text

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from migracoes import aplicar_migracoes  # noqa: E402
from models import Doacao, Estabelecimento, ItemDoacao, db  # noqa: E402
from Publico import _disponiveis, serializar_doacao  # noqa: E402


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def criar_pedidos(quantidade=3):
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado Verde", cnpj="12345678000195",
            email="verde@exemplo.com", telefone="11999999999",
            endereco="RUA A, 1 - CENTRO, NITERÓI/RJ - 24000000")
        db.session.add(empresa)
        db.session.flush()
        for i in range(quantidade):
            pedido = Doacao(estabelecimento_id=empresa.id, status="DISPONIVEL",
                data_limite_retirada=datetime.now() + timedelta(days=5))
            db.session.add(pedido)
            db.session.flush()
            db.session.add(ItemDoacao(doacao_id=pedido.id,
                nome="Leite" if i % 2 == 0 else "Pão",
                categoria="Laticínios" if i % 2 == 0 else "Padaria",
                quantidade=100, unidade_medida="unidade"))
        db.session.commit()
        return empresa.id


def test_lista_publica_pagina_filtra_e_preserva_lista():
    criar_pedidos()
    cliente = app.test_client()
    resposta = cliente.get("/reconecta/publico/doacoes?pagina=2&por_pagina=1")
    assert resposta.status_code == 200
    assert isinstance(resposta.json, list) and len(resposta.json) == 1
    assert (resposta.headers["X-Total-Count"], resposta.headers["X-Pagina"],
            resposta.headers["X-Por-Pagina"]) == ("3", "2", "1")
    filtrada = cliente.get("/reconecta/publico/doacoes?categoria=Padaria&uf=RJ&busca=pão")
    assert filtrada.status_code == 200
    assert len(filtrada.json) == 1
    assert filtrada.headers["X-Total-Count"] == "1"
    assert cliente.get("/reconecta/publico/doacoes?limite=2").headers["X-Por-Pagina"] == "2"
    assert cliente.get("/reconecta/publico/doacoes?pagina=50&por_pagina=1").json == []


@pytest.mark.parametrize("parametro", ["pagina=0", "pagina=x", "por_pagina=51",
                                        "limite=101", "categoria=Falso", "uf=ZZZ",
                                        "busca=" + "a" * 101])
def test_filtros_invalidos_retornam_400(parametro):
    resposta = app.test_client().get("/reconecta/publico/doacoes?" + parametro)
    assert resposta.status_code == 400
    assert resposta.json["codigo"] == "DADOS_INVALIDOS"
    assert resposta.json["campos"]


def test_consultas_lista_nao_crescem_com_numero_de_pedidos():
    criar_pedidos(25)
    with app.app_context():
        db.session.remove()
        consultas = []

        def contar(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                consultas.append(statement)

        event.listen(db.engine, "before_cursor_execute", contar)
        try:
            inicio = perf_counter()
            antiga = (_disponiveis().order_by(Doacao.data_cadastro.desc(),
                      Doacao.id.desc()).limit(25).all())
            assert len([serializar_doacao(d) for d in antiga]) == 25
            tempo_antigo = perf_counter() - inicio
            total_antigo = len(consultas)
            consultas.clear()
            db.session.remove()
            inicio = perf_counter()
            resposta = app.test_client().get("/reconecta/publico/doacoes?por_pagina=25")
            tempo_novo = perf_counter() - inicio
        finally:
            event.remove(db.engine, "before_cursor_execute", contar)
        assert resposta.status_code == 200
        assert len(resposta.json) == 25
        assert len(consultas) <= 6
        assert len(consultas) < total_antigo
        print(f"lista de 25 pedidos: antes {total_antigo} SELECT/{tempo_antigo:.4f}s; "
              f"depois {len(consultas)} SELECT/{tempo_novo:.4f}s")


def test_dashboard_usa_consultas_agregadas_independentes_do_volume():
    criar_pedidos(25)
    with app.app_context():
        consultas = []

        def contar(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                consultas.append(statement)

        event.listen(db.engine, "before_cursor_execute", contar)
        try:
            inicio = perf_counter()
            resposta = app.test_client().get("/reconecta/dashboard")
            tempo = perf_counter() - inicio
        finally:
            event.remove(db.engine, "before_cursor_execute", contar)
        assert resposta.status_code == 200
        assert resposta.json["indicadores"]["pedidos_abertos"] == 25
        assert len(consultas) <= 12
        print(f"dashboard de 25 pedidos: {len(consultas)} SELECT/{tempo:.4f}s")


def test_migracao_de_indices_e_idempotente():
    criar_pedidos(1)
    with app.app_context():
        with db.engine.begin() as conexao:
            for nome in ("ix_doacoes_status_prazo", "ix_doacoes_estabelecimento_id",
                         "ix_itens_doacao_doacao_id", "ix_contribuicoes_doacao_status",
                         "ix_contribuicoes_item_doacao_id"):
                conexao.execute(text(f"DROP INDEX {nome}"))
        aplicar_migracoes(db.engine)
        aplicar_migracoes(db.engine)
        assert db.session.query(Doacao).count() == 1
        indices = {tabela: {i["name"] for i in inspect(db.engine).get_indexes(tabela)}
                   for tabela in ("doacoes", "itens_doacao", "contribuicoes")}
    assert "ix_doacoes_status_prazo" in indices["doacoes"]
    assert "ix_doacoes_estabelecimento_id" in indices["doacoes"]
    assert "ix_itens_doacao_doacao_id" in indices["itens_doacao"]
    assert "ix_contribuicoes_doacao_status" in indices["contribuicoes"]
    assert "ix_contribuicoes_item_doacao_id" in indices["contribuicoes"]


@pytest.mark.parametrize("rota", ["estabelecimentos", "instituicoes", "doacoes"])
def test_cruds_originais_rejeitam_corpo_ausente_e_campos_faltando(rota):
    cliente = app.test_client()
    for kwargs in ({}, {"json": {}}):
        resposta = cliente.post("/reconecta/" + rota + "/", **kwargs)
        assert resposta.status_code == 400
        assert resposta.json["codigo"] == "DADOS_INVALIDOS"
        assert resposta.json["campos"]


def test_crud_original_valida_tipos_e_referencia_em_post_e_put():
    empresa_id = criar_pedidos(1)
    cliente = app.test_client()
    assert cliente.post("/reconecta/estabelecimentos/", json={
        "nome": 5, "cnpj": [], "email": None, "endereco": True
    }).status_code == 400
    assert cliente.post("/reconecta/instituicoes/", json={
        "nome": 5, "cnpj": [], "email": None, "endereco": True
    }).status_code == 400
    assert cliente.post("/reconecta/doacoes/", json={
        "estabelecimento_id": 999999, "data_limite_retirada": "ontem"
    }).status_code == 400
    assert cliente.put(f"/reconecta/estabelecimentos/{empresa_id}", json={
        "email": 7}).json["codigo"] == "DADOS_INVALIDOS"
    assert cliente.put("/reconecta/doacoes/1", json={
        "data_limite_retirada": "ontem"}).json["codigo"] == "DADOS_INVALIDOS"


def test_erros_404_405_500_api_sao_json_sem_traceback(monkeypatch):
    cliente = app.test_client()
    assert cliente.get("/reconecta/rota-inexistente").json == {
        "codigo": "NAO_ENCONTRADO", "mensagem": "Rota não encontrada."}
    assert cliente.post("/reconecta/dashboard").json == {
        "codigo": "METODO_NAO_PERMITIDO", "mensagem": "Método não permitido."}
    import Dashboard
    def quebrar():
        raise RuntimeError("segredo interno")
    monkeypatch.setattr(Dashboard, "montar_dashboard", quebrar)
    resposta = cliente.get("/reconecta/dashboard")
    assert resposta.status_code == 500
    assert resposta.json == {"codigo": "ERRO_INTERNO",
                             "mensagem": "Não foi possível concluir a solicitação."}
    assert b"segredo interno" not in resposta.data
