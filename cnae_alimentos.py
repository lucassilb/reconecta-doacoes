"""Critério "relacionado a alimentação" baseado em CNAE (IBGE, subclasses CNAE 2.3).

A decisão usa apenas o código CNAE de cada atividade — nunca o texto da
descrição. O código é normalizado para 7 dígitos e comparado com prefixos de
classe/subclasse oficiais; vale o prefixo mais longo que casar.

Normalização: a BrasilAPI devolve o código como inteiro, então uma subclasse
como "01.55-5/02" chega como o int 155502 — o zero à esquerda é restaurado
com zfill(7). Códigos com pontuação ("47.11-3/01") também são aceitos.

As regras marcadas como False documentam exclusões explícitas; qualquer código
sem prefixo casado também é considerado não alimentar (default de segurança).

Catálogo completo, justificativas e casos-limite: docs/cnae-alimentos.md
"""

import re

_NAO_DIGITO = re.compile(r"\D+")

# prefixo do código CNAE (subclasse com 7 dígitos, sem pontuação)
#   -> (alimentar: bool, categoria ou motivo em pt-BR)
REGRAS_CNAE = {
    # Seção A — agricultura, pecuária, pesca e aquicultura
    "0111": (True, "Lavouras temporárias de alimentos"),        # cereais
    "0112": (False, "Lavouras de fibras (algodão, juta)"),
    "0113": (True, "Lavouras temporárias de alimentos"),        # cana-de-açúcar
    "0114": (False, "Cultivo de fumo"),
    "0115": (True, "Lavouras temporárias de alimentos"),        # soja
    "0116": (True, "Lavouras temporárias de alimentos"),        # amendoim, girassol, oleaginosas
    "0119": (True, "Lavouras temporárias de alimentos"),        # feijão, mandioca, batata, tomate etc.
    "0121": (True, "Horticultura"),
    "0122": (False, "Floricultura e plantas ornamentais"),
    "013": (True, "Lavouras permanentes de alimentos"),         # frutas, café, cacau, especiarias
    "014": (False, "Produção de sementes e mudas certificadas"),
    "015": (True, "Pecuária e produção animal"),
    "0161": (False, "Serviços de apoio à agricultura"),
    "0162": (False, "Serviços de apoio à pecuária"),
    "0163": (True, "Pós-colheita e beneficiamento de produtos agrícolas"),
    "017": (False, "Caça e serviços relacionados"),
    "03": (True, "Pesca e aquicultura"),
    # Seção C — indústria
    "10": (True, "Indústria de alimentos"),
    "1066": (False, "Fabricação de alimentos para animais (ração)"),
    "111": (False, "Fabricação de bebidas alcoólicas"),
    "112": (True, "Indústria de bebidas não alcoólicas"),       # águas, refrigerantes, sucos, chás
    # Seção G — comércio
    "4631": (True, "Atacado de alimentos"),                     # leite e laticínios
    "4632": (True, "Atacado de alimentos"),                     # cereais e farinhas
    "4633": (True, "Atacado de alimentos"),                     # hortifrutigranjeiros
    "4634": (True, "Atacado de alimentos"),                     # carnes e pescados
    "4635": (True, "Atacado de bebidas"),                       # mistura alcoólicas e não alcoólicas
    "4636": (False, "Atacado de fumo"),
    "4637": (True, "Atacado de alimentos"),                     # café, açúcar, óleos, especializados
    "4639": (True, "Atacado de alimentos"),                     # produtos alimentícios em geral
    "4711": (True, "Supermercados e mercearias"),               # hipermercados e supermercados
    "4712": (True, "Supermercados e mercearias"),               # minimercados, mercearias, armazéns
    "4713": (False, "Varejo de mercadorias em geral sem predominância alimentar"),
    "4721": (True, "Varejo especializado de alimentos"),        # padarias, laticínios, doces
    "4722": (True, "Varejo especializado de alimentos"),        # açougues e peixarias
    "4723": (True, "Varejo especializado de alimentos"),        # bebidas
    "4724": (True, "Varejo especializado de alimentos"),        # hortifrutigranjeiros
    "4729601": (False, "Tabacaria"),
    "4729602": (True, "Varejo de alimentos"),                   # lojas de conveniência
    "4729699": (True, "Varejo de alimentos"),                   # outros produtos alimentícios
    # Seção I — alojamento e alimentação
    "56": (True, "Serviços de alimentação"),                    # restaurantes, lanchonetes, catering
    # Seção Q — assistência social (bancos de alimentos, cozinhas comunitárias)
    "8800": (True, "Assistência social sem alojamento"),
    # Seção R/S — associações genéricas não comprovam vínculo alimentar
    "94": (False, "Associações genéricas sem vínculo alimentar comprovável"),
}


def _normalizar_codigo(codigo):
    """Converte o código CNAE para 7 dígitos sem pontuação.

    Aceita int (BrasilAPI remove o zero à esquerda), string "4711301" ou
    formatado "47.11-3/01". Devolve None quando não sobra dígito válido.
    """
    if codigo is None:
        return None
    digitos = _NAO_DIGITO.sub("", str(codigo))
    if not digitos or len(digitos) > 7:
        return None
    return digitos.zfill(7)


def _regra_do_codigo(codigo_normalizado):
    """Prefixo mais longo do catálogo que casa com o código, ou None."""
    melhor = None
    for prefixo in REGRAS_CNAE:
        if codigo_normalizado.startswith(prefixo):
            if melhor is None or len(prefixo) > len(melhor):
                melhor = prefixo
    return REGRAS_CNAE[melhor] if melhor else None


def classificar_atividades(cnaes):
    """Filtra as atividades relacionadas a alimentação/doação de alimentos.

    cnaes: lista de dicts {"codigo": ..., "descricao": ...} — CNAE fiscal
    (principal) mais os secundários, como vêm da BrasilAPI. O código pode ser
    int ou string, com ou sem pontuação.

    Retorna lista de dicts {"codigo": "<7 dígitos>", "descricao": ...,
    "categoria": "<rótulo pt-BR>"}, na mesma ordem da entrada.
    """
    resultado = []
    for item in cnaes or []:
        if not isinstance(item, dict):
            continue
        codigo = _normalizar_codigo(item.get("codigo"))
        if codigo is None:
            continue
        regra = _regra_do_codigo(codigo)
        if regra is None or not regra[0]:
            continue
        resultado.append(
            {
                "codigo": codigo,
                "descricao": item.get("descricao") or "",
                "categoria": regra[1],
            }
        )
    return resultado
