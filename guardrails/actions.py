"""Ações do NeMo Guardrails: delegam para guardas_ia (a mesma lógica usada em produção)."""

import json

from nemoguardrails.actions import action

import guardas_ia


@action(name="reconecta_verificar_entrada")
async def reconecta_verificar_entrada(texto: str = ""):
    veredito = guardas_ia.verificar_entrada(texto)
    return veredito.motivo if veredito.bloqueado else ""


@action(name="reconecta_verificar_saida")
async def reconecta_verificar_saida(texto: str = "", entrada: str = ""):
    """texto: JSON devolvido pela LLM; entrada: o que foi enviado a ela (no resumo, os agregados)."""
    try:
        objeto = json.loads(texto)
    except (TypeError, ValueError):
        return "formato"
    if not isinstance(objeto, dict):
        return "formato"
    formato = "pedido" if "itens" in objeto else "resumo"
    dados = None
    if formato == "resumo":
        try:
            dados = json.loads(entrada)
        except (TypeError, ValueError):
            dados = None
    veredito = guardas_ia.verificar_saida(objeto, formato, dados)
    return veredito.motivo if veredito.bloqueado else ""
