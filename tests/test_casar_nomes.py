"""Variações de nomes não podem esconder alimentos nem trocar variedades."""

from datetime import timedelta

from conexao import casar
from fuso import agora_brasilia_sem_fuso
from scripts.avaliar_conexao import ler_casos


def _pedido(pid, nome):
    return {"id": pid, "empresa": {"nome": f"ONG {pid}",
                                    "municipio_uf": "São Paulo/SP"},
            "receber_ate": (agora_brasilia_sem_fuso() + timedelta(days=3)).isoformat(),
            "itens": [{"id": pid * 10, "nome": nome, "categoria": "Padaria",
                       "quantidade": 40, "faltam": 25, "unidade_medida": "unidade"}]}


def _oferta(nome):
    return [{"nome": nome, "categoria": "Padaria", "quantidade": 20,
             "unidade_medida": "unidade"}]


def test_pao_frances_atende_pedido_generico_com_peso_inferior_ao_exato():
    pedidos = [_pedido(1, "Pão"), _pedido(2, "Pão francês")]
    sugestoes = casar(_oferta("Pão francês fresco"), pedidos, uf="SP")
    assert [s["pedido_id"] for s in sugestoes] == [2, 1]
    assert sugestoes[0]["pontuacao"] > sugestoes[1]["pontuacao"]


def test_plural_e_descricao_da_oferta_nao_ocultam_pao_frances():
    for nome in ("pães franceses de hoje", "sobra de pães franceses frescos"):
        sugestoes = casar(_oferta(nome), [_pedido(1, "Pão francês")], uf="SP")
        assert [s["pedido_id"] for s in sugestoes] == [1]


def test_cobertura_parcial_aceita_modificadores_sem_subconjunto():
    pedidos = [_pedido(1, "pão francês para café"), _pedido(2, "pão de queijo")]
    sugestoes = casar(_oferta("pães franceses embalados"), pedidos, uf="SP")
    assert [s["pedido_id"] for s in sugestoes] == [1]


def test_tipo_conflitante_e_restricao_alimentar_nao_geram_sugestao():
    assert casar(_oferta("Pão francês"),
                 [_pedido(1, "Pão de queijo"), _pedido(2, "Pão integral")], uf="SP") == []
    assert casar(_oferta("Pão com lactose"),
                 [_pedido(3, "Pão sem lactose")], uf="SP") == []


def test_gabarito_preserva_casos_dificeis_e_novos_rotulos():
    casos = {caso["id"]: caso for caso in ler_casos()}
    assert len(casos) == 86
    assert {f"S{i:02d}" for i in range(1, 17)} <= casos.keys()
    assert {f"N{i:02d}" for i in range(1, 7)} <= casos.keys()
    assert casos["N05"]["esperado_pedido_id"] is None
