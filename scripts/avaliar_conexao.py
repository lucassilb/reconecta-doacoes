"""Avalia a recomendação de pedidos contra ofertas rotuladas antes da execução.

Uso: python scripts/avaliar_conexao.py
O gabarito em data/ofertas_avaliacao.jsonl não depende de conexao.casar.
"""

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from conexao import casar  # noqa: E402
from fuso import agora_brasilia_sem_fuso, hoje_brasilia  # noqa: E402

CASOS = RAIZ / "data" / "ofertas_avaliacao.jsonl"
SAIDA = RAIZ / "modelo" / "avaliacao_conexao.json"


def ler_casos(caminho=CASOS):
    with Path(caminho).open(encoding="utf-8") as arquivo:
        casos = [json.loads(linha) for linha in arquivo if linha.strip()]
    if len(casos) < 60:
        raise ValueError("O gabarito de conexão precisa de pelo menos 60 casos.")
    ids = [caso["id"] for caso in casos]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs de caso repetidos no gabarito.")
    for caso in casos:
        pedidos = caso["pedidos_abertos"]
        ids_pedidos = [pedido["id"] for pedido in pedidos]
        if len(ids_pedidos) != len(set(ids_pedidos)):
            raise ValueError(f"Pedido repetido no caso {caso['id']}.")
        if caso["esperado_pedido_id"] is not None and caso["esperado_pedido_id"] not in ids_pedidos:
            raise ValueError(f"Pedido esperado ausente no caso {caso['id']}.")
    return casos


def preparar_pedidos(caso, agora):
    """Converte prazos relativos em pedidos no formato de conexao.casar."""
    pedidos = copy.deepcopy(caso["pedidos_abertos"])
    for pedido in pedidos:
        dias = pedido.pop("prazo_dias")
        pedido["receber_ate"] = (agora + timedelta(days=dias)).isoformat()
    return pedidos


def avaliar(casos, *, casador=casar, agora=None):
    agora = agora or agora_brasilia_sem_fuso()
    positivos = sum(caso["esperado_pedido_id"] is not None for caso in casos)
    negativos = len(casos) - positivos
    if not positivos or not negativos:
        raise ValueError("O gabarito precisa de casos com e sem destino correto.")
    top1 = top3 = sem_sugestao = 0
    erros = []
    for caso in casos:
        sugestoes = casador(caso["oferta"], preparar_pedidos(caso, agora), uf=caso["uf"])
        ids = [s["pedido_id"] for s in sugestoes]
        esperado = caso["esperado_pedido_id"]
        if esperado is None:
            sem_sugestao += not ids
            correto = not ids
        else:
            top1 += ids[:1] == [esperado]
            top3 += esperado in ids[:3]
            correto = ids[:1] == [esperado]
        if not correto:
            erros.append({"caso": caso["id"], "esperado_pedido_id": esperado,
                          "sugeridos": ids[:3]})
    return {
        "casos": len(casos), "com_destino": positivos, "sem_destino": negativos,
        "acertos_top1": top1, "acertos_top3": top3,
        "sem_sugestao_corretas": sem_sugestao,
        "acuracia_top1": round(top1 / positivos, 4),
        "acuracia_top3": round(top3 / positivos, 4),
        "taxa_sem_sugestao_correta": round(sem_sugestao / negativos, 4),
        "acuracia_geral_top1": round((top1 + sem_sugestao) / len(casos), 4),
        "erros": erros,
    }


def gravar(resultado, caminho=SAIDA, hoje=None):
    relatorio = {"versao": 1, "data": (hoje or hoje_brasilia()).isoformat(),
                 "gabarito": "data/ofertas_avaliacao.jsonl", **resultado}
    Path(caminho).write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    return relatorio


def main():
    relatorio = gravar(avaliar(ler_casos()))
    print(f"Conexão: {relatorio['casos']} casos "
          f"({relatorio['com_destino']} com destino, {relatorio['sem_destino']} sem destino); "
          f"top-1 {relatorio['acertos_top1']}/{relatorio['com_destino']} "
          f"({relatorio['acuracia_top1']:.1%}), "
          f"top-3 {relatorio['acertos_top3']}/{relatorio['com_destino']} "
          f"({relatorio['acuracia_top3']:.1%}), "
          f"sem sugestão {relatorio['sem_sugestao_corretas']}/{relatorio['sem_destino']} "
          f"({relatorio['taxa_sem_sugestao_correta']:.1%}).")


if __name__ == "__main__":
    main()
