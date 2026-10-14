"""Predição de descarte com artefato JSON; inferência sem bibliotecas de treino.

Os rótulos do treino são simulados. Probabilidades não são taxas observadas em
operações reais e servem somente para ordenar ofertas para revisão humana.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

MODELO = Path(__file__).resolve().parent / "modelo" / "risco_descarte.json"
CATEGORIAS = ("Hortifrúti", "Padaria", "Laticínios", "Carnes e peixes",
              "Grãos e cereais", "Refeições prontas", "Bebidas não alcoólicas", "Outros")
PERECIVEIS = set(CATEGORIAS[:4]) | {"Refeições prontas"}
ARMAZENAMENTOS = ("ambiente", "refrigerado", "congelado", "nao_informado")
ATRIBUTOS = (
    "prazo_inverso", "dias_validade", "kg_log", "perecivel",
    "temperatura_c", "temperatura_ausente", "temperatura_excesso",
    "distancia_log", "distancia_ausente", "fim_semana", "hora_noite",
    *("armazenamento_" + a for a in ARMAZENAMENTOS),
    *("categoria_" + c for c in CATEGORIAS),
)


def _numero(valor, nome, minimo, maximo, *, opcional=False):
    if valor in (None, "") and opcional:
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{nome}: informe um número válido.")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{nome}: informe um número válido.") from erro
    if not math.isfinite(numero) or not minimo <= numero <= maximo:
        raise ValueError(f"{nome}: valor fora do intervalo permitido.")
    return numero


def validar_lote(lote):
    if not isinstance(lote, dict):
        raise ValueError("Informe um lote em formato JSON.")
    categoria = lote.get("categoria")
    if categoria not in CATEGORIAS:
        raise ValueError("categoria: selecione uma categoria válida.")
    armazenamento = lote.get("armazenamento", "nao_informado")
    if armazenamento not in ARMAZENAMENTOS:
        raise ValueError("armazenamento: use ambiente, refrigerado, congelado ou nao_informado.")
    perecivel = lote.get("perecivel", categoria in PERECIVEIS)
    if not isinstance(perecivel, bool):
        raise ValueError("perecivel: informe verdadeiro ou falso.")
    dias = _numero(lote.get("dias_validade"), "dias_validade", 0, 365)
    kg = _numero(lote.get("quantidade_kg"), "quantidade_kg", 0.01, 100000)
    temperatura = _numero(lote.get("temperatura_c"), "temperatura_c", -35, 60,
                          opcional=True)
    distancia = _numero(lote.get("distancia_ong_km"), "distancia_ong_km", 0, 2000,
                        opcional=True)
    dia = _numero(lote.get("dia_semana", 2), "dia_semana", 0, 6)
    hora = _numero(lote.get("hora_publicacao", 12), "hora_publicacao", 0, 23)
    if not dia.is_integer() or not hora.is_integer():
        raise ValueError("dia_semana e hora_publicacao devem ser inteiros.")
    uf = lote.get("uf") or "NA"
    if not isinstance(uf, str) or len(uf) != 2 or not uf.isalpha():
        raise ValueError("uf: informe duas letras.")
    return {"categoria": categoria, "perecivel": perecivel,
            "dias_validade": dias, "quantidade_kg": kg,
            "temperatura_c": temperatura, "armazenamento": armazenamento,
            "dia_semana": int(dia), "hora_publicacao": int(hora),
            "uf": uf.upper(), "distancia_ong_km": distancia}


def vetor(lote):
    lote = validar_lote(lote)
    dias = lote["dias_validade"]
    temperatura = lote["temperatura_c"]
    temperatura_imputada = temperatura if temperatura is not None else {
        "ambiente": 24, "refrigerado": 4, "congelado": -18,
        "nao_informado": 16}[lote["armazenamento"]]
    distancia = lote["distancia_ong_km"]
    valores = [1 / (dias + 1), min(dias, 30), math.log1p(lote["quantidade_kg"]),
               int(lote["perecivel"]), temperatura_imputada,
               int(temperatura is None),
               max(0, temperatura_imputada - 8) if lote["perecivel"] else 0,
               math.log1p(distancia or 0), int(distancia is None),
               int(lote["dia_semana"] >= 5),
               int(lote["hora_publicacao"] < 6 or lote["hora_publicacao"] >= 20)]
    valores.extend(int(lote["armazenamento"] == nome) for nome in ARMAZENAMENTOS)
    valores.extend(int(lote["categoria"] == nome) for nome in CATEGORIAS)
    return valores


def carregar(caminho=MODELO):
    modelo = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if modelo.get("versao") != 1 or modelo.get("atributos") != list(ATRIBUTOS):
        raise ValueError("Modelo de risco incompatível com o código.")
    return modelo


@lru_cache(maxsize=1)
def _modelo_padrao():
    return carregar()


def _probabilidade(valores, modelo):
    if modelo["tipo"] == "logistica":
        escore = modelo["intercepto"] + sum(
            peso * (valor - media) / escala
            for peso, valor, media, escala in zip(
                modelo["coeficientes"], valores, modelo["media"], modelo["escala"]))
        return 1 / (1 + math.exp(-max(-700, min(700, escore))))
    if modelo["tipo"] == "floresta":
        soma = 0.0
        for arvore in modelo["arvores"]:
            no = 0
            while arvore["esquerda"][no] >= 0:
                atributo = arvore["atributo"][no]
                no = (arvore["esquerda"][no] if valores[atributo] <= arvore["limiar"][no]
                      else arvore["direita"][no])
            soma += arvore["probabilidade"][no]
        return soma / len(modelo["arvores"])
    raise ValueError("Tipo de modelo de risco desconhecido.")


def prever(lote, modelo=None):
    """Probabilidade, nível e sinais observáveis; motivos não são causalidade."""
    dados = validar_lote(lote)
    probabilidade = _probabilidade(vetor(dados), modelo or _modelo_padrao())
    nivel = "alto" if probabilidade >= 0.65 else "medio" if probabilidade >= 0.35 else "baixo"
    motivos = []
    if dados["dias_validade"] <= 2:
        motivos.append("Validade em até dois dias")
    if dados["perecivel"] and dados["armazenamento"] == "ambiente":
        motivos.append("Alimento perecível em temperatura ambiente declarada")
    if dados["temperatura_c"] is None:
        motivos.append("Temperatura não informada")
    if dados["distancia_ong_km"] is None:
        motivos.append("Distância até ONG não informada")
    elif dados["distancia_ong_km"] >= 30:
        motivos.append("ONG informada a 30 km ou mais")
    if dados["dia_semana"] >= 5:
        motivos.append("Publicação no fim de semana")
    return {"probabilidade": round(probabilidade, 4), "nivel": nivel,
            "motivos": motivos[:4], "base": "simulacao",
            "aviso": "Estimativa treinada com dados simulados; confirme a prioridade na operação."}
