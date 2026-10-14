"""IA de conexão: cruza o que o doador tem com os pedidos abertos.

`casar` é pura (sem rede, sem banco): recebe itens no formato do pipeline de
interpretação (`llm_service.interpretar_pedido`) e pedidos no formato de
`Publico.serializar_doacao`, e devolve até 5 sugestões ordenadas com pontuação
explicável — a pessoa decide; a função só recomenda.

Distância: quando o chamador anota `distancia_km` (e `distancia_aproximada`) em cada
pedido — ver `geo.py` —, a proximidade substitui a regra de mesma UF na pontuação
e vira motivo ("a 3,4 km"). Sem anotação, vale a regra de UF de antes.
"""

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from fuso import agora_brasilia

MAX_SUGESTOES = 5
# (até km, pontos): perto pesa mais que a mesma UF (10); longe não ganha nada.
FAIXAS_DISTANCIA = ((5, 15), (15, 12), (50, 9), (150, 5), (400, 2))
_PALAVRAS_DE_LIGACAO = {"de", "da", "do", "das", "dos", "e", "em", "com", "sem"}
_TIPOS_GENERICOS = {"pao", "bolo", "suco", "agua", "sopa", "marmita", "carne",
                    "queijo", "leite", "oleo", "biscoito", "file", "salada"}


