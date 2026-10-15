"""Guardas de entrada e saída da LLM (Groq Free / Ollama) do assistente e do resumo.

As regras ficam em guardrails/rails.co (Colang do NVIDIA NeMo Guardrails): os fluxos
de entrada e saída chamam as ações `reconecta_verificar_entrada` e
`reconecta_verificar_saida`, implementadas AQUI. Em CI e testes o NeMo carrega essa
configuração (guardrails/config.yml) e executa os fluxos; em produção (Render free,
512 MB) o NeMo não é instalado e o servidor chama as mesmas ações direto, lendo as
mensagens de recusa do próprio rails.co. Detalhes e números em docs/seguranca.md.

Tudo é local e determinístico: nenhuma rail chama a LLM (não gasta cota do Groq Free).
"""

import csv
import json
import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pii

PASTA_CONFIG = Path(__file__).resolve().parent / "guardrails"
_log = logging.getLogger("reconecta.guardas")


@dataclass(frozen=True)
class Veredito:
    bloqueado: bool
    motivo: str | None = None  # injecao | fora_do_tema | duvida | dado_pessoal | link | vazamento | numero
    mensagem: str | None = None


_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "@": "a", "$": "s", "5": "s", "7": "t"})
_INVISIVEIS = re.compile(r"[\u200b-\u200f\u2060\ufeff\u00ad]")


def _simples(texto, leet=False):
    """Minúsculas, sem acento e sem caracteres invisíveis; com leet=True, '1gn0r3' -> 'ignore'."""
    texto = _INVISIVEIS.sub("", unicodedata.normalize("NFKC", str(texto)))
    texto = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                    if not unicodedata.combining(c))
    if leet:
        texto = texto.translate(_LEET)
    return " ".join(texto.split())


def _soletrados(texto):
    """Trechos soletrados ('i g n o r e  a s  r e g r a s') juntados: 'ignoreasregras'."""
    return [m.group(0).replace(" ", "") for m in re.finditer(r"\b(?:\w ){4,}\w\b", texto)]


# no texto soletrado não há espaços: procura verbo e alvo colados
_COMPACTO = re.compile(r"(?:ignor|desconsider|esquec|desprez|disregard|forget|override|bypass)\w{0,24}?"
                       r"(?:instruc|regra|orientac|comando|prompt|restric|instruction|rule|system)|"
                       r"jailbreak|systemprompt|promptdosistema|mododesenvolvedor|developermode")


# --- injeção de prompt e jailbreak (português e inglês), sobre o texto simplificado ---
# formas de ordem ("esqueci de dizer..." não conta)
_VERBO_IGNORAR = (r"(?:ignor[ae]m?|ignorar|desconsider[ae]m?|desconsiderar|esquec[ae]m?|esquecer|"
                  r"desprez[ae]m?|descart[ae]m?|pul[ae]m?|anul[ae]m?|sobrescrev[ae]m?|substitu[ai]m?|"
                  r"desobedec[ae]m?|nao (?:siga|obedeca|respeite)|disregard|forget|override|bypass|skip)")
_ALVO_REGRAS = (r"(?:instruc\w*|regras?|orientac\w*|comandos?|diretrizes?|prompts?|restric\w*|"
                r"limitac\w*|politicas?|filtros?|configurac\w*|mensagens? anterio\w*|"
                r"instructions?|rules?|guidelines?|system)")
