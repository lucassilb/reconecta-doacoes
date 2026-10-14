"""Gera lotes simulados e compara modelos de descarte com dados separados.

Uso: python scripts/treinar_risco.py --gerar-dados
     python scripts/treinar_risco.py
Somente este script usa pandas/scikit-learn; a API lê o JSON exportado.
"""

import argparse
import csv
import json
import math
import random
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from risco_descarte import ATRIBUTOS, CATEGORIAS, PERECIVEIS, vetor  # noqa: E402
from scripts import treinar_modelo  # noqa: E402

DATASET = RAIZ / "data" / "lotes_descarte.csv"
MODELO = RAIZ / "modelo" / "risco_descarte.json"
SEMENTE = 1402
SEMENTE_DIVISAO = 42
COLUNAS = ("id", "categoria", "perecivel", "dias_validade", "quantidade_kg",
           "temperatura_c", "armazenamento", "dia_semana", "hora_publicacao",
           "uf", "distancia_ong_km", "descartado")
UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def gerar_linhas(total=3200, semente=SEMENTE):
    """Rótulos sorteados por regra fixa; não são resultado do modelo treinado."""
    sorteio = random.Random(semente)
    linhas = []
    for indice in range(1, total + 1):
        categoria = sorteio.choice(CATEGORIAS)
        perecivel = categoria in PERECIVEIS
        dias = sorteio.randint(0, 12 if perecivel else 45)
        kg = round(math.exp(sorteio.uniform(math.log(.5), math.log(400))), 2)
        armazenamento = sorteio.choices(
            ["ambiente", "refrigerado", "congelado", "nao_informado"],
            weights=[45, 35, 8, 12] if perecivel else [75, 10, 3, 12])[0]
        temperatura_base = {"ambiente": 25, "refrigerado": 5,
                            "congelado": -18, "nao_informado": 20}[armazenamento]
        temperatura = (round(sorteio.gauss(temperatura_base, 4), 1)
                       if armazenamento != "nao_informado" else None)
        distancia = (round(sorteio.uniform(0, 90), 1)
                     if sorteio.random() < .82 else None)
        dia = sorteio.randrange(7)
        hora = sorteio.randrange(24)
        # Premissa didática: validade curta, perecibilidade, calor, volume,
        # distância e horário aumentam o risco. Há aleatoriedade no desfecho.
        escore = (-2.45 + 1.5 / (dias + 1) + .62 * perecivel +
                  .48 * (perecivel and armazenamento == "ambiente") +
                  .035 * max(0, (temperatura or 8) - 8) * perecivel +
                  .13 * math.log1p(kg) + .13 * math.log1p(distancia or 0) +
                  .23 * (dia >= 5) + .18 * (hora < 6 or hora >= 20))
        probabilidade = 1 / (1 + math.exp(-escore))
        linhas.append({
            "id": indice, "categoria": categoria, "perecivel": int(perecivel),
            "dias_validade": dias, "quantidade_kg": kg,
            "temperatura_c": temperatura if temperatura is not None else "",
            "armazenamento": armazenamento, "dia_semana": dia,
            "hora_publicacao": hora, "uf": sorteio.choice(UFS),
            "distancia_ong_km": distancia if distancia is not None else "",
            "descartado": int(sorteio.random() < probabilidade),
        })
    return linhas


def gravar_dataset(caminho=DATASET):
    with Path(caminho).open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(gerar_linhas())


def ler_dataset(caminho=DATASET):
    import pandas as pd

    tabela = pd.read_csv(caminho, keep_default_na=False)
    if list(tabela.columns) != list(COLUNAS) or len(tabela) < 2000:
        raise ValueError("O dataset de descarte exige as 12 colunas e pelo menos 2.000 lotes.")
    if tabela["id"].tolist() != list(range(1, len(tabela) + 1)):
        raise ValueError("IDs de lotes devem ser sequenciais.")
    if not set(tabela["descartado"].unique()) <= {0, 1}:
        raise ValueError("Rótulos de descarte devem ser 0 ou 1.")
    entradas = []
    for linha in tabela.to_dict("records"):
        entradas.append({
            "categoria": linha["categoria"], "perecivel": bool(linha["perecivel"]),
            "dias_validade": linha["dias_validade"], "quantidade_kg": linha["quantidade_kg"],
            "temperatura_c": linha["temperatura_c"], "armazenamento": linha["armazenamento"],
            "dia_semana": linha["dia_semana"], "hora_publicacao": linha["hora_publicacao"],
            "uf": linha["uf"], "distancia_ong_km": linha["distancia_ong_km"],
        })
    atributos = pd.DataFrame([vetor(entrada) for entrada in entradas], columns=ATRIBUTOS)
    return tabela, atributos, tabela["descartado"]


def _modelos():
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "logistica": make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=500, C=.7, random_state=SEMENTE_DIVISAO)),
        "floresta": RandomForestClassifier(
            n_estimators=60, max_depth=8, min_samples_leaf=10,
            random_state=SEMENTE_DIVISAO, n_jobs=1),
    }