def _normalizar(valor):
    texto = "".join(c for c in unicodedata.normalize("NFKD", str(valor or "").lower())
                    if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _similaridade(a, b):
    return SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio()


def _termos_nome(nome):
    """Palavras do nome em forma simples, inclusive plurais frequentes."""
    termos = set()
    for termo in re.findall(r"[a-z]+", _normalizar(nome)):
        if termo in _PALAVRAS_DE_LIGACAO:
            continue
        if termo.endswith(("aes", "oes")) and len(termo) >= 4:
            termo = termo[:-3] + "ao"
        elif termo.endswith("ais") and len(termo) > 4:
            termo = termo[:-3] + "al"
        elif termo.endswith("s") and len(termo) > 3:
            termo = termo[:-1]
        termos.add(termo)
    return termos


def _termos_alimento(nome):
    """Termos úteis para distinguir alimentos da mesma categoria ampla."""
    return _termos_nome(nome) - _TIPOS_GENERICOS


def _restricoes(nome, palavra):
    termos = _normalizar(nome).split()
    return {termos[i + 1] for i, termo in enumerate(termos[:-1]) if termo == palavra}


def _uf(texto):
    """'Bairro, Cidade/UF' → 'UF' (duas letras), senão None."""
    if not isinstance(texto, str):
        return None
    achado = re.search(r"/\s*([A-Za-z]{2})\s*$", texto.strip())
    return achado.group(1).upper() if achado else None


def _dias_ate(iso):
    """Dias até o prazo (float); None se a data não for legível."""
    if not isinstance(iso, str) or not iso:
        return None
    try:
        limite = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if limite.tzinfo is None:
        return (limite - agora_brasilia().replace(tzinfo=None)).total_seconds() / 86400
    return (limite - agora_brasilia()).total_seconds() / 86400


def _faltam(item_pedido):
    """Quanto falta para a meta do item; None se o pedido não informar."""
    faltam = item_pedido.get("faltam")
    if isinstance(faltam, (int, float)):
        return float(faltam) if faltam > 0 else None
    meta = item_pedido.get("quantidade")
    recebido = item_pedido.get("recebido", 0)
    try:
        resta = float(meta) - float(recebido)
    except (TypeError, ValueError):
        return None
    return resta if resta > 0 else None


def texto_distancia(km, aproximada=False):
    """'a 3,4 km', 'a cerca de 12 km' (centróide do município) ou 'na mesma cidade'."""
    if aproximada and km < 1:
        return "na mesma cidade"
    if km < 1:
        return "a menos de 1 km"
    valor = f"{km:.1f}".replace(".", ",") if km < 10 else f"{round(km):d}"
    return f"a {'cerca de ' if aproximada else ''}{valor} km"


def _avaliar(item_doador, item_pedido, pedido, uf):
    """Pontua um par (item do doador × item do pedido) ou devolve None."""
    mesma_categoria = item_pedido.get("categoria") == item_doador.get("categoria")
    sim = _similaridade(item_doador.get("nome"), item_pedido.get("nome"))
    nome_oferta = item_doador.get("nome")
    nome_pedido = item_pedido.get("nome")
    termos_nome_oferta = _termos_nome(nome_oferta)
    termos_nome_pedido = _termos_nome(nome_pedido)
    if not termos_nome_oferta or not termos_nome_pedido:
        return None
    termos_oferta = _termos_alimento(nome_oferta)
    termos_pedido = _termos_alimento(nome_pedido)
    termos_comuns = termos_oferta & termos_pedido
    if not termos_comuns and sim < 0.82 and termos_nome_oferta != termos_nome_pedido:
        return None
    if termos_oferta and termos_pedido and not (termos_oferta <= termos_pedido or
                                               termos_pedido <= termos_oferta):
        return None
    if _restricoes(nome_pedido, "sem") - _restricoes(nome_oferta, "sem"):
        return None
    if _restricoes(nome_oferta, "sem") & _restricoes(nome_pedido, "com"):
        return None
    if not mesma_categoria and sim < 0.72:
        return None
    unidade_doador = item_doador.get("unidade_medida")
    unidade_pedido = item_pedido.get("unidade_medida")
    if unidade_doador and unidade_pedido and unidade_doador != unidade_pedido:
        return None
    faltam = _faltam(item_pedido)
    if faltam is None:
        return None

    pontos = 0.0
    motivos = []
    if mesma_categoria:
        pontos += 35
        motivos.append(f"pede {item_pedido['categoria']}")
    pontos += 25 * sim
    if sim >= 0.55:
        motivos.append(f"item parecido com '{item_pedido.get('nome')}'")

    quantidade = item_doador.get("quantidade")
    unidade_igual = (not item_doador.get("unidade_medida") or
                     item_doador.get("unidade_medida") == item_pedido.get("unidade_medida"))
    if faltam:
        motivos.append(f"faltam {faltam:g} de {float(item_pedido.get('quantidade', faltam)):g} "
                       f"{item_pedido.get('nome')}")
        if unidade_igual and isinstance(quantidade, (int, float)) and quantidade > 0:
            pontos += 15 * min(quantidade / faltam, 1)
        else:
            pontos += 8

    dias = _dias_ate(pedido.get("receber_ate"))
    if dias is not None:
        if dias <= 3:
            pontos += 10
            motivos.append("prazo em até 3 dias" if dias > 1 else "prazo hoje ou amanhã")
        elif dias <= 7:
            pontos += 5
            motivos.append(f"prazo em {int(round(dias))} dias")

    km = pedido.get("distancia_km")
    if isinstance(km, (int, float)) and km >= 0:
        pontos += next((p for limite, p in FAIXAS_DISTANCIA if km <= limite), 0)
        motivos.append(texto_distancia(km, pedido.get("distancia_aproximada")))
    else:
        uf_pedido = _uf((pedido.get("empresa") or {}).get("municipio_uf"))
        if uf and uf_pedido and uf == uf_pedido:
            pontos += 10
            motivos.append("mesma UF")

    sugerida = quantidade
    if faltam and isinstance(quantidade, (int, float)):
        sugerida = min(quantidade, faltam)
    return pontos, motivos, sugerida, item_pedido


def casar(itens, pedidos, uf=None):
    """Devolve até 5 sugestões {"pedido_id","organizacao","municipio_uf","pontuacao",
    "motivos","item_id","quantidade_sugerida"} ordenadas por pontuação."""
    sugestoes = []
    for pedido in pedidos or []:
        candidatos = []
        for indice_doador, item_doador in enumerate(itens or []):
            for indice_pedido, item_pedido in enumerate(pedido.get("itens") or []):
                avaliado = _avaliar(item_doador, item_pedido, pedido, uf)
                if avaliado:
                    candidatos.append((avaliado, indice_doador, indice_pedido))
        if not candidatos:
            continue
        candidatos.sort(key=lambda c: -c[0][0])
        usados_doador, usados_pedido = set(), set()
        for _, indice_doador, indice_pedido in candidatos:
            if indice_doador not in usados_doador and indice_pedido not in usados_pedido:
                usados_doador.add(indice_doador)
                usados_pedido.add(indice_pedido)
        pontos, motivos, sugerida, item_pedido = candidatos[0][0]
        if len(usados_doador) > 1:
            pontos += 12 * (len(usados_doador) - 1)
            motivos = [*motivos, f"atende {len(usados_doador)} itens"]
        sugestao = {
            "pedido_id": pedido.get("id"),
            "organizacao": (pedido.get("empresa") or {}).get("nome"),
            "municipio_uf": (pedido.get("empresa") or {}).get("municipio_uf"),
            "pontuacao": int(round(min(pontos, 100))),
            "motivos": motivos,
            "item_id": item_pedido.get("id"),
            "quantidade_sugerida": sugerida,
        }
        if isinstance(pedido.get("distancia_km"), (int, float)):
            sugestao["distancia_km"] = round(float(pedido["distancia_km"]), 1)
            sugestao["distancia"] = texto_distancia(pedido["distancia_km"],
                                                    pedido.get("distancia_aproximada"))
        if pedido.get("estabelecimento_id") is not None:
            sugestao["estabelecimento_id"] = pedido["estabelecimento_id"]
        sugestoes.append(sugestao)
    sugestoes.sort(key=lambda s: (-s["pontuacao"], s["pedido_id"] or 0))
    return sugestoes[:MAX_SUGESTOES]
