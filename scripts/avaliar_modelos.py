"""Avalia a interpretação de pedidos em data/pedidos_avaliacao.jsonl.

Compara (a) regras, (b) classificador treinado + regras e (c) a LLM local
(qwen2.5:3b no Ollama em http://localhost:11434) e grava docs/avaliacao-modelos.md
e modelo/avaliacao.json com os números da execução.

Uso:  python scripts/avaliar_modelos.py            (com a LLM; leva alguns minutos)
      python scripts/avaliar_modelos.py --sem-llm  (só regras e classificador)
"""

import copy
import json
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import classificador  # noqa: E402
import llm_service  # noqa: E402
from fuso import hoje_brasilia  # noqa: E402

PEDIDOS = RAIZ / "data" / "pedidos_avaliacao.jsonl"
RELATORIO = RAIZ / "docs" / "avaliacao-modelos.md"
BRUTO = RAIZ / "modelo" / "avaliacao.json"
VAZIAS = {"de", "da", "do", "das", "dos", "e", "em", "para", "com"}
DIAS = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def ler_pedidos():
    with PEDIDOS.open(encoding="utf-8") as arquivo:
        return [json.loads(linha) for linha in arquivo if linha.strip()]


def resolver_prazo(prazo, hoje):
    """Transforma o prazo do gabarito na data esperada para o dia da execução."""
    if not prazo:
        return None
    tipo, valor = prazo["tipo"], prazo.get("valor")
    if tipo == "amanha":
        return (hoje + timedelta(days=1)).isoformat()
    if tipo == "em_dias":
        return (hoje + timedelta(days=valor)).isoformat()
    if tipo == "dia_semana":
        return (hoje + timedelta(days=(DIAS[valor] - hoje.weekday()) % 7 or 7)).isoformat()
    if tipo == "data":
        return valor
    if tipo == "dia_mes":
        ano, mes = hoje.year, hoje.month
        for _ in range(13):
            try:
                candidato = date(ano, mes, valor)
            except ValueError:
                candidato = None
            if candidato and candidato > hoje:
                return candidato.isoformat()
            mes, ano = (1, ano + 1) if mes == 12 else (mes + 1, ano)
    raise ValueError(f"prazo desconhecido: {prazo}")


