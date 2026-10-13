import csv
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")

import classificador  # noqa: E402
import llm_service  # noqa: E402
from Publico import CATEGORIAS, UNIDADES  # noqa: E402
from scripts import avaliar_modelos, treinar_modelo  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
CSV = RAIZ / "data" / "alimentos.csv"
PEDIDOS = RAIZ / "data" / "pedidos_avaliacao.jsonl"
MODELO = RAIZ / "modelo" / "classificador_categorias.json"


@pytest.fixture(scope="module")
def linhas():
    with CSV.open(encoding="utf-8", newline="") as arquivo:
        leitor = csv.DictReader(arquivo)
        assert leitor.fieldnames == ["id", "texto", "categoria", "unidade_sugerida", "origem"]
        return list(leitor)


@pytest.fixture(scope="module")
def treino():
    """Um treino completo por módulo (alguns segundos, Python puro)."""
    return treinar_modelo.executar(hoje=date(2026, 1, 1))


# ---------- dataset ----------

def test_dataset_tem_formato_tamanho_e_categorias_validas(linhas):
    assert len(linhas) >= 600
    assert [int(l["id"]) for l in linhas] == list(range(1, len(linhas) + 1))
    assert {l["categoria"] for l in linhas} == set(CATEGORIAS)
    assert {l["unidade_sugerida"] for l in linhas} <= set(UNIDADES)
    assert {l["origem"] for l in linhas} == {"nome_base", "variacao_escrita", "embalagem"}
    assert all(l["texto"] == l["texto"].strip() and 2 <= len(l["texto"]) <= 100 for l in linhas)
    por_categoria = {c: sum(l["categoria"] == c for l in linhas) for c in CATEGORIAS}
    assert min(por_categoria.values()) >= 60, por_categoria


def test_dataset_sem_duplicata_nem_dado_pessoal(linhas):
    chaves = [" ".join(llm_service._sem_acentos(l["texto"]).split()) for l in linhas]
    assert len(chaves) == len(set(chaves)), "texto repetido (ignorando acento e caixa)"
    for l in linhas:
        assert "@" not in l["texto"]
        assert not re.search(r"\d{8,}|\d{3}\.\d{3}\.\d{3}|\(\d{2}\)", l["texto"]), l["texto"]


def test_dataset_e_o_que_o_gerador_produz(linhas):
    from data import gerar_dataset
    assert [[str(c) for c in linha] for linha in gerar_dataset.linhas()] == \
        [[l[c] for c in gerar_dataset.COLUNAS] for l in linhas]


def test_pedidos_de_avaliacao_tem_gabarito_valido():
    pedidos = avaliar_modelos.ler_pedidos()
    assert len(pedidos) >= 60
    assert [p["id"] for p in pedidos] == list(range(1, len(pedidos) + 1))
    assert {p["dificuldade"] for p in pedidos} == {"facil", "medio", "dificil"}
    for p in pedidos:
        assert 5 <= len(p["texto"]) <= 600 and p["itens"]
        for item in p["itens"]:
            assert item["categoria"] in CATEGORIAS and item["unidade_medida"] in UNIDADES
            assert item["nome"] and item["quantidade"] > 0
        # todo prazo do gabarito vira uma data futura no dia da execução
        prazo = avaliar_modelos.resolver_prazo(p["prazo"], date(2026, 10, 13))
        assert prazo is None or date.fromisoformat(prazo) > date(2026, 10, 13)


# ---------- treino ----------

def test_treino_e_reprodutivel_e_o_modelo_do_repositorio_esta_em_dia(treino):
    final, _ = treino
    outro, _ = treinar_modelo.executar(hoje=date(2026, 1, 1))
    assert json.dumps(final, sort_keys=True) == json.dumps(outro, sort_keys=True)
    gravado = json.loads(MODELO.read_text(encoding="utf-8"))
    for modelo in (final, gravado):
        modelo["metadados"] = {**modelo["metadados"], "treinado_em": "-"}
    assert json.loads(json.dumps(final)) == gravado, \
        "rode python scripts/treinar_modelo.py depois de mudar o dataset ou o treino"


def test_divisao_estratificada_sem_vazamento(treino, linhas):
    exemplos = treinar_modelo.ler_dataset()
    parte_treino, parte_teste = treinar_modelo.dividir(exemplos)
    assert len(parte_treino) + len(parte_teste) == len(linhas)
    assert not {t for t, _ in parte_treino} & {t for t, _ in parte_teste}
    for categoria in CATEGORIAS:
        total = sum(c == categoria for _, c in exemplos)
        no_teste = sum(c == categoria for _, c in parte_teste)
        assert abs(no_teste - 0.2 * total) <= 1
    assert (parte_treino, parte_teste) == treinar_modelo.dividir(exemplos)


