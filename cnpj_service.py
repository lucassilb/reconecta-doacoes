"""Consulta pública de CNPJ e normalização das três fontes disponíveis."""

import re
import threading
import time

import requests


TIMEOUT = 8
CACHE_TTL = 600
_cache = {}
_cache_lock = threading.Lock()


class ConsultaCNPJError(Exception):
    def __init__(self, codigo, mensagem, status):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem
        self.status = status


def validar_cnpj(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{14}|[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}", valor.strip()):
        return None
    digitos = re.sub(r"\D", "", valor)
    if len(set(digitos)) == 1:
        return None
    for tamanho, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                           (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(n) * peso for n, peso in zip(digitos[:tamanho], pesos)) % 11
        esperado = 0 if resto < 2 else 11 - resto
        if int(digitos[tamanho]) != esperado:
            return None
    return digitos


def formatar_cnpj(digitos):
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def _codigo(valor):
    digitos = re.sub(r"\D", "", str(valor or ""))
    return digitos.zfill(7) if digitos else ""


def _atividade(codigo, descricao=""):
    codigo = _codigo(codigo)
    return {"codigo": codigo, "descricao": str(descricao or "")} if codigo else None


def _situacao(valor, descricao=None):
    if str(valor).strip() in ("2", "02"):
        return "ATIVA"
    texto = descricao or valor or "DESCONHECIDA"
    return str(texto).strip().upper()


def _telefone(valor):
    digitos = re.sub(r"\D", "", str(valor or ""))
    if len(digitos) in (10, 11):
        parte = digitos[2:]
        return f"({digitos[:2]}) {parte[:-4]}-{parte[-4:]}"
    return str(valor).strip() if valor else None


def _endereco(dados):
    return {chave: str(dados.get(chave) or "").strip() for chave in
            ("logradouro", "numero", "complemento", "bairro", "municipio", "uf", "cep")}


def _normalizar_brasilapi(dados):
    principal = _atividade(dados.get("cnae_fiscal"), dados.get("cnae_fiscal_descricao"))
    secundarios = [_atividade(item.get("codigo"), item.get("descricao"))
                   for item in dados.get("cnaes_secundarios") or [] if isinstance(item, dict)]
    return {
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": dados.get("nome_fantasia") or "",
        "situacao": _situacao(dados.get("situacao_cadastral"), dados.get("descricao_situacao_cadastral")),
        "cnae_principal": principal,
        "cnaes": [item for item in [principal, *secundarios] if item],
        "endereco": _endereco(dados),
        "email": dados.get("email") or None,
        "telefone": _telefone(dados.get("ddd_telefone_1")),
    }


def _normalizar_opencnpj(dados):
    catalogo = {_codigo(item.get("codigo")): item.get("descricao") for item in dados.get("cnaes") or []
                if isinstance(item, dict)}
    principal_raw = dados.get("cnae_principal")
    if isinstance(principal_raw, dict):
        principal = _atividade(principal_raw.get("codigo"), principal_raw.get("descricao"))
    else:
        principal = _atividade(principal_raw, catalogo.get(_codigo(principal_raw)))
    secundarios = []
    for item in dados.get("cnaes_secundarios") or []:
        codigo = item.get("codigo") if isinstance(item, dict) else item
        descricao = item.get("descricao") if isinstance(item, dict) else catalogo.get(_codigo(codigo))
        atividade = _atividade(codigo, descricao)
        if atividade:
            secundarios.append(atividade)
    return {
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": dados.get("nome_fantasia") or "",
        "situacao": _situacao(dados.get("situacao_cadastral")),
        "cnae_principal": principal,
        "cnaes": [item for item in [principal, *secundarios] if item],
        "endereco": _endereco(dados),
        "email": dados.get("email") or None,
        "telefone": _telefone(dados.get("telefone") or dados.get("ddd_telefone_1")),
    }


def _normalizar_cnpjws(dados):
    estabelecimento = dados.get("estabelecimento") or {}
    principal_raw = estabelecimento.get("atividade_principal") or {}
    principal = _atividade(principal_raw.get("id") or principal_raw.get("codigo"), principal_raw.get("descricao"))
    secundarios = [_atividade(item.get("id") or item.get("codigo"), item.get("descricao"))
                   for item in estabelecimento.get("atividades_secundarias") or [] if isinstance(item, dict)]
    endereco = _endereco(estabelecimento)
    if not endereco["municipio"]:
        municipio = estabelecimento.get("cidade") or {}
        endereco["municipio"] = municipio.get("nome", "") if isinstance(municipio, dict) else str(municipio)
    if not endereco["uf"]:
        estado = estabelecimento.get("estado") or {}
        endereco["uf"] = estado.get("sigla", "") if isinstance(estado, dict) else str(estado)
    return {
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": estabelecimento.get("nome_fantasia") or "",
        "situacao": _situacao(estabelecimento.get("situacao_cadastral")),
        "cnae_principal": principal,
        "cnaes": [item for item in [principal, *secundarios] if item],
        "endereco": endereco,
        "email": estabelecimento.get("email") or None,
        "telefone": _telefone(str(estabelecimento.get("ddd1") or "") + str(estabelecimento.get("telefone1") or "")),
    }


FONTES = (
    ("brasilapi", "https://brasilapi.com.br/api/cnpj/v1/{}", _normalizar_brasilapi),
    ("opencnpj", "https://api.opencnpj.org/{}", _normalizar_opencnpj),
    ("cnpjws", "https://publica.cnpj.ws/cnpj/{}", _normalizar_cnpjws),
)


def consultar_cnpj(valor):
    digitos = validar_cnpj(valor)
    if not digitos:
        raise ConsultaCNPJError("CNPJ_INVALIDO", "Informe um CNPJ válido.", 400)

    with _cache_lock:
        entrada = _cache.get(digitos)
        if entrada and entrada[0] > time.monotonic():
            dados, fonte = entrada[1:]
        else:
            dados = fonte = None

    if dados is None:
        for nome, url, normalizar in FONTES:
            try:
                resposta = requests.get(url.format(digitos), timeout=TIMEOUT)
                if resposta.status_code == 404:
                    raise ConsultaCNPJError("CNPJ_NAO_ENCONTRADO", "CNPJ não encontrado na Receita Federal.", 404)
                resposta.raise_for_status()
                candidato = normalizar(resposta.json())
                if not candidato["razao_social"] or not candidato["cnae_principal"]:
                    continue
            except ConsultaCNPJError:
                raise
            except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
                continue
            dados, fonte = candidato, nome
            with _cache_lock:
                _cache[digitos] = (time.monotonic() + CACHE_TTL, dados, fonte)
            break
        if dados is None:
            raise ConsultaCNPJError("CONSULTA_INDISPONIVEL", "Consulta de CNPJ indisponível no momento. Tente novamente.", 503)

    try:
        from cnae_alimentos import classificar_atividades
    except ImportError as erro:
        raise ConsultaCNPJError("CONSULTA_INDISPONIVEL", "Classificação de atividades indisponível no momento.", 503) from erro
    atividades = classificar_atividades(dados["cnaes"])
    situacao = dados["situacao"]
    return {
        "cnpj": digitos,
        "cnpj_formatado": formatar_cnpj(digitos),
        "razao_social": dados["razao_social"],
        "nome_fantasia": dados["nome_fantasia"],
        "situacao": situacao,
        "ativo": situacao == "ATIVA",
        "cnae_principal": dados["cnae_principal"],
        "atividades_alimentares": atividades,
        "relacionado_alimentacao": bool(atividades),
        "endereco": dados["endereco"],
        "email": dados["email"],
        "telefone": dados["telefone"],
        "fonte": fonte,
    }
