"""IA de conexão: cruza o que o doador tem com os pedidos abertos.

`casar` é pura (sem rede, sem banco): recebe itens no formato do pipeline de
interpretação (`llm_service.interpretar_pedido`) e pedidos no formato de
`Publico.serializar_doacao`, e devolve até 5 sugestões ordenadas com pontuação
explicável — a pessoa decide; a função só recomenda.
"""

import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

from fuso import agora_brasilia

MAX_SUGESTOES = 5


def _normalizar(valor):
    texto = "".join(c for c in unicodedata.normalize("NFKD", str(valor or "").lower())
                    if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip()


def _similaridade(a, b):
    return SequenceMatcher(None, _normalizar(a), _normalizar(b)).ratio()


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
    if isinstance(faltam, (int, float)) and faltam > 0:
        return float(faltam)
    meta = item_pedido.get("quantidade")
    recebido = item_pedido.get("recebido", 0)
    try:
        resta = float(meta) - float(recebido)
    except (TypeError, ValueError):
        return None
    return resta if resta > 0 else None


def _avaliar(item_doador, item_pedido, pedido, uf):
    """Pontua um par (item do doador × item do pedido) ou devolve None."""
    mesma_categoria = item_pedido.get("categoria") == item_doador.get("categoria")
    sim = _similaridade(item_doador.get("nome"), item_pedido.get("nome"))
    if not mesma_categoria and sim < 0.55:
        return None

    pontos = 0.0
    motivos = []
    if mesma_categoria:
        pontos += 35
        motivos.append(f"pede {item_pedido['categoria']}")
    pontos += 25 * sim
    if sim >= 0.55:
        motivos.append(f"item parecido com '{item_pedido.get('nome')}'")

    faltam = _faltam(item_pedido)
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
        melhor = None
        for item_doador in itens or []:
            for item_pedido in pedido.get("itens") or []:
                avaliado = _avaliar(item_doador, item_pedido, pedido, uf)
                if avaliado and (melhor is None or avaliado[0] > melhor[0]):
                    melhor = avaliado
        if melhor is None:
            continue
        pontos, motivos, sugerida, item_pedido = melhor
        sugestao = {
            "pedido_id": pedido.get("id"),
            "organizacao": (pedido.get("empresa") or {}).get("nome"),
            "municipio_uf": (pedido.get("empresa") or {}).get("municipio_uf"),
            "pontuacao": int(round(min(pontos, 100))),
            "motivos": motivos,
            "item_id": item_pedido.get("id"),
            "quantidade_sugerida": sugerida,
        }
        if pedido.get("estabelecimento_id") is not None:
            sugestao["estabelecimento_id"] = pedido["estabelecimento_id"]
        sugestoes.append(sugestao)
    sugestoes.sort(key=lambda s: (-s["pontuacao"], s["pedido_id"] or 0))
    return sugestoes[:MAX_SUGESTOES]