def _exportar(modelo, nome, hoje, tamanho):
    artefato = {"versao": 1, "tipo": nome, "atributos": list(ATRIBUTOS),
                "treinado_em": hoje.isoformat(), "exemplos": tamanho,
                "origem": "dados simulados; não mede perdas reais"}
    if nome == "logistica":
        escala, classificador = modelo.steps[0][1], modelo.steps[1][1]
        artefato.update(media=escala.mean_.tolist(), escala=escala.scale_.tolist(),
                        coeficientes=classificador.coef_[0].tolist(),
                        intercepto=float(classificador.intercept_[0]))
    else:
        arvores = []
        for estimador in modelo.estimators_:
            arvore = estimador.tree_
            probabilidades = []
            for no in range(arvore.node_count):
                valores = arvore.value[no][0]
                probabilidades.append(float(valores[1] / sum(valores)))
            arvores.append({
                "esquerda": arvore.children_left.tolist(),
                "direita": arvore.children_right.tolist(),
                "atributo": arvore.feature.tolist(),
                "limiar": arvore.threshold.tolist(),
                "probabilidade": probabilidades,
            })
        artefato["arvores"] = arvores
    return artefato


def executar(*, dataset_path=DATASET, modelo_path=MODELO, hoje=None):
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)
    from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split

    hoje = hoje or date.today()
    tabela, x, y = ler_dataset(dataset_path)
    x_treino, x_teste, y_treino, y_teste = train_test_split(
        x, y, test_size=.2, random_state=SEMENTE_DIVISAO, stratify=y)
    dobras = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEMENTE_DIVISAO)
    modelos = _modelos()
    comparacao = {}
    for nome, modelo in modelos.items():
        cv = cross_validate(modelo, x_treino, y_treino, cv=dobras,
                            scoring={"acuracia": "accuracy", "f1": "f1",
                                     "auc": "roc_auc"}, n_jobs=1)
        comparacao[nome] = {chave: round(float(cv["test_" + chave].mean()), 4)
                            for chave in ("acuracia", "f1", "auc")}
    escolhido = max(modelos, key=lambda nome: (comparacao[nome]["f1"],
                                               comparacao[nome]["auc"],
                                               nome == "logistica"))
    modelo = modelos[escolhido].fit(x_treino, y_treino)
    previstos = modelo.predict(x_teste)
    probabilidades = modelo.predict_proba(x_teste)[:, 1]
    metricas = {"dataset": "data/lotes_descarte.csv", "origem": "simulado",
                "linhas": len(tabela), "treino": len(x_treino), "teste": len(x_teste),
                "descartados": int(y.sum()), "semente": SEMENTE,
                "validacao_cruzada": {"dobras": 5, "modelos": comparacao},
                "modelo_escolhido": escolhido,
                "acuracia": round(float(accuracy_score(y_teste, previstos)), 4),
                "precisao": round(float(precision_score(y_teste, previstos)), 4),
                "recall": round(float(recall_score(y_teste, previstos)), 4),
                "f1": round(float(f1_score(y_teste, previstos)), 4),
                "auc": round(float(roc_auc_score(y_teste, probabilidades)), 4),
                "matriz_confusao": confusion_matrix(y_teste, previstos, labels=[0, 1]).tolist()}
    # O teste acima não participa do ajuste final do artefato.
    modelo.fit(x, y)
    artefato = _exportar(modelo, escolhido, hoje, len(tabela))
    Path(modelo_path).write_text(json.dumps(artefato, ensure_ascii=False,
                                       separators=(",", ":")) + "\n", encoding="utf-8")
    return metricas


def comparar_categorias(acuracia_nb, f1_nb):
    """TF-IDF linear e Naive Bayes atual no mesmo teste independente de 185 linhas."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline

    treino, teste = treinar_modelo.dividir(treinar_modelo.ler_dataset())
    modelo = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                         sublinear_tf=True),
                         LogisticRegression(max_iter=1000, C=4.0))
    textos = [texto for texto, _ in treino]
    rotulos = [rotulo for _, rotulo in treino]
    cv = cross_val_score(modelo, textos, rotulos, cv=StratifiedKFold(
        n_splits=5, shuffle=True, random_state=SEMENTE_DIVISAO), scoring="accuracy")
    modelo.fit(textos, rotulos)
    previstos = modelo.predict([texto for texto, _ in teste])
    reais = [rotulo for _, rotulo in teste]
    acuracia_sk = round(float(accuracy_score(reais, previstos)), 4)
    if acuracia_sk > acuracia_nb:
        raise ValueError("O TF-IDF superou o Naive Bayes; adote e exporte o novo modelo antes do CI.")
    return {"teste": len(teste), "naive_bayes": {"acuracia": acuracia_nb,
            "f1_macro": f1_nb}, "tfidf_linear": {"acuracia": acuracia_sk,
            "f1_macro": round(float(f1_score(reais, previstos, average="macro")), 4),
            "acuracia_cv_treino": round(float(cv.mean()), 4)},
            "adotado": "naive_bayes"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gerar-dados", action="store_true")
    args = parser.parse_args()
    if args.gerar_dados:
        gravar_dataset()
        print(f"Dataset simulado: {DATASET}")
    else:
        print(json.dumps(executar(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
