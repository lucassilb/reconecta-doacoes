"""Compara pedidos inteiros do gabarito com regras e, se houver chave, Groq Free.

Uso: python scripts/avaliar_groq.py
     python scripts/avaliar_groq.py --key-file C:/caminho/groq.key
O intervalo de 12,2 s entre chamadas reais conserva a cota gratuita de tokens.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import llm_service  # noqa: E402
from fuso import hoje_brasilia  # noqa: E402
from scripts.avaliar_modelos import ler_pedidos, pontuar, resolver_prazo  # noqa: E402

CHAVE_LOCAL = Path("C:/Users/lucas/relatorios/reconecta-2026-10-14/r17/groq.key")
SAIDA = RAIZ / "modelo" / "avaliacao_groq.json"


def avaliar(pedidos, funcao):
    perfeitos = 0
    fontes = Counter()
    for pedido in pedidos:
        saida = funcao(pedido["texto"])
        fontes[saida.get("fonte", "regras")] += 1
        esperado = resolver_prazo(pedido["prazo"], hoje_brasilia())
        perfeitos += pontuar(pedido, saida, esperado)["perfeito"]
    return {"pedidos_perfeitos": perfeitos, "total": len(pedidos), "fontes": dict(fontes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", type=Path, default=CHAVE_LOCAL)
    parser.add_argument("--intervalo", type=float, default=12.2,
                        help="segundos mínimos entre chamadas ao Groq")
    args = parser.parse_args()
    pedidos = ler_pedidos()
    resultado = {"data": hoje_brasilia().isoformat(), "pedidos": len(pedidos),
                 "modelo": llm_service._modelo_groq(),
                 "regras": avaliar(pedidos, lambda texto: llm_service._pedido_regras(texto, False)),
                 "classificador_regras": avaliar(pedidos, llm_service._pedido_regras)}
    historico = RAIZ / "modelo" / "avaliacao.json"
    if historico.exists():
        anterior = json.loads(historico.read_text(encoding="utf-8"))
        llm = anterior.get("sistemas", {}).get("llm_aplicacao")
        if llm and llm.get("pedidos") == len(pedidos):
            resultado["ollama_historico"] = {
                "executado_em": anterior.get("executado_em"),
                "pedidos_perfeitos": llm["pedidos_perfeitos"], "total": llm["pedidos"]}

    chave = os.getenv("GROQ_API_KEY", "").strip()
    if not chave and args.key_file.is_file():
        chave = args.key_file.read_text(encoding="utf-8").strip()
    if chave:
        if args.intervalo < 12.2:
            parser.error("o intervalo mínimo é 12,2 s para preservar o Groq Free")
        os.environ["GROQ_API_KEY"] = chave
        fontes = Counter()
        perfeitos = 0
        for indice, pedido in enumerate(pedidos):
            if indice:
                time.sleep(args.intervalo)
            espera = llm_service._groq_estado["aberto_ate"] - time.monotonic()
            if espera > 0:
                time.sleep(espera + 0.2)
            try:
                saida = llm_service.interpretar_pedido(pedido["texto"])
            except llm_service.EntradaRecusada:
                # a guarda de entrada recusa (caso 58, injeção): no app a pessoa reescreve o texto
                fontes["guarda_recusou"] += 1
                print(f"{indice + 1}/{len(pedidos)} fonte=guarda_recusou", flush=True)
                continue
            fontes[saida["modelo"] or "regras"] += 1
            esperado = resolver_prazo(pedido["prazo"], hoje_brasilia())
            perfeitos += pontuar(pedido, saida, esperado)["perfeito"]
            print(f"{indice + 1}/{len(pedidos)} fonte={saida['modelo'] or 'regras'}", flush=True)
        resultado["groq"] = {"avaliado": True, "pedidos_perfeitos": perfeitos,
                             "total": len(pedidos), "fontes": dict(fontes),
                             "chamadas_groq": llm_service._groq_dia["requisicoes"]}
    else:
        resultado["groq"] = {"avaliado": False, "motivo": "GROQ_API_KEY ausente"}
    SAIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()
