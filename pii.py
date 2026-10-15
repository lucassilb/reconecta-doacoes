"""Padrões de dados pessoais usados pelo log mínimo e pelas guardas da IA.

`mascarar` troca documento, contato, IP, segredo e parâmetros sensíveis de URL por
marcadores; `encontrar` diz quais tipos aparecem num texto (guarda de saída da IA).
Nome, endereço e texto livre não têm formato fixo: esses ficam fora dos logs na origem.
"""

import ipaddress
import re

_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}(?:/|%2F)?\d{4}-?\d{2}(?!\d)", re.IGNORECASE)
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TELEFONE = re.compile(r"(?<![\d.])(?:\+?55[ -]?)?\(?\d{2}\)?[ -]?9?\d{4}[ -]?\d{4}(?![\d.])")
_CEP = re.compile(r"(?<![\d.])\d{5}-\d{3}(?!\d)")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.\d{1,3}(?![\d.])")
# ao menos 4 grupos: "10:20:30" (hora) não é IPv6
_IPV6 = re.compile(r"(?<![\w:])((?:[0-9a-f]{1,4}:){2}[0-9a-f]{1,4})(?::[0-9a-f]{0,4}){1,5}(?![\w:])",
                   re.IGNORECASE)
# cabeçalhos inteiros (Authorization: Bearer x, Cookie: a=1; b=2) e pares chave=valor
_CABECALHO = re.compile(r"(?i)\b((?:proxy-)?authorization|cookie|set-cookie|x-admin-token)(\s*:\s*)[^\r\n]+")
_SEGREDO = re.compile(r"(?i)\b(bearer\s+|(?:session|token|senha|password|api[_-]?key|secret)\s*[:=]\s*\"?)"
                      r"[^\s\",;&]+")
_CHAVE_GROQ = re.compile(r"\bgsk_[A-Za-z0-9]{12,}")
_QUERY = re.compile(r"(?i)([?&](?:cep|email|e-mail|cpf|cnpj|telefone|busca|q|nome|endereco|"
                    r"token|senha|identificador)=)[^&\s\"]*")

_ORDEM = (
    ("chave", _CHAVE_GROQ, "[chave]"),
    ("segredo", _CABECALHO, r"\1\2[oculto]"),
    ("segredo", _SEGREDO, r"\1[oculto]"),
    ("parametro", _QUERY, r"\1[oculto]"),
    ("email", _EMAIL, "[email]"),
    ("cnpj", _CNPJ, "[cnpj]"),
    ("cpf", _CPF, "[cpf]"),
    ("telefone", _TELEFONE, "[telefone]"),
    ("cep", _CEP, "[cep]"),
    ("ip", _IPV4, r"\1.\2.\3.0"),
    ("ip", _IPV6, r"\1::"),
)


def mascarar(texto):
    """Devolve o texto com os padrões pessoais e segredos trocados por marcadores."""
    if not texto:
        return texto
    for _tipo, padrao, troca in _ORDEM:
        texto = padrao.sub(troca, texto)
    return texto


def encontrar(texto):
    """Tipos de dado pessoal presentes no texto (vazio quando não há nenhum)."""
    if not texto:
        return set()
    achados = set()
    for tipo, padrao, _troca in _ORDEM:
        if padrao.search(texto):
            achados.add(tipo)
            texto = padrao.sub(" ", texto)
    return achados


def ip_reduzido(ip):
    """IPv4 sem o último octeto (/24) e IPv6 só com os 3 primeiros grupos (/48)."""
    if not ip:
        return None
    ip = str(ip).strip()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    if ":" in ip:
        grupos = ip.split(":")
        return ":".join(grupos[:3]) + "::" if len(grupos) > 3 else ip
    partes = ip.split(".")
    return ".".join(partes[:3] + ["0"]) if len(partes) == 4 else None