_INJECAO = [re.compile(p) for p in (
    r"\b" + _VERBO_IGNORAR + r"\b.{0,40}?\b" + _ALVO_REGRAS,
    r"\b(?:a partir de agora|de agora em diante|daqui pra frente|from now on)\b.{0,30}\b(?:responda|responde|"
    r"aja|seja|finja|obedeca|ignore|fale|respond|act|you are|you will)\b",
    r"\b(?:voce|vc) (?:agora (?:e|sera|vai ser|passa a ser)|(?:e|sera|vai ser|passa a ser) (?:um|uma|o|a) "
    r"(?:nov[oa] )?(?:assistente|ia|bot|chatbot|modelo|hacker|personagem|especialista|programador|ai|gpt|dan))\b",
    r"\b(?:finja|fingir|simule|interprete o papel|faca de conta|aja como|atue como|comporte-se como|"
    r"you are now|act as|pretend|roleplay)\b",
    r"\b(?:modo|mode) (?:desenvolvedor|developer|dev|deus|god|admin|root|irrestrito|sem censura|dan)\b",
    r"\b(?:jailbreak|do anything now|dan mode|sem (?:restric\w*|filtros?|censura|limites)|"
    r"without (?:restrictions|filters|limits))\b",
    r"\b(?:mostre|revele|imprima|repita|diga|exiba|vaze|copie|liste|escreva|qual (?:e|eh)|print|reveal|show|repeat)\b"
    r".{0,30}\b(?:prompt|instruc\w* (?:do sistema|iniciai?s?|ocultas?|originai?s?|internas?)|system message|"
    r"mensagem do sistema|configurac\w* (?:do sistema|interna))",
    r"\b(?:system prompt|prompt do sistema|prompt de sistema|instruc\w* do sistema|mensagem do sistema)\b",
    r"\b(?:novas? instruc\w*|nova regra|new instructions?|updated instructions?)\b",
    r"\b(?:responda|retorne|devolva|escreva|gere|output|return)\b.{0,30}\b(?:apenas|somente|exatamente|only|exactly)\b"
    r".{0,30}\b(?:json|isto|isso|o seguinte|seguinte texto|this|the following)\b",
    r"\b(?:base64|rot13|hexadecimal|decodifiqu\w*|decode)\b",
    r"\b(?:chave|token|senha|credencia\w*|api key|segredo)\b.{0,30}\b(?:api|groq|servidor|sistema|admin|ambiente|env)\b",
    r"(?:\bvariave\w* de ambiente|\benvironment variables?|\.env\b|\bos\.environ|\bgroq_api_key)",
)]
# marcadores de papel/turno colados no texto (testados no texto original, sem simplificar)
_MARCADORES = re.compile(
    r"(?im)^[^\S\n]*(?:system|sistema|assistant|assistente|developer|user)[^\S\n]*:|"
    r"<\|?(?:im_start|im_end|system|endoftext)\|?>|\[/?(?:INST|SYS)\]|<</?SYS>>|</?s>|"
    r"```\s{0,64}(?:system|json)|###\s{0,64}(?:instru|system|sistema)")
# JSON pronto com as chaves do esquema: tentativa de ditar a saída do modelo
_CHAVES = r"(?:itens|nome|categoria|quantidade|unidade_medida|receber_ate|observacoes|resumo|recomendacoes)"
_JSON_ESQUEMA = re.compile(r"[{,]\s*[\"']?" + _CHAVES + r"[\"']?\s*:|[\"']" + _CHAVES + r"[\"']\s*:")

# --- tema: alimentos e doação ---
_ALIMENTOS = (
    "alimento", "alimentos", "comida", "comidas", "refeicao", "refeicoes", "marmita", "marmitas",
    "marmitex", "lanche", "lanches", "sopa", "sopas", "prato", "pratos", "almoco", "jantar",
    "cafe", "leite", "queijo", "queijos", "iogurte", "iogurtes", "manteiga", "requeijao", "nata",
    "pao", "paes", "bolo", "bolos", "biscoito", "biscoitos", "bolacha", "bolachas", "farinha",
    "rosca", "roscas", "torrada", "torradas", "salgado", "salgados", "doce", "doces", "sonho",
    "fruta", "frutas", "banana", "bananas", "maca", "macas", "laranja", "laranjas", "tomate",
    "tomates", "batata", "batatas", "cebola", "cebolas", "verdura", "verduras", "alface",
    "legume", "legumes", "cenoura", "cenouras", "abobora", "chuchu", "mandioca", "aipim",
    "couve", "repolho", "pepino", "pimentao", "mamao", "melancia", "melao", "uva", "uvas",
    "abacaxi", "manga", "mangas", "limao", "limoes", "goiaba", "morango", "morangos", "hortifruti",
    "carne", "carnes", "frango", "frangos", "peixe", "peixes", "ovo", "ovos", "linguica",
    "salsicha", "presunto", "mortadela", "bife", "file", "sardinha", "atum",
    "arroz", "feijao", "lentilha", "grao", "graos", "cereal", "cereais", "aveia", "macarrao",
    "milho", "fuba", "acucar", "sal", "oleo", "azeite", "cha", "achocolatado",
    "agua", "suco", "sucos", "refrigerante", "refrigerantes", "bebida", "bebidas", "polpa",
    "enlatado", "enlatados", "conserva", "conservas", "molho", "massa", "massas", "pizza",
    "chocolate", "bombom", "bombons", "granola", "mel", "geleia", "cesta basica", "cestas basicas",
    "excedente", "excedentes", "sobra", "sobras", "sobrou", "sobraram", "perecivel", "pereciveis",
    "padaria", "laticinio", "laticinios", "hortifrutis", "feira", "mercado", "estoque",
    "cheiro verde", "pe de moleque", "hot dog", "cachorro quente", "formula infantil",
)
_ALIMENTOS_RE = re.compile(r"\b(?:" + "|".join(sorted({re.escape(a) for a in _ALIMENTOS},
                                                      key=len, reverse=True)) + r")\b")