def test_acuracia_minima_e_melhor_que_as_regras(treino):
    _, metricas = treino
    teste = metricas["teste"]
    assert teste["classificador"]["acuracia"] >= 0.70
    assert teste["classificador"]["f1_macro"] >= 0.70
    assert metricas["validacao_cruzada_dataset_inteiro"]["media"] >= 0.72
    assert teste["classificador"]["acuracia"] >= teste["regras_palavras_chave"]["acuracia"] + 0.15
    assert teste["classificador_mais_regras"]["acuracia"] >= teste["regras_palavras_chave"]["acuracia"]
    matriz = teste["classificador"]["matriz_confusao"]["linhas_real_colunas_previsto"]
    assert sum(map(sum, matriz)) == metricas["dataset"]["teste"]
    assert 0 < metricas["limiar"] < 1


# ---------- modelo gravado ----------

def test_modelo_e_json_sem_pickle_e_classifica():
    assert MODELO.read_text(encoding="utf-8").lstrip().startswith("{")
    for fonte in ("classificador.py", "scripts/treinar_modelo.py"):
        texto = (RAIZ / fonte).read_text(encoding="utf-8")
        assert "import pickle" not in texto and "joblib" not in texto
    modelo = classificador.carregar()
    assert modelo.categorias == CATEGORIAS
    assert modelo.metadados["exemplos_no_modelo_final"] >= 600
    for texto, esperada in (("leite integral 1L", "Laticínios"), ("pao frances", "Padaria"),
                            ("arroz tipo 1 5kg", "Grãos e cereais"), ("BANANA PRATA", "Hortifrúti"),
                            ("marmitas", "Refeições prontas"), ("açúcar", "Outros")):
        categoria, confianca = classificador.classificar(texto)
        assert categoria == esperada, texto
        assert modelo.limiar <= confianca <= 1
    pontos = modelo.pontuar("suco de laranja")
    assert len(pontos) == len(CATEGORIAS) and abs(sum(c for _, c in pontos) - 1) < 1e-9


def test_texto_sem_atributo_conhecido_nao_recebe_categoria():
    assert classificador.classificar("") == (None, 0.0)
    assert classificador.classificar("12345 !!!")[0] is None
    assert classificador.classificar("!!! ???") == (None, 0.0)


def test_modelo_ausente_ou_invalido_nao_derruba(tmp_path):
    with pytest.raises(OSError):
        classificador.carregar(tmp_path / "nao-existe.json")
    ruim = tmp_path / "ruim.json"
    ruim.write_text('{"versao": 99}', encoding="utf-8")
    with pytest.raises(ValueError):
        classificador.carregar(ruim)


# ---------- integração no llm_service ----------

def test_categoria_do_item_vem_do_classificador_quando_confiante():
    # a regra de palavras-chave erra estes; o modelo treinado acerta
    assert llm_service._categoria("pão de queijo") == "Laticínios"
    assert llm_service._categoria_item("pão de queijo") == "Padaria"
    assert llm_service._categoria("molho de tomate") == "Hortifrúti"
    assert llm_service._categoria_item("molho de tomate") == "Outros"
    assert llm_service._categoria("presunto") == "Outros"
    assert llm_service._categoria_item("presunto") == "Carnes e peixes"
    assert llm_service._categoria_item("pão de queijo", usar_classificador=False) == "Laticínios"


def test_abaixo_do_limiar_ou_sem_modelo_valem_as_regras(monkeypatch):
    monkeypatch.setattr(classificador, "classificar", lambda _t: ("Padaria", 0.01))
    assert llm_service._categoria_item("leite") == "Laticínios"
    assert llm_service._categoria_item("xyzw") == "Outros"
    monkeypatch.undo()
    monkeypatch.setattr(classificador, "modelo_padrao", lambda: None)
    assert classificador.classificar("leite") == (None, 0.0) and classificador.limiar() == 1.0
    assert llm_service._categoria_item("leite") == "Laticínios"
    assert llm_service._categoria_item("presunto") == "Outros"


def test_pedido_por_regras_usa_o_classificador_e_mantem_o_contrato():
    saida = llm_service._pedido_regras(
        "Oi, tudo bem? Precisamos de 2,5 kg de presunto e 300 unidades de pão de queijo até sexta")
    assert [(i["nome"], i["categoria"], i["quantidade"], i["unidade_medida"])
            for i in saida["itens"]] == [("presunto", "Carnes e peixes", 2.5, "kg"),
                                         ("pão de queijo", "Padaria", 300.0, "unidade")]
    assert set(saida) == {"itens", "receber_ate", "observacoes"}
    assert all(set(i) == {"nome", "categoria", "quantidade", "unidade_medida"}
               for i in saida["itens"])
    sem = llm_service._pedido_regras("300 unidades de pão de queijo", usar_classificador=False)
    assert sem["itens"][0]["categoria"] == "Laticínios"


def test_script_de_demonstracao_roda():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "classificar.py"), "leite integral 1L"],
        capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=RAIZ,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "DATABASE_URL": "sqlite://"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode == 0, resultado.stderr
    assert "Laticínios" in resultado.stdout and "limiar" in resultado.stdout
