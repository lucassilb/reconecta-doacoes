"""Regressões da avaliação independente e do ciclo automatizado da IA."""

from datetime import date, timedelta

import pytest

from classificador import carregar
from conexao import casar
from fuso import agora_brasilia_sem_fuso
from scripts import avaliar_conexao, ciclo_ia


def _pedido(pid, itens, dias=5):
    return {"id": pid, "empresa": {"nome": "Associação de bairro",
                                   "municipio_uf": "São Paulo/SP"},
            "receber_ate": (agora_brasilia_sem_fuso() + timedelta(days=dias)).isoformat(),
            "itens": itens}


def _item(nome, categoria, faltam=30, unidade="kg"):
    return {"id": 1, "nome": nome, "categoria": categoria,
            "quantidade": 50, "faltam": faltam, "unidade_medida": unidade}


def test_gabarito_tem_positivos_negativos_e_pedidos_identificados():
    casos = avaliar_conexao.ler_casos()
    assert len(casos) >= 60
    assert sum(c["esperado_pedido_id"] is None for c in casos) >= 10
    assert any(len(c["oferta"]) > 1 for c in casos)
    for caso in casos:
        ids = {p["id"] for p in caso["pedidos_abertos"]}
        assert caso["esperado_pedido_id"] is None or caso["esperado_pedido_id"] in ids


def test_gabarito_reduzido_nao_passa_pelo_ciclo(tmp_path):
    caminho = tmp_path / "ofertas.jsonl"
    caminho.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pelo menos 60"):
        avaliar_conexao.ler_casos(caminho)


def test_avaliacao_distingue_top1_top3_e_rejeicao_correta():
    casos = [
        {"id": "a", "uf": "SP", "oferta": [], "pedidos_abertos": [], "esperado_pedido_id": 11},
        {"id": "b", "uf": "SP", "oferta": [], "pedidos_abertos": [], "esperado_pedido_id": 22},
        {"id": "c", "uf": "SP", "oferta": [], "pedidos_abertos": [], "esperado_pedido_id": None},
    ]
    sugestoes = {"a": [11], "b": [20, 21, 22], "c": []}
    for caso in casos:
        caso["oferta"] = [{"nome": caso["id"]}]
    def casador(itens, pedidos, uf):
        return [{"pedido_id": pid} for pid in sugestoes[itens[0]["nome"]]]
    resultado = avaliar_conexao.avaliar(casos, casador=casador)
    assert (resultado["acertos_top1"], resultado["acertos_top3"],
            resultado["sem_sugestao_corretas"]) == (1, 2, 1)
    assert (resultado["acuracia_top1"], resultado["acuracia_top3"],
            resultado["taxa_sem_sugestao_correta"]) == (0.5, 1.0, 1.0)


def test_casar_exige_alimento_compativel_e_meta_pendente():
    oferta = [{"nome": "banana prata", "categoria": "Hortifrúti",
               "quantidade": 10, "unidade_medida": "kg"}]
    pedidos = [_pedido(1, [_item("maçã gala", "Hortifrúti")]),
               _pedido(2, [_item("banana prata", "Hortifrúti", faltam=0)])]
    assert casar(oferta, pedidos, uf="SP") == []
    assert casar(oferta, [_pedido(3, [_item("banana prata", "Hortifrúti")])],
                 uf="SP")[0]["pedido_id"] == 3
    feijao = [{"nome": "feijão preto", "categoria": "Grãos e cereais",
               "quantidade": 10, "unidade_medida": "kg"}]
    assert casar(feijao, [_pedido(4, [_item("feijão carioca", "Grãos e cereais")])]) == []
    leite = [{"nome": "leite com lactose", "categoria": "Laticínios",
              "quantidade": 10, "unidade_medida": "L"}]
    assert casar(leite, [_pedido(5, [_item("leite sem lactose", "Laticínios",
                                            unidade="L")])]) == []
    paes = [{"nome": "pães", "categoria": "Padaria", "quantidade": 10,
             "unidade_medida": "unidade"}]
    assert casar(paes, [_pedido(6, [_item("pão", "Padaria",
                                           unidade="unidade")])])[0]["pedido_id"] == 6


def test_casar_prefere_pedido_que_aproveita_dois_itens():
    oferta = [{"nome": "pão francês", "categoria": "Padaria", "quantidade": 30,
               "unidade_medida": "unidade"},
              {"nome": "leite integral", "categoria": "Laticínios", "quantidade": 20,
               "unidade_medida": "L"}]
    pao = _item("pão francês", "Padaria", unidade="unidade")
    leite = _item("leite integral", "Laticínios", unidade="L")
    leite["id"] = 2
    pedidos = [_pedido(1, [pao], dias=2), _pedido(2, [pao, leite], dias=5)]
    sugestoes = casar(oferta, pedidos, uf="SP")
    assert sugestoes[0]["pedido_id"] == 2
    assert "atende 2 itens" in sugestoes[0]["motivos"]


def test_ciclo_grava_modelo_metricas_e_bloqueia_regressao(tmp_path):
    modelo = tmp_path / "classificador.json"
    metricas = tmp_path / "metricas.json"
    avaliacao = tmp_path / "avaliacao.json"
    resultado = ciclo_ia.executar(hoje=date(2026, 10, 14),
                                 modelo_path=modelo, metricas_path=metricas,
                                 avaliacao_path=avaliacao)
    assert carregar(modelo).metadados["tamanho_teste"] == 185
    assert resultado["tamanho_conjuntos"]["ofertas"] >= 60
    assert metricas.is_file() and avaliacao.is_file()
    with pytest.raises(ValueError, match="acuracia_top1"):
        ciclo_ia.verificar_limiares(resultado, {"acuracia_top1": 0.99})