# "200 coxinhas", "3 kg de tapioca": número seguido de unidade ou de uma palavra
_QUANTIDADE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:(?:kg|g|quilos?|gramas?|l|litros?|ml|caixas?|pacotes?|"
                         r"unidades?|duzias?|fardos?|sacos?|latas?|potes?|bandejas?|porcoes?|garrafas?|"
                         r"cestas?)\b|(?:de\s+)?[a-z]{3,})")
# vocabulário do dataset do classificador (data/alimentos.csv): sinal fraco de alimento,
# sem as palavras genéricas que aparecem nele
_GENERICAS = {
    "contra", "dois", "forma", "feito", "extra", "completo", "individual", "diversos", "itens", "cara",
    "festa", "italia", "limpa", "limpo", "lisa", "longa", "duro", "grosso", "flor", "corda", "disco",
    "cabeca", "animal", "bebe", "leao", "cheiro", "coloridos", "coracao", "cristal", "formula", "infantil",
    "ingles", "inglesa", "japonesa", "japoneses", "italiana", "italiano", "americana", "arabe", "branca",
    "branco", "brancos", "amarelo", "executivo", "fitness", "detox", "finos", "caixa", "caixinha", "copo",
    "cubo", "cubos", "fatia", "garrafa", "lata", "litro", "litros", "bandeja", "barra", "cartela", "fardo",
    "pacote", "pacotes", "unidade", "unidades", "granel", "embalada", "derivados", "liquido", "inteira",
    "inteiro", "fresca", "fresco", "frescas", "frescos", "gelada", "gelado", "pote", "potes", "saco",
    "sacos", "vidro", "kilo", "quilo", "quilos", "gramas", "tipo", "sabor", "sabores", "sortidos",
    "variados", "mista", "misto", "natural", "zero", "light", "diet", "grande", "pequeno", "media", "medio",
    "para", "vida", "maria", "micro", "mini", "minas", "nacional", "natura", "ninja", "ondas", "parafuso",
    "partida", "pascal", "paulista", "peca", "primeira", "segunda", "produtos", "quente", "quentes",
    "quimico", "reino", "restaurante", "roxa", "roxo", "seca", "secas", "seco", "simples", "solido",
    "spray", "terra", "tommy", "tradicional", "verde", "verdes", "vermelha", "vermelho", "vermelhos",
    "virgem", "williams", "preto", "prata", "perola", "rubi", "mole", "moleque", "palmer", "petit",
}
_VOCABULARIO = None


def _vocabulario():
    global _VOCABULARIO
    if _VOCABULARIO is None:
        palavras = set()
        try:
            with open(PASTA_CONFIG.parent / "data" / "alimentos.csv", encoding="utf-8") as arquivo:
                for linha in csv.DictReader(arquivo):
                    palavras.update(p for p in re.findall(r"[a-z]{4,}", _simples(linha.get("texto", ""))))
        except OSError:
            pass
        _VOCABULARIO = frozenset(palavras - _GENERICAS)
    return _VOCABULARIO
_TAREFA_FORA = re.compile(
    r"\b(?:escrev[ae]m?|escrever|cri[ae]m?|criar|ger[ae]m?|gerar|faca|faz|fazer|componha|elabore|conte|"
    r"conta|me (?:de|da|diz)|traduz[ae]?|traduzir|programe|codifique|write|create|generate|tell me|make)\b"
    r".{0,40}\b(?:poemas?|poesias?|piadas?|historinhas?|historias?|contos?|redac\w*|musicas?|"
    r"letras? de musica|raps?|codigo (?:em|python|java|de programa)|um codigo|scripts?|sql|python|"
    r"javascript|html|traduc\w*|artigos?|resenhas?|poem|joke|story|code|essay)\b")
