"""Treina e avalia o classificador de categorias e grava o modelo em JSON.

Uso:  python scripts/treinar_modelo.py
Lê data/alimentos.csv e grava modelo/classificador_categorias.json e modelo/metricas.json.
Tudo determinístico para a mesma semente (só a data do treino muda).
"""

import csv
import json
import random
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import classificador  # noqa: E402
from llm_service import _categoria as categoria_por_regras  # noqa: E402
from Publico import CATEGORIAS  # noqa: E402

DATASET = RAIZ / "data" / "alimentos.csv"
MODELO = RAIZ / "modelo" / "classificador_categorias.json"
METRICAS = RAIZ / "modelo" / "metricas.json"
SEMENTE = 42
FRACAO_TESTE = 0.2
DOBRAS = 5
GRADE = [{"ngramas": ngramas, "palavras": True, "primeira": primeira, "alfa": alfa}
         for ngramas in ([2, 4], [3, 5])
         for primeira in (0, 1, 2, 4)
         for alfa in (0.03, 0.1, 0.3, 1.0)]


def ler_dataset(caminho=DATASET):
    with Path(caminho).open(encoding="utf-8", newline="") as arquivo:
        return [(linha["texto"], linha["categoria"]) for linha in csv.DictReader(arquivo)]


def dividir(exemplos, semente=SEMENTE, fracao_teste=FRACAO_TESTE):
    """Divisão estratificada por categoria, estável para a mesma semente."""
    sorteio = random.Random(semente)
    treino, teste = [], []
    for categoria in CATEGORIAS:
        grupo = [e for e in exemplos if e[1] == categoria]
        sorteio.shuffle(grupo)
        corte = round(len(grupo) * fracao_teste)
        teste.extend(grupo[:corte])
        treino.extend(grupo[corte:])
    return treino, teste


def dobras_estratificadas(exemplos, dobras=DOBRAS, semente=SEMENTE):
    sorteio = random.Random(semente)
    partes = [[] for _ in range(dobras)]
    for categoria in CATEGORIAS:
        grupo = [e for e in exemplos if e[1] == categoria]
        sorteio.shuffle(grupo)
        for posicao, exemplo in enumerate(grupo):
            partes[posicao % dobras].append(exemplo)
    return partes


def prever(modelo, exemplos):
    """Lista de (categoria prevista, confiança); sem atributo conhecido vira ("Outros", 0)."""
    saida = []
    for texto, _ in exemplos:
        categoria, confianca = modelo.classificar(texto)
        saida.append((categoria or "Outros", confianca))
    return saida


def acuracia(reais, previstos):
    return sum(r == p for r, p in zip(reais, previstos)) / len(reais)


def relatorio(reais, previstos):
    """Acurácia, precisão/recall/F1 por categoria, médias macro e matriz de confusão."""
    matriz = {real: {previsto: 0 for previsto in CATEGORIAS} for real in CATEGORIAS}
    for real, previsto in zip(reais, previstos):
        matriz[real][previsto] += 1
    por_categoria = {}
    for categoria in CATEGORIAS:
        certos = matriz[categoria][categoria]
        previstos_como = sum(matriz[real][categoria] for real in CATEGORIAS)
        reais_da = sum(matriz[categoria].values())
        precisao = certos / previstos_como if previstos_como else 0.0
        recall = certos / reais_da if reais_da else 0.0
        f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
        por_categoria[categoria] = {"precisao": round(precisao, 4), "recall": round(recall, 4),
                                    "f1": round(f1, 4), "suporte": reais_da}
    return {
        "acuracia": round(acuracia(reais, previstos), 4),
        "f1_macro": round(sum(v["f1"] for v in por_categoria.values()) / len(CATEGORIAS), 4),
        "por_categoria": por_categoria,
        "matriz_confusao": {"ordem": CATEGORIAS,
                            "linhas_real_colunas_previsto":
                                [[matriz[r][p] for p in CATEGORIAS] for r in CATEGORIAS]},
    }


def validacao_cruzada(exemplos, config, dobras=DOBRAS, semente=SEMENTE):
    """Acurácia por dobra e as previsões fora da dobra de cada exemplo."""
    partes = dobras_estratificadas(exemplos, dobras, semente)
    acuracias, fora_da_dobra = [], []
    for indice, validacao in enumerate(partes):
        treino = [e for outro, parte in enumerate(partes) if outro != indice for e in parte]
        modelo = classificador.Classificador(classificador.treinar(treino, CATEGORIAS, config))
        previsoes = prever(modelo, validacao)
        acuracias.append(acuracia([e[1] for e in validacao], [p[0] for p in previsoes]))
        fora_da_dobra.extend(zip(validacao, previsoes))
    return acuracias, fora_da_dobra


def escolher_config(treino):
    """Melhor acurácia média em validação cruzada no treino; empate fica com a primeira da grade."""
    melhor, melhor_media = None, -1.0
    grade = []
    for config in GRADE:
        acuracias, _ = validacao_cruzada(treino, config)
        media = sum(acuracias) / len(acuracias)
        grade.append({**config, "acuracia_cv": round(media, 4)})
        if media > melhor_media + 1e-12:
            melhor, melhor_media = config, media
    return melhor, grade


def combinar(exemplo, previsao, limiar):
    """Regra da aplicação: classificador se confiante; senão palavras-chave."""
    categoria, confianca = previsao
    return categoria if confianca >= limiar else categoria_por_regras(exemplo[0])


