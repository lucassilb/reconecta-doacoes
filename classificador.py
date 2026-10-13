"""Classificador local de categoria de alimento (Naive Bayes multinomial em Python puro).

O modelo treinado fica em modelo/classificador_categorias.json (texto, sem pickle).
Treino e avaliação: scripts/treinar_modelo.py. Dataset: data/alimentos.csv.
"""

import json
import math
import re
import threading
import unicodedata
from pathlib import Path

CAMINHO_MODELO = Path(__file__).resolve().parent / "modelo" / "classificador_categorias.json"
CONFIG_PADRAO = {"ngramas": [2, 4], "palavras": True, "primeira": 1, "alfa": 0.1}
VERSAO_FORMATO = 1


def normalizar(texto):
    """Minúsculas, sem acento, dígitos trocados por 0 e espaços simples."""
    sem = "".join(c for c in unicodedata.normalize("NFKD", str(texto).lower())
                  if not unicodedata.combining(c))
    sem = re.sub(r"\d", "0", sem)
    sem = re.sub(r"[^a-z0 ]+", " ", sem)
    return " ".join(sem.split())


def extrair_atributos(texto, config=None):
    """N-gramas de caracteres por palavra (com bordas), as palavras e a primeira palavra.

    A primeira palavra costuma ser o alimento em si ("molho de tomate" é molho, não
    tomate); "primeira" diz quantas vezes esse atributo entra na conta.
    """
    config = config or CONFIG_PADRAO
    minimo, maximo = config["ngramas"]
    palavras = normalizar(texto).split()
    atributos = ["1:" + palavras[0]] * config.get("primeira", 0) if palavras else []
    for palavra in palavras:
        if config["palavras"]:
            atributos.append("p:" + palavra)
        marcada = f"^{palavra}$"
        for tamanho in range(minimo, maximo + 1):
            for inicio in range(len(marcada) - tamanho + 1):
                atributos.append(marcada[inicio:inicio + tamanho])
    return atributos


def treinar(exemplos, categorias, config=None):
    """exemplos: lista de (texto, categoria). Devolve o dicionário do modelo."""
    config = dict(config or CONFIG_PADRAO)
    indice = {categoria: i for i, categoria in enumerate(categorias)}
    documentos = [0] * len(categorias)
    totais = [0] * len(categorias)
    vocabulario = {}
    for texto, categoria in exemplos:
        classe = indice[categoria]
        documentos[classe] += 1
        for atributo in extrair_atributos(texto, config):
            contagens = vocabulario.setdefault(atributo, {})
            contagens[classe] = contagens.get(classe, 0) + 1
            totais[classe] += 1
    return {
        "versao": VERSAO_FORMATO,
        "config": config,
        "categorias": list(categorias),
        "documentos": documentos,
        "totais": totais,
        # atributo -> [[classe, contagem], ...] em ordem estável
        "vocabulario": {atributo: sorted(contagens.items())
                        for atributo, contagens in sorted(vocabulario.items())},
    }


class Classificador:
    def __init__(self, modelo):
        if modelo.get("versao") != VERSAO_FORMATO:
            raise ValueError("Formato de modelo desconhecido.")
        self.config = modelo["config"]
        self.categorias = modelo["categorias"]
        self.limiar = float(modelo.get("limiar", 0.0))
        self.metadados = modelo.get("metadados", {})
        classes = range(len(self.categorias))
        alfa = self.config["alfa"]
        tamanho = len(modelo["vocabulario"])
        documentos = modelo["documentos"]
        total_documentos = sum(documentos)
        self._priori = [math.log((documentos[c] + 1) / (total_documentos + len(documentos)))
                        for c in classes]
        denominadores = [modelo["totais"][c] + alfa * tamanho for c in classes]
        self._ausente = [math.log(alfa / denominadores[c]) for c in classes]
        self._pesos = {}
        for atributo, contagens in modelo["vocabulario"].items():
            linha = list(self._ausente)
            for classe, contagem in contagens:
                linha[int(classe)] = math.log((contagem + alfa) / denominadores[int(classe)])
            self._pesos[atributo] = linha

    def pontuar(self, texto):
        """Lista de (categoria, confiança) da mais para a menos provável.

        A confiança é a softmax da média do log-verossimilhança por atributo
        conhecido: fica entre 0 e 1 e serve para comparar com o limiar, mas não é
        uma probabilidade calibrada.
        """
        if not re.search(r"[a-z]", normalizar(texto)):
            return []  # só números ou símbolos: o modelo não opina
        conhecidos = [self._pesos[a] for a in extrair_atributos(texto, self.config)
                      if a in self._pesos]
        if not conhecidos:
            return []
        medias = []
        for classe in range(len(self.categorias)):
            soma = self._priori[classe] + sum(linha[classe] for linha in conhecidos)
            medias.append(soma / len(conhecidos))
        maior = max(medias)
        expoentes = [math.exp(m - maior) for m in medias]
        total = sum(expoentes)
        return sorted(((self.categorias[c], expoentes[c] / total)
                       for c in range(len(self.categorias))),
                      key=lambda par: (-par[1], par[0]))

    def classificar(self, texto):
        pontos = self.pontuar(texto)
        return pontos[0] if pontos else (None, 0.0)


def carregar(caminho=None):
    with Path(caminho or CAMINHO_MODELO).open(encoding="utf-8") as arquivo:
        return Classificador(json.load(arquivo))


_cache = {"modelo": None, "tentou": False}
_cache_lock = threading.Lock()


def modelo_padrao():
    """Modelo do repositório, carregado uma vez; None se o arquivo faltar ou for inválido."""
    with _cache_lock:
        if not _cache["tentou"]:
            _cache["tentou"] = True
            try:
                _cache["modelo"] = carregar()
            except (OSError, ValueError, KeyError, TypeError):
                _cache["modelo"] = None
        return _cache["modelo"]


def classificar(texto):
    """(categoria, confiança) pelo modelo treinado; (None, 0.0) sem modelo ou sem atributo conhecido."""
    modelo = modelo_padrao()
    return modelo.classificar(texto) if modelo else (None, 0.0)


def limiar():
    modelo = modelo_padrao()
    return modelo.limiar if modelo else 1.0