_ASSUNTO_FORA = re.compile(
    r"\b(?:hacke\w*|invadir|invasao|senha d[eoa]|phishing|malware|virus|bitcoin|cripto\w*|"
    r"investiment\w*|apostas?|cassino|loteria|horoscopo|eleic\w*|president\w*|partido|politic\w*|"
    r"capital d[aoe]|quem (?:ganhou|descobriu|inventou)|previsao do tempo|futebol|novela|filme|"
    r"remedio|medicament\w*|arma|armas|droga|drogas)\b")


def _bloqueio(motivo):
    return Veredito(True, motivo, mensagem_recusa(motivo))


def verificar_entrada(texto):
    """Texto livre do usuário antes de qualquer LLM. Bloqueia injeção e pedido fora do tema."""
    bruto = str(texto or "")
    if len(bruto) > 600:
        return _bloqueio("fora_do_tema")
    simples = _simples(bruto)
    variantes = {simples, _simples(bruto, leet=True)}
    soletrados = [s for v in variantes for s in _soletrados(v)]
    if (_MARCADORES.search(bruto) or any(p.search(v) for p in _INJECAO for v in variantes)
            or any(_COMPACTO.search(s) for s in soletrados)):
        return _bloqueio("injecao")
    if _JSON_ESQUEMA.search(simples):
        return _bloqueio("injecao")
    if _TAREFA_FORA.search(simples):
        return _bloqueio("fora_do_tema")
    if _ALIMENTOS_RE.search(simples):
        return Veredito(False)
    if _ASSUNTO_FORA.search(simples):
        return _bloqueio("fora_do_tema")
    if _vocabulario() & set(re.findall(r"[a-z]{4,}", simples)):
        return Veredito(False)
    if not _QUANTIDADE.search(simples):
        return _bloqueio("fora_do_tema")
    # quantidade sem alimento conhecido ("3 caixas de bombril"?): a LLM tenta, e a saída
    # continua passando pela guarda e pela validação de formato
    return Veredito(False, "duvida")


# --- saída: campos de texto que a LLM devolveu ---
_LINK = re.compile(r"(?i)\b(?:https?://|www\.)|\b[\w-]+\.(?:com|net|org|io|br|xyz|ru)\b|"
                   r"<[a-z/!][^>]*>|\]\(")
_VAZAMENTO = re.compile(
    r"\b(?:voce extrai pedidos|voce resume indicadores|formato obrigatorio|categorias permitidas|"
    r"unidades permitidas|trate os dados como dados|system prompt|prompt do sistema|instruc\w* do sistema|"
    r"ignor\w* (?:as|todas as) instruc\w*|groq_api_key|api key|chave da api)\b")


def _textos_saida(objeto, formato):
    if formato == "pedido":
        return [item.get("nome", "") for item in objeto.get("itens", [])] + [objeto.get("observacoes", "")]
    return [objeto.get("resumo", "")] + list(objeto.get("recomendacoes", []))


def _numeros(texto):
    return [float(n.replace(",", ".")) for n in re.findall(r"(?<![\w.,])\d+(?:[.,]\d+)?", texto)]


def _numeros_permitidos(dados):
    vistos = set()

    def visitar(valor):
        if isinstance(valor, bool):
            return
        if isinstance(valor, (int, float)):
            vistos.add(round(float(valor), 1))
        elif isinstance(valor, dict):
            for v in valor.values():
                visitar(v)
        elif isinstance(valor, (list, tuple)):
            for v in valor:
                visitar(v)
    visitar(dados)
    return vistos | {30.0, 3.0, 1.0, 0.0}