def _singular(palavra):
    for final, troca in (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el")):
        if palavra.endswith(final) and len(palavra) > 4:
            return palavra[:-len(final)] + troca
    return palavra[:-1] if palavra.endswith("s") and len(palavra) > 3 else palavra


def _palavras(nome):
    return {_singular(p) for p in classificador.normalizar(nome).split()} - VAZIAS


def semelhanca(nome_a, nome_b):
    a, b = _palavras(nome_a), _palavras(nome_b)
    if not a or not b:
        return 0.0
    if a <= b or b <= a:
        return 0.5 + 0.5 * len(a & b) / len(a | b)
    return len(a & b) / len(a | b)


def casar(gabarito, previstos):
    """Pares (item do gabarito, item previsto ou None), cada previsto usado uma vez."""
    candidatos = sorted(((semelhanca(g["nome"], p["nome"]), ig, ip)
                         for ig, g in enumerate(gabarito) for ip, p in enumerate(previstos)),
                        key=lambda t: (-t[0], t[1], t[2]))
    par, usados = {}, set()
    for valor, ig, ip in candidatos:
        if valor >= 0.5 and ig not in par and ip not in usados:
            par[ig] = ip
            usados.add(ip)
    return [(g, previstos[par[ig]] if ig in par else None) for ig, g in enumerate(gabarito)], \
        len(previstos) - len(usados)


def pontuar(pedido, saida, prazo_esperado):
    previstos = (saida or {}).get("itens") or []
    pares, sobrando = casar(pedido["itens"], previstos)
    linha = {"itens": len(pares), "encontrados": 0, "categoria": 0, "quantidade": 0,
             "unidade": 0, "sobrando": sobrando, "previstos": len(previstos)}
    for esperado, previsto in pares:
        if not previsto:
            continue
        linha["encontrados"] += 1
        linha["categoria"] += previsto["categoria"] == esperado["categoria"]
        linha["quantidade"] += abs(float(previsto["quantidade"]) - float(esperado["quantidade"])) < 0.005
        linha["unidade"] += previsto["unidade_medida"] == esperado["unidade_medida"]
    linha["prazo"] = ((saida or {}).get("receber_ate") == prazo_esperado)
    linha["perfeito"] = (linha["prazo"] and sobrando == 0 and all(
        linha[c] == linha["itens"] for c in ("encontrados", "categoria", "quantidade", "unidade")))
    return linha


def sistema_regras(texto):
    return llm_service._pedido_regras(texto, usar_classificador=False), "regras"


def sistema_classificador(texto):
    return llm_service._pedido_regras(texto), "regras"


def sistemas_llm(texto):
    """Uma chamada ao Ollama; devolve (saída só validada, saída da aplicação e sua fonte)."""
    bruto = llm_service._chamar_ollama(llm_service._sistema_pedido(),
                                       llm_service._sem_identificadores(texto),
                                       formato=llm_service.ESQUEMA_PEDIDO)
    validado = llm_service._validar_pedido(bruto)
    aplicacao, fonte = None, "regras"
    if validado:
        aplicacao = llm_service._conferir_com_texto(copy.deepcopy(validado), texto)
        fonte = "llm" if aplicacao else "regras"
    if not aplicacao:
        aplicacao = llm_service._pedido_regras(texto)
    return validado, aplicacao, fonte


def resumir(linhas, tempos):
    itens = sum(l["itens"] for l in linhas)
    previstos = sum(l["previstos"] for l in linhas)
    soma = lambda campo: sum(l[campo] for l in linhas)  # noqa: E731
    por_nivel = {}
    for nivel in ("facil", "medio", "dificil"):
        do_nivel = [l for l in linhas if l["dificuldade"] == nivel]
        por_nivel[nivel] = {"pedidos": len(do_nivel),
                            "perfeitos": sum(l["perfeito"] for l in do_nivel)}
    return {
        "pedidos": len(linhas), "itens_gabarito": itens, "itens_previstos": previstos,
        "itens_encontrados": soma("encontrados"), "itens_sobrando": soma("sobrando"),
        "categoria_certa": soma("categoria"), "quantidade_certa": soma("quantidade"),
        "unidade_certa": soma("unidade"), "prazo_certo": soma("prazo"),
        "pedidos_perfeitos": soma("perfeito"), "por_dificuldade": por_nivel,
        "latencia_s": {"media": round(statistics.mean(tempos), 3),
                       "mediana": round(statistics.median(tempos), 3),
                       "maxima": round(max(tempos), 3)},
    }


def _pct(parte, total):
    return f"{parte}/{total} ({100 * parte / total:.1f}%)" if total else "—"


def _itens_curtos(saida):
    return "; ".join(f"{i['quantidade']:g} {i['unidade_medida']} {i['nome']} [{i['categoria']}]"
                     for i in (saida or {}).get("itens") or []) or "(nenhum item)"


def montar_relatorio(resultado):
    r = resultado
    nomes = {"regras": "(a) Regras", "classificador": "(b) Classificador + regras",
             "llm_validada": "(c1) LLM, saída validada",
             "llm_aplicacao": "(c2) LLM na aplicação"}
    presentes = [chave for chave in nomes if chave in r["sistemas"]]
    linhas = [
        "# Avaliação dos modelos de interpretação de pedidos", "",
        f"Execução de **{r['executado_em']}** (horário de Brasília), gerada por "
        "`python scripts/avaliar_modelos.py`. Os números abaixo são desta execução; "
        "rodar de novo regrava este arquivo.", "",
        f"- Conjunto: `data/pedidos_avaliacao.jsonl`, {r['pedidos']} pedidos "
        f"({r['por_dificuldade']['facil']} fáceis, {r['por_dificuldade']['medio']} médios, "
        f"{r['por_dificuldade']['dificil']} difíceis) e {r['itens']} itens no gabarito.",
        f"- Classificador: `modelo/classificador_categorias.json`, treinado em "
        f"{r['classificador']['treinado_em']}, limiar {r['classificador']['limiar']}.",
        f"- LLM: {r['llm']}", "",
        "## Sistemas comparados", "",
        "- **(a) Regras**: expressões regulares para quantidade, unidade e prazo; categoria por palavras-chave.",
        "- **(b) Classificador + regras**: as mesmas regras, com a categoria vinda do modelo treinado "
        "quando a confiança passa do limiar. É o que a aplicação responde sem o Ollama (`fonte: \"regras\"`).",
        "- **(c1) LLM, saída validada**: resposta do `qwen2.5:3b` depois da validação de formato, sem conferência.",
        "- **(c2) LLM na aplicação**: o caminho completo de `interpretar_pedido`: a saída da LLM é conferida "
        "com os números do texto e, se for rejeitada, a resposta vem de (b).", "",
        "## Resultados", "",
        "Os percentuais de categoria, quantidade e unidade são sobre os itens do gabarito: "
        "item que o sistema não encontrou conta como erro.", "",
        "| Medida | " + " | ".join(nomes[c] for c in presentes) + " |",
        "|---|" + "---|" * len(presentes),
    ]
    def linha(rotulo, funcao):
        linhas.append(f"| {rotulo} | " + " | ".join(funcao(r["sistemas"][c]) for c in presentes) + " |")
    linha("Itens encontrados", lambda s: _pct(s["itens_encontrados"], s["itens_gabarito"]))
    linha("Categoria certa", lambda s: _pct(s["categoria_certa"], s["itens_gabarito"]))
    linha("Quantidade certa", lambda s: _pct(s["quantidade_certa"], s["itens_gabarito"]))
    linha("Unidade certa", lambda s: _pct(s["unidade_certa"], s["itens_gabarito"]))
    linha("Itens a mais (não estão no gabarito)", lambda s: str(s["itens_sobrando"]))
    linha("Prazo certo (por pedido)", lambda s: _pct(s["prazo_certo"], s["pedidos"]))
    linha("Pedido inteiro certo", lambda s: _pct(s["pedidos_perfeitos"], s["pedidos"]))
    for nivel, rotulo in (("facil", "fáceis"), ("medio", "médios"), ("dificil", "difíceis")):
        linha(f"Pedido inteiro certo: {rotulo}",
              lambda s, n=nivel: _pct(s["por_dificuldade"][n]["perfeitos"],
                                      s["por_dificuldade"][n]["pedidos"]))
    linha("Latência média por pedido", lambda s: f"{s['latencia_s']['media']} s")
    linha("Latência mediana / máxima",
          lambda s: f"{s['latencia_s']['mediana']} s / {s['latencia_s']['maxima']} s")
    if "fontes_llm" in r:
        f = r["fontes_llm"]
        linhas += ["", f"Na aplicação com a LLM ligada, {f['llm']} de {r['pedidos']} respostas saíram com "
                   f"`fonte: \"llm\"` e {f['regras']} caíram para as regras. A LLM não devolveu um objeto "
                   f"válido em {f['invalidas']} pedidos."]
    linhas += ["", "## Exemplos de erro", ""]
    for chave in presentes:
        linhas += [f"### {nomes[chave]}", ""]
        exemplos = r["erros"][chave][:6]
        if not exemplos:
            linhas += ["Nenhum erro nesta execução.", ""]
        for e in exemplos:
            linhas += [f"- Pedido {e['id']} ({e['dificuldade']}): \"{e['texto']}\"",
                       f"  - Esperado: {e['esperado']}; prazo {e['prazo_esperado']}",
                       f"  - Obtido: {e['obtido']}; prazo {e['prazo_obtido']}"]
        linhas.append("")
    linhas += ["## Como ler", "",
               "- O conjunto é pequeno e foi escrito para o projeto: serve para comparar os sistemas "
               "entre si, não para estimar o desempenho com pedidos reais.",
               "- Os prazos relativos (\"até sexta\") são resolvidos para a data da execução, então o "
               "gabarito de prazo muda conforme o dia em que o script roda.",
               "- A latência depende desta máquina; a da LLM inclui a carga do modelo na primeira chamada.",
               ""]
    return "\n".join(linhas)


def main():
    com_llm = "--sem-llm" not in sys.argv
    hoje = hoje_brasilia()
    pedidos = ler_pedidos()
    modelo = classificador.modelo_padrao()
    if not modelo:
        sys.exit("Modelo não encontrado: rode scripts/treinar_modelo.py antes.")
    sistemas = {"regras": [], "classificador": []}
    tempos = {"regras": [], "classificador": []}
    erros = {"regras": [], "classificador": []}
    if com_llm:
        if not llm_service._chamar_ollama("Responda JSON.", "{\"ok\": true}"):
            sys.exit("Ollama não respondeu em http://localhost:11434 (use --sem-llm).")
        for chave in ("llm_validada", "llm_aplicacao"):
            sistemas[chave], tempos[chave], erros[chave] = [], [], []
    fontes = {"llm": 0, "regras": 0, "invalidas": 0}

    def registrar(chave, pedido, saida, prazo, tempo):
        linha = pontuar(pedido, saida, prazo)
        linha["dificuldade"] = pedido["dificuldade"]
        sistemas[chave].append(linha)
        tempos[chave].append(tempo)
        if not linha["perfeito"]:
            erros[chave].append({
                "id": pedido["id"], "dificuldade": pedido["dificuldade"], "texto": pedido["texto"],
                "esperado": _itens_curtos(pedido), "prazo_esperado": prazo,
                "obtido": _itens_curtos(saida), "prazo_obtido": (saida or {}).get("receber_ate")})

    for numero, pedido in enumerate(pedidos, 1):
        prazo = resolver_prazo(pedido["prazo"], hoje)
        for chave, funcao in (("regras", sistema_regras), ("classificador", sistema_classificador)):
            inicio = time.perf_counter()
            saida, _ = funcao(pedido["texto"])
            registrar(chave, pedido, saida, prazo, time.perf_counter() - inicio)
        if com_llm:
            inicio = time.perf_counter()
            validado, aplicacao, fonte = sistemas_llm(pedido["texto"])
            tempo = time.perf_counter() - inicio
            fontes[fonte] += 1
            fontes["invalidas"] += validado is None
            registrar("llm_validada", pedido, validado, prazo, tempo)
            registrar("llm_aplicacao", pedido, aplicacao, prazo, tempo)
            print(f"{numero}/{len(pedidos)} {tempo:.1f}s fonte={fonte}", flush=True)

    resultado = {
        "executado_em": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "pedidos": len(pedidos), "itens": sum(len(p["itens"]) for p in pedidos),
        "por_dificuldade": {n: sum(p["dificuldade"] == n for p in pedidos)
                            for n in ("facil", "medio", "dificil")},
        "classificador": {"treinado_em": modelo.metadados.get("treinado_em"),
                          "limiar": modelo.limiar},
        "llm": (f"`{llm_service.MODELO_PADRAO}` no Ollama local (`{llm_service.URL_PADRAO}`), "
                "temperatura 0,2, uma chamada por pedido." if com_llm
                else "não avaliada nesta execução (`--sem-llm`)."),
        "sistemas": {chave: resumir(linhas, tempos[chave]) for chave, linhas in sistemas.items()},
        "erros": erros,
    }
    if com_llm:
        resultado["fontes_llm"] = fontes
    BRUTO.parent.mkdir(parents=True, exist_ok=True)
    BRUTO.write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    RELATORIO.write_text(montar_relatorio(resultado), encoding="utf-8", newline="\n")
    for chave, resumo in resultado["sistemas"].items():
        print(chave, {k: v for k, v in resumo.items() if k != "por_dificuldade"})
    print(f"relatório: {RELATORIO.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
