"""Treina, avalia e aplica os limiares da inteligência central em um comando.

Uso: python scripts/ciclo_ia.py
Não chama Ollama, serviços pagos ou banco de dados.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from fuso import hoje_brasilia  # noqa: E402
from scripts import avaliar_conexao, treinar_modelo  # noqa: E402

LIMIARES = RAIZ / "modelo" / "limiares.json"


def verificar_limiares(metricas, limiares):
    falhas = [f"{nome}: {metricas[nome]:.4f} < {minimo:.4f}"
              for nome, minimo in limiares.items()
              if metricas[nome] < minimo]
    if falhas:
        raise ValueError("Limiar da IA não atingido: " + "; ".join(falhas))


def executar(*, hoje=None, limiares_path=LIMIARES,
             modelo_path=treinar_modelo.MODELO,
             metricas_path=treinar_modelo.METRICAS,
             avaliacao_path=avaliar_conexao.SAIDA):
    hoje = hoje or hoje_brasilia()
    modelo, treino = treinar_modelo.executar(hoje=hoje)
    conexao = avaliar_conexao.gravar(
        avaliar_conexao.avaliar(avaliar_conexao.ler_casos()),
        caminho=avaliacao_path, hoje=hoje)
    metricas = {
        **treino,
        "data": hoje.isoformat(),
        "versao": 1,
        "acuracia_classificador": treino["teste"]["classificador"]["acuracia"],
        "acuracia_top1": conexao["acuracia_top1"],
        "acuracia_top3": conexao["acuracia_top3"],
        "taxa_sem_sugestao_correta": conexao["taxa_sem_sugestao_correta"],
        "tamanho_conjuntos": {
            "alimentos": treino["dataset"]["linhas"],
            "alimentos_treino": treino["dataset"]["treino"],
            "alimentos_teste": treino["dataset"]["teste"],
            "ofertas": conexao["casos"],
            "ofertas_com_destino": conexao["com_destino"],
            "ofertas_sem_destino": conexao["sem_destino"],
        },
    }
    treinar_modelo.gravar(modelo, Path(modelo_path), compacto=True)
    treinar_modelo.gravar(metricas, Path(metricas_path))
    limiares = json.loads(Path(limiares_path).read_text(encoding="utf-8"))
    verificar_limiares(metricas, limiares)
    return metricas


def main():
    try:
        metricas = executar()
    except ValueError as erro:
        sys.exit(str(erro))
    print(f"IA: {metricas['tamanho_conjuntos']['alimentos_teste']} alimentos no teste, "
          f"acurácia {metricas['acuracia_classificador']:.1%}; "
          f"{metricas['tamanho_conjuntos']['ofertas']} ofertas, "
          f"top-1 {metricas['acuracia_top1']:.1%}, "
          f"top-3 {metricas['acuracia_top3']:.1%}, "
          f"sem sugestão correta {metricas['taxa_sem_sugestao_correta']:.1%}.")


if __name__ == "__main__":
    main()