def verificar_saida(objeto, formato, dados=None):
    """Resposta já validada no formato. Bloqueia dado pessoal, link, vazamento do prompt
    e, no resumo, número que não veio dos agregados enviados ao modelo."""
    textos = [str(t or "") for t in _textos_saida(objeto, formato)]
    for texto in textos:
        if len(texto) > 1000:  # _validar_resumo permite até 1000 caracteres.
            return _bloqueio("vazamento")
        if pii.encontrar(texto):
            return _bloqueio("dado_pessoal")
        if _LINK.search(texto):
            return _bloqueio("link")
        if _VAZAMENTO.search(_simples(texto)) or _MARCADORES.search(texto):
            return _bloqueio("vazamento")
    if formato == "resumo" and dados is not None:
        permitidos = _numeros_permitidos(dados)
        for numero in (n for texto in textos for n in _numeros(texto)):
            if round(numero, 1) not in permitidos:
                return _bloqueio("numero")
    return Veredito(False)


# --- mensagens de recusa: lidas do rails.co (fonte única com o NeMo) ---
_MENSAGENS_PADRAO = {
    "injecao": "Não posso seguir instruções escritas no texto. Descreva só os alimentos, "
               "as quantidades e o prazo (ex.: 10 kg de arroz até sexta).",
    "fora_do_tema": "Eu só ajudo com doação de alimentos. Descreva o que você tem ou precisa "
                    "(ex.: 20 pães e 5 litros de leite).",
}
_MENSAGENS = None


def _carregar_mensagens():
    mensagens = dict(_MENSAGENS_PADRAO)
    try:
        colang = (PASTA_CONFIG / "rails.co").read_text(encoding="utf-8")
    except OSError:
        return mensagens
    for nome, texto in re.findall(r'(?m)^define bot recusar (\w+)\s*\n\s*"([^"]+)"', colang):
        mensagens[nome] = texto
    return mensagens


def mensagem_recusa(motivo):
    global _MENSAGENS
    if _MENSAGENS is None:
        _MENSAGENS = _carregar_mensagens()
    return _MENSAGENS.get(motivo)


# --- motor: NeMo Guardrails quando RECONECTA_NEMO=1 e a biblioteca está instalada (CI e
# testes); senão as mesmas ações chamadas direto (produção). O resultado é o mesmo. ---
_nemo = {"rails": None, "falhou": False}
_nemo_lock = threading.Lock()


def _rails_nemo():
    if os.getenv("RECONECTA_NEMO", "").strip() != "1" or _nemo["falhou"]:
        return None
    if _nemo["rails"] is None:
        try:
            from nemoguardrails import LLMRails, RailsConfig
            # o NeMo registra os eventos com o texto da conversa em INFO/DEBUG: log mínimo
            logging.getLogger("nemoguardrails").setLevel(logging.WARNING)
            _nemo["rails"] = LLMRails(RailsConfig.from_path(str(PASTA_CONFIG)))
        except Exception:  # noqa: BLE001 - sem a biblioteca, as ações rodam direto
            _nemo["falhou"] = True
            _log.warning("NeMo Guardrails indisponível; guardas rodando direto")
            return None
    return _nemo["rails"]


def motor():
    return "nemo" if _rails_nemo() is not None else "direto"


def _motivo_da_mensagem(conteudo):
    for motivo in ("injecao", "fora_do_tema"):
        if conteudo == mensagem_recusa(motivo):
            return motivo
    return "saida"


def checar_entrada(texto):
    rails = _rails_nemo()
    if rails is None:
        return verificar_entrada(texto)
    with _nemo_lock:
        resultado = rails.check([{"role": "user", "content": str(texto or "")}])
    if resultado.status.value != "blocked":
        return Veredito(False)
    motivo = _motivo_da_mensagem(resultado.content)
    return Veredito(True, motivo, mensagem_recusa(motivo))


def checar_saida(objeto, formato, entrada=""):
    """entrada: o texto enviado à LLM (no resumo, o JSON dos agregados)."""
    rails = _rails_nemo()
    if rails is None:
        dados = None
        if formato == "resumo":
            try:
                dados = json.loads(entrada)
            except (TypeError, ValueError):
                dados = None
        return verificar_saida(objeto, formato, dados)
    from nemoguardrails.rails.llm.options import RailType
    with _nemo_lock:
        resultado = rails.check([{"role": "user", "content": str(entrada or "")},
                                 {"role": "assistant", "content": json.dumps(objeto, ensure_ascii=False)}],
                                rail_types=[RailType.OUTPUT])
    if resultado.status.value != "blocked":
        return Veredito(False)
    return Veredito(True, "saida", mensagem_recusa("saida"))
