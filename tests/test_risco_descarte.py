"""Provas do treino simulado, inferência leve e prioridade pública."""

import json
import os
from datetime import date, timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
import IA  # noqa: E402
from fuso import agora_brasilia_sem_fuso, hoje_brasilia  # noqa: E402
from models import Estabelecimento, Excedente, ItemExcedente, _utc_naive, db  # noqa: E402
from risco_descarte import carregar, prever  # noqa: E402
from scripts import treinar_risco  # noqa: E402


@pytest.fixture(autouse=True)
def banco_temporario():
    app.config["TESTING"] = True
    IA._acessos.clear()
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    IA._acessos.clear()


def test_dataset_simulado_tem_regra_reproduzivel_e_ambas_classes(tmp_path):
    tabela, atributos, rotulos = treinar_risco.ler_dataset()
    assert len(tabela) == 3200 and atributos.shape == (3200, 23)
    assert 0 < rotulos.sum() < len(rotulos)
    assert set(tabela["categoria"]) == set(treinar_risco.CATEGORIAS)
    assert set(tabela["uf"]) == set(treinar_risco.UFS)
    copia = tmp_path / "lotes.csv"
    treinar_risco.gravar_dataset(copia)
    assert copia.read_bytes() == treinar_risco.DATASET.read_bytes()


def test_exportacao_json_reproduz_probabilidade_do_sklearn(tmp_path):
    caminho = tmp_path / "risco.json"
    metricas = treinar_risco.executar(modelo_path=caminho, hoje=date(2026, 10, 14))
    assert metricas["treino"] == 2560 and metricas["teste"] == 640
    assert sum(map(sum, metricas["matriz_confusao"])) == 640
    assert metricas["modelo_escolhido"] in {"logistica", "floresta"}
    gravado = carregar()
    gravado["treinado_em"] = "2026-10-14"
    assert json.loads(caminho.read_text(encoding="utf-8")) == gravado

    tabela, x, y = treinar_risco.ler_dataset()
    modelo_sklearn = treinar_risco._modelos()[metricas["modelo_escolhido"]].fit(x, y)
    lote = tabela.iloc[0].to_dict()
    lote["perecivel"] = bool(lote["perecivel"])
    puro = prever(lote, carregar(caminho))["probabilidade"]
    sklearn = modelo_sklearn.predict_proba(x.iloc[[0]])[0, 1]
    assert abs(puro - sklearn) < .0001

    floresta = treinar_risco._modelos()["floresta"].fit(x, y)
    artefato_floresta = treinar_risco._exportar(floresta, "floresta", date(2026, 10, 14), len(y))
    puro_floresta = prever(lote, artefato_floresta)["probabilidade"]
    assert abs(puro_floresta - floresta.predict_proba(x.iloc[[0]])[0, 1]) < .0001


def test_rota_risco_valida_lote_e_declara_origem_simulada():
    cliente = app.test_client()
    lote = {"categoria": "Hortifrúti", "dias_validade": 0,
            "quantidade_kg": 100, "perecivel": True,
            "armazenamento": "ambiente", "temperatura_c": 29,
            "dia_semana": 5, "hora_publicacao": 22, "uf": "SP",
            "distancia_ong_km": 40}
    resposta = cliente.post("/reconecta/ia/risco-descarte", json=lote)
    assert resposta.status_code == 200
    assert resposta.json == prever(lote)
    assert resposta.json["base"] == "simulacao"
    assert resposta.json["nivel"] == "alto"
    assert "simulados" in resposta.json["aviso"]
    invalido = cliente.post("/reconecta/ia/risco-descarte",
                            json={**lote, "temperatura_c": "infinito"})
    assert invalido.status_code == 400 and invalido.json["codigo"] == "DADOS_INVALIDOS"
    assert "/reconecta/ia/risco-descarte" in cliente.get("/swagger.json").json["paths"]


def test_lista_de_excedentes_ordena_por_risco_sem_expor_endereco():
    with app.app_context():
        mercado = Estabelecimento(nome="Mercado Exemplo", cnpj="12345678000195",
            email="mercado@example.invalid", telefone="11999999999",
            endereco="Rua A, 1 - Centro, São Paulo/SP - 01000000",
            atividade_alimentar=True)
        db.session.add(mercado)
        db.session.flush()
        prazo = agora_brasilia_sem_fuso() + timedelta(days=3)
        hoje = hoje_brasilia()
        for nome, categoria, validade, quantidade, unidade in (
                ("Banana", "Hortifrúti", hoje, 100, "kg"),
                ("Arroz", "Grãos e cereais", hoje + timedelta(days=20), 5, "kg"),
                ("Conserva", "Outros", hoje + timedelta(days=30), 1, "kg")):
            oferta = Excedente(estabelecimento_id=mercado.id, retirar_ate=prazo,
                               criado_em=_utc_naive())
            oferta.itens = [ItemExcedente(nome=nome, categoria=categoria,
                             quantidade=quantidade, unidade_medida=unidade,
                             validade=validade)]
            db.session.add(oferta)
        db.session.commit()

    resposta = app.test_client().get("/reconecta/excedentes?por_pagina=2")
    assert resposta.status_code == 200
    assert resposta.headers["X-Total-Count"] == "3"
    assert len(resposta.json) == 2
    assert resposta.json[0]["prioridade"]["probabilidade"] >= resposta.json[1]["prioridade"]["probabilidade"]
    assert all(item["prioridade"]["base"] == "simulacao" for item in resposta.json)
    assert "Rua A" not in resposta.get_data(as_text=True)


def test_prever_recusa_nan_e_nao_usa_sklearn_na_producao():
    with pytest.raises(ValueError, match="quantidade_kg"):
        prever({"categoria": "Outros", "dias_validade": 1, "quantidade_kg": float("nan")})
    fonte = (treinar_risco.RAIZ / "risco_descarte.py").read_text(encoding="utf-8")
    assert "import sklearn" not in fonte and "import pandas" not in fonte