def escolher_limiar(fora_da_dobra):
    """Limiar que maximiza a acurácia do conjunto classificador + regras fora da dobra.

    Empate fica com o maior limiar (mais conservador).
    """
    reais = [exemplo[1] for exemplo, _ in fora_da_dobra]
    curva = []
    melhor, melhor_acuracia = 0.0, -1.0
    for passo in range(0, 96):
        limiar = passo / 100
        previstos = [combinar(exemplo, previsao, limiar) for exemplo, previsao in fora_da_dobra]
        aceitos = [(exemplo[1], previsao[0]) for exemplo, previsao in fora_da_dobra
                   if previsao[1] >= limiar]
        valor = acuracia(reais, previstos)
        curva.append({"limiar": limiar, "acuracia_combinada": round(valor, 4),
                      "cobertura": round(len(aceitos) / len(reais), 4),
                      "precisao_dos_aceitos": round(
                          sum(r == p for r, p in aceitos) / len(aceitos), 4) if aceitos else None})
        if valor >= melhor_acuracia - 1e-12:
            melhor, melhor_acuracia = limiar, max(valor, melhor_acuracia)
    return melhor, curva


def executar(semente=SEMENTE, hoje=None):
    """Roda treino e avaliação; devolve (modelo final, métricas)."""
    exemplos = ler_dataset()
    treino, teste = dividir(exemplos, semente)
    config, grade = escolher_config(treino)
    acuracias_treino, fora_da_dobra = validacao_cruzada(treino, config)
    limiar, curva = escolher_limiar(fora_da_dobra)

    # avaliação única no teste, com o modelo treinado só no treino
    modelo_treino = classificador.Classificador(classificador.treinar(treino, CATEGORIAS, config))
    reais = [e[1] for e in teste]
    previsoes = prever(modelo_treino, teste)
    erros = [{"texto": e[0], "real": e[1], "previsto": p[0], "confianca": round(p[1], 3)}
             for e, p in zip(teste, previsoes) if e[1] != p[0]]

    acuracias_total, _ = validacao_cruzada(exemplos, config)
    media = sum(acuracias_total) / len(acuracias_total)
    desvio = (sum((a - media) ** 2 for a in acuracias_total) / len(acuracias_total)) ** 0.5

    metricas = {
        "dataset": {"arquivo": "data/alimentos.csv", "linhas": len(exemplos),
                    "treino": len(treino), "teste": len(teste),
                    "por_categoria": {c: sum(e[1] == c for e in exemplos) for c in CATEGORIAS}},
        "semente": semente,
        "config_escolhida": config,
        "grade_validacao_cruzada_no_treino": grade,
        "limiar": limiar,
        "curva_limiar": [p for p in curva if p["limiar"] * 100 % 5 == 0],
        "teste": {
            "classificador": relatorio(reais, [p[0] for p in previsoes]),
            "regras_palavras_chave": relatorio(reais, [categoria_por_regras(e[0]) for e in teste]),
            "classificador_mais_regras": relatorio(
                reais, [combinar(e, p, limiar) for e, p in zip(teste, previsoes)]),
            "erros_do_classificador": erros,
        },
        "validacao_cruzada_dataset_inteiro": {
            "dobras": DOBRAS, "acuracias": [round(a, 4) for a in acuracias_total],
            "media": round(media, 4), "desvio_padrao": round(desvio, 4)},
        "validacao_cruzada_treino": {
            "acuracias": [round(a, 4) for a in acuracias_treino],
            "media": round(sum(acuracias_treino) / len(acuracias_treino), 4)},
    }

    # modelo final: mesma configuração, treinado no dataset inteiro
    final = classificador.treinar(exemplos, CATEGORIAS, config)
    final["limiar"] = limiar
    final["metadados"] = {
        "algoritmo": "Naive Bayes multinomial (n-gramas de caracteres e palavras)",
        "treinado_em": (hoje or date.today()).isoformat(),
        "semente": semente,
        "dataset": "data/alimentos.csv",
        "exemplos_no_modelo_final": len(exemplos),
        "tamanho_treino_avaliado": len(treino),
        "tamanho_teste": len(teste),
        "atributos": len(final["vocabulario"]),
        "acuracia_teste": metricas["teste"]["classificador"]["acuracia"],
        "f1_macro_teste": metricas["teste"]["classificador"]["f1_macro"],
        "acuracia_validacao_cruzada": metricas["validacao_cruzada_dataset_inteiro"]["media"],
        "acuracia_teste_regras": metricas["teste"]["regras_palavras_chave"]["acuracia"],
    }
    return final, metricas


def gravar(objeto, caminho, compacto=False):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        if compacto:
            json.dump(objeto, arquivo, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(objeto, arquivo, ensure_ascii=False, indent=1)
        arquivo.write("\n")


def main():
    final, metricas = executar()
    gravar(final, MODELO, compacto=True)
    gravar(metricas, METRICAS)
    teste = metricas["teste"]
    print(f"dataset: {metricas['dataset']['linhas']} linhas "
          f"(treino {metricas['dataset']['treino']}, teste {metricas['dataset']['teste']})")
    print(f"configuração: {metricas['config_escolhida']}  limiar: {metricas['limiar']}")
    for nome in ("classificador", "regras_palavras_chave", "classificador_mais_regras"):
        print(f"teste {nome}: acurácia {teste[nome]['acuracia']}  F1 macro {teste[nome]['f1_macro']}")
    cv = metricas["validacao_cruzada_dataset_inteiro"]
    print(f"validação cruzada ({cv['dobras']} dobras): {cv['media']} ± {cv['desvio_padrao']}")
    print(f"modelo: {MODELO.relative_to(RAIZ)} ({MODELO.stat().st_size // 1024} KB, "
          f"{final['metadados']['atributos']} atributos)")


if __name__ == "__main__":
    main()
