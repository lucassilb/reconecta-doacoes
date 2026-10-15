"""Demonstração isolada do banco configurado e identificada como simulada."""
import os
from datetime import datetime, timedelta

from sqlalchemy import event

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
import Dashboard  # noqa: E402
from fuso import BRASILIA, inicio_dia_utc  # noqa: E402
from models import Contribuicao, Estabelecimento, db  # noqa: E402


def test_demonstracao_usa_sqlite_separado_e_semente_deterministica():
    with app.app_context():
        db.drop_all()
        db.create_all()
        consultas_reais = []

        def observar(_conn, _cursor, comando, _parametros, _contexto, _varios):
            consultas_reais.append(comando)

        event.listen(db.engine, "before_cursor_execute", observar)
        try:
            cliente = app.test_client()
            resumo = cliente.get("/reconecta/dashboard?modo=demonstracao")
            impacto = cliente.get("/reconecta/dashboard/impacto?modo=demonstracao")
            seguranca = cliente.get("/reconecta/dashboard/seguranca?modo=demonstracao")
            repetido = cliente.get("/reconecta/dashboard/impacto?modo=demonstracao")
        finally:
            event.remove(db.engine, "before_cursor_execute", observar)

        assert consultas_reais == []  # nem SELECT nem INSERT no banco configurado
        assert Contribuicao.query.count() == 0
        assert Estabelecimento.query.count() == 0

    assert all(r.status_code == 200 for r in (resumo, impacto, seguranca, repetido))
    assert all(r.json["modo"] == "demonstracao" for r in (resumo, impacto, seguranca))
    indicadores = resumo.json["indicadores"]
    assert indicadores["ongs"] == 100
    assert indicadores["empresas"] == 105
    assert indicadores["empresas_alimentos"] == 5
    assert indicadores["doadores"] == 8
    assert indicadores["doacoes_recebidas"] == 288
    assert indicadores["doacoes_entregues"] == 224
    assert indicadores["excedentes_resgatados"] == 112
    assert impacto.json["peso"] == {"kg_medido": 1690.765, "kg_estimado": 6053.54,
                                    "refeicoes_estimadas": 15489, "itens_sem_conversao": 0}
    assert len(impacto.json["refeicoes"]["por_regiao"]) == 5
    assert sum(sum(dia) for dia in impacto.json["calor_doacoes"]["valores"]) == 288
    assert impacto.json == repetido.json
    assert impacto.json["ia"]["metricas"]["acuracia_classificador"] == 0.7784
    assert seguranca.json["sast"]["ferramentas"]["trivy-image"]["severidades"]["HIGH"] == 44
    assert "example.invalid" not in resumo.get_data(as_text=True)
    assert "DEMO-CNPJ" not in resumo.get_data(as_text=True)


def test_padrao_real_e_pagina_declara_faixa_e_alternancia():
    with app.app_context():
        db.drop_all()
        db.create_all()
        cliente = app.test_client()
        real = cliente.get("/reconecta/dashboard")
        impacto_real = cliente.get("/reconecta/dashboard/impacto")
    assert "modo" not in real.json
    assert real.json["indicadores"]["doacoes_entregues"] == 0
    assert impacto_real.json["peso"]["kg_medido"] == 0
    html = cliente.get("/dashboard").get_data(as_text=True)
    assert "Dados de demonstração — simulados, não são doações reais" in html
    assert 'id="modo-real"' in html and 'id="modo-demonstracao"' in html
    assert 'id="impacto-sobretitulo"' in html and 'id="impacto-descricao"' in html
    assert 'data-ind="empresas"' not in html
    assert 'data-ind="instituicoes"' not in html
    assert 'data-ind="empresas_alimentos"' in html and 'data-ind="ongs"' in html
    assert "Cobertura média por item aberto" in html


def test_resumo_sast_tem_copia_incluida_na_imagem(monkeypatch, tmp_path):
    pasta = tmp_path / "data"
    pasta.mkdir()
    (pasta / "resumo_sast.json").write_text('{"origem":"snapshot"}', encoding="utf-8")
    monkeypatch.setattr(Dashboard, "RAIZ", tmp_path)
    assert Dashboard._resumo_sast() == {"origem": "snapshot"}


def test_semente_tem_mesmo_calor_em_workers_do_mesmo_dia(monkeypatch):
    dia = datetime(2026, 10, 14, tzinfo=BRASILIA)
    monkeypatch.setattr(Dashboard, "_DEMO_APP", None)
    monkeypatch.setattr(Dashboard, "_DEMO_DIA", None)
    monkeypatch.setattr(Dashboard, "agora_brasilia", lambda: dia.replace(hour=8))
    primeiro = app.test_client().get("/reconecta/dashboard/impacto?modo=demonstracao")
    with Dashboard._DEMO_APP.app_context():
        criado_primeiro = Contribuicao.query.order_by(Contribuicao.id).first().criado_em

    # Outra instância de processo, iniciada mais tarde no mesmo dia.
    monkeypatch.setattr(Dashboard, "_DEMO_APP", None)
    monkeypatch.setattr(Dashboard, "_DEMO_DIA", None)
    monkeypatch.setattr(Dashboard, "agora_brasilia", lambda: dia.replace(hour=22))
    segundo = app.test_client().get("/reconecta/dashboard/impacto?modo=demonstracao")
    with Dashboard._DEMO_APP.app_context():
        criado_segundo = Contribuicao.query.order_by(Contribuicao.id).first().criado_em

    assert primeiro.status_code == segundo.status_code == 200
    assert criado_primeiro == criado_segundo
    assert criado_primeiro < inicio_dia_utc(dia.date())
    assert primeiro.json == segundo.json


def test_demonstracao_ressemeia_quando_dia_muda(monkeypatch):
    relogio = {"agora": datetime(2026, 10, 14, 23, 59, tzinfo=BRASILIA)}
    monkeypatch.setattr(Dashboard, "_DEMO_APP", None)
    monkeypatch.setattr(Dashboard, "_DEMO_DIA", None)
    monkeypatch.setattr(Dashboard, "agora_brasilia", lambda: relogio["agora"])
    cliente = app.test_client()
    primeiro = cliente.get("/reconecta/dashboard?modo=demonstracao")
    app_primeiro = Dashboard._DEMO_APP
    relogio["agora"] += timedelta(minutes=2)
    segundo = cliente.get("/reconecta/dashboard?modo=demonstracao")

    assert primeiro.status_code == segundo.status_code == 200
    assert Dashboard._DEMO_APP is not app_primeiro
    assert Dashboard._DEMO_DIA == relogio["agora"].date()
    assert primeiro.json["por_dia"][-1]["data"] == "2026-10-14"
    assert segundo.json["por_dia"][-1]["data"] == "2026-10-15"
    assert primeiro.json["indicadores"]["pedidos_abertos"] > 0
    assert segundo.json["indicadores"]["pedidos_abertos"] > 0
    assert any(d["doacoes"] for d in segundo.json["por_dia"])
