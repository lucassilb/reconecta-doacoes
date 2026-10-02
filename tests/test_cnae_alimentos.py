"""Testes do critério CNAE alimentar — catálogo + casos reais (sem rede).

Os casos reais foram colhidos via GET na BrasilAPI em 2026-10-02 e estão
congelados em tests/fixtures/cnpjs_reais.json.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cnae_alimentos import REGRAS_CNAE, classificar_atividades

FIXTURES = Path(__file__).parent / "fixtures" / "cnpjs_reais.json"


def _carregar_casos():
    dados = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return [(caso["nome"], caso) for caso in dados["casos"]]


def _cnaes_do_caso(caso):
    return [caso["cnae_principal"]] + caso["cnaes_secundarios"]


# ---------- normalização de código ----------


def test_codigo_como_int_sem_zero_a_esquerda():
    # BrasilAPI devolve 0155-5/05 como o int 155505
    [item] = classificar_atividades([{"codigo": 155505, "descricao": "Produção de ovos"}])
    assert item["codigo"] == "0155505"
    assert item["categoria"] == "Pecuária e produção animal"


def test_codigo_com_pontuacao():
    [item] = classificar_atividades([{"codigo": "47.11-3/01", "descricao": "Hipermercados"}])
    assert item["codigo"] == "4711301"


def test_codigo_invalido_ou_ausente():
    entradas = [
        {"codigo": None, "descricao": "sem codigo"},
        {"descricao": "sem chave codigo"},
        {"codigo": "", "descricao": "vazio"},
        {"codigo": "12345678", "descricao": "mais de 7 digitos"},
        "string solta",
    ]
    assert classificar_atividades(entradas) == []


def test_lista_vazia():
    assert classificar_atividades([]) == []
    assert classificar_atividades(None) == []


# ---------- regra principal: o código manda, não a descrição ----------


def test_descricao_enganosa_nao_classifica():
    # descrição menciona alimento mas o código é de informática
    assert classificar_atividades(
        [{"codigo": "6201501", "descricao": "Comércio de alimentos (texto forjado)"}]
    ) == []


def test_descricao_nao_alimentar_com_codigo_alimentar_classifica():
    [item] = classificar_atividades(
        [{"codigo": "1091102", "descricao": "texto qualquer"}]
    )
    assert item["codigo"] == "1091102"


# ---------- inclusões do catálogo ----------


@pytest.mark.parametrize(
    "codigo",
    [
        "0111301",  # arroz
        "0115600",  # soja
        "0119905",  # feijão
        "0121101",  # horticultura
        "0134200",  # café
        "0151201",  # bovinos de corte
        "0163600",  # pós-colheita
        "0311601",  # pesca
        "1011201",  # frigorífico
        "1091102",  # padaria com produção própria
        "1121600",  # águas envasadas
        "1122401",  # refrigerantes
        "4631100",  # atacado leite/laticínios
        "4634601",  # atacado carnes
        "4639701",  # atacado alimentos em geral
        "4711301",  # hipermercados
        "4711302",  # supermercados
        "4712100",  # minimercados
        "4721102",  # padaria revenda
        "4722901",  # açougue
        "4723700",  # varejo bebidas
        "4724500",  # hortifruti
        "4729602",  # loja de conveniência
        "4729699",  # outros produtos alimentícios
        "5611201",  # restaurante
        "5620104",  # fornecimento de refeições (catering)
        "8800600",  # assistência social sem alojamento (bancos de alimentos)
    ],
)
def test_codigos_alimentares_sao_aceitos(codigo):
    [item] = classificar_atividades([{"codigo": codigo, "descricao": ""}])
    assert item["codigo"] == codigo
    assert item["categoria"]


# ---------- exclusões do catálogo ----------


@pytest.mark.parametrize(
    "codigo",
    [
        "0112101",  # algodão
        "0114800",  # fumo
        "0122900",  # floricultura
        "0141501",  # sementes certificadas
        "0161099",  # serviços de apoio à agricultura
        "0210107",  # extração de madeira
        "1111901",  # aguardente
        "1112700",  # vinho
        "1113502",  # cerveja
        "1200100",  # produtos do fumo
        "4622200",  # atacado de soja em grão (commodity)
        "4636202",  # atacado de cigarros
        "4713002",  # mercadorias em geral sem predominância alimentar
        "4729601",  # tabacaria
        "4771701",  # farmácia
        "6319400",  # portais de internet
        "9430800",  # associação de defesa de direitos (genérica)
        "9499500",  # associação genérica
    ],
)
def test_codigos_nao_alimentares_sao_recusados(codigo):
    assert classificar_atividades([{"codigo": codigo, "descricao": ""}]) == []


def test_tabacaria_excluida_dentro_da_mesma_classe():
    # 4729-6/01 é tabacaria; /02 e /99 são alimentos — mesma classe CNAE
    resultado = classificar_atividades(
        [
            {"codigo": "4729601", "descricao": "Tabacaria"},
            {"codigo": "4729602", "descricao": "Loja de conveniência"},
            {"codigo": "4729699", "descricao": "Produtos alimentícios"},
        ]
    )
    assert [r["codigo"] for r in resultado] == ["4729602", "4729699"]


def test_ordem_da_entrada_preservada():
    resultado = classificar_atividades(
        [
            {"codigo": "5611201", "descricao": "restaurante"},
            {"codigo": "6319400", "descricao": "portal"},
            {"codigo": "1091102", "descricao": "padaria"},
        ]
    )
    assert [r["codigo"] for r in resultado] == ["5611201", "1091102"]


# ---------- casos reais da BrasilAPI ----------


@pytest.mark.parametrize("nome,caso", _carregar_casos(), ids=[n for n, _ in _carregar_casos()])
def test_caso_real(nome, caso):
    resultado = classificar_atividades(_cnaes_do_caso(caso))
    assert {r["codigo"] for r in resultado} == set(
        caso["esperado"]["cnaes_alimentares"]
    ), f"{nome}: {caso['porque']}"
    assert bool(resultado) is caso["esperado"]["alimentar"]


def test_fixture_cobre_requisitos_minimos():
    casos = [caso for _, caso in _carregar_casos()]
    ativos_alimentares = [
        c for c in casos
        if c["situacao"] == "ATIVA" and c["esperado"]["alimentar"]
        and _regra_alimentar(c["cnae_principal"]["codigo"])
    ]
    assert len(ativos_alimentares) >= 2
    assert any(c["situacao"] == "BAIXADA" for c in casos)
    assert any(
        c["cnae_principal"]["codigo"].startswith("111") for c in casos
    ), "precisa de caso de bebida alcoólica"


def _regra_alimentar(codigo):
    return any(
        alimentar and codigo.startswith(prefixo)
        for prefixo, (alimentar, _) in REGRAS_CNAE.items()
    )
