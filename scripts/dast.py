"""ZAP baseline e API scan no Compose efêmero; nunca aceita URL de produção.

Uso: python scripts/dast.py. Requer Docker e porta local 5005 livre.
Escreve somente resumo sem cookies, payloads ou evidências em relatorios/seguranca.
"""

import json
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = RAIZ / "compose.dast.yml"
SAIDA = RAIZ / "relatorios" / "seguranca"
BASE = "http://127.0.0.1:5005"
PAPEIS = {
    "doador": ("doador@dast.invalid", "doador",
               {"/reconecta/auth/me", "/reconecta/painel/minhas-doacoes",
                "/reconecta/excedentes", "/reconecta/notificacoes"}),
    "empresa": ("empresa@dast.invalid", "empresa_alimentos",
                {"/reconecta/auth/me", "/reconecta/painel/doacoes",
                 "/reconecta/excedentes/meus", "/reconecta/notificacoes"}),
    "ong": ("ong@dast.invalid", "ong",
            {"/reconecta/auth/me", "/reconecta/painel/doacoes",
             "/reconecta/excedentes/reservas", "/reconecta/notificacoes"}),
}
PUBLICAS = {"/reconecta/saude", "/reconecta/publico/ongs",
            "/reconecta/publico/resumo", "/reconecta/publico/doacoes",
            "/reconecta/dashboard/impacto"}
RISCO = {"0": "INFORMATIVA", "1": "BAIXA", "2": "MEDIA", "3": "ALTA", "4": "CRITICA"}


def comando(args, *, ambiente, entrada=None, segredo=False, tolerar_avisos=False):
    resultado = subprocess.run(args, cwd=RAIZ, env=ambiente, input=entrada,
                               text=True, encoding="utf-8", errors="replace",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=900,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if resultado.returncode not in ((0, 2) if tolerar_avisos else (0,)):
        # As opções de autenticação contêm cookies fictícios; nunca imprimir comando
        # ou saída bruta da ferramenta, que pode incluir cabeçalhos.
        detalhe = "" if segredo else "\n".join(resultado.stdout.splitlines()[-12:])
        raise RuntimeError(f"{args[0]} falhou (código {resultado.returncode}). {detalhe}")
    if not segredo:
        print(f"{args[0]}: concluído (código {resultado.returncode})", flush=True)
    return resultado


def compose(projecto, ambiente, *args, **kwargs):
    return comando(["docker", "compose", "-f", str(COMPOSE), "-p", projecto, *args],
                   ambiente=ambiente, **kwargs)


def requisicao(caminho, *, dados=None, cookie=None):
    cabecalhos = {"Accept": "application/json"}
    if dados is not None:
        cabecalhos["Content-Type"] = "application/json"
    if cookie:
        cabecalhos["Cookie"] = cookie
    req = Request(BASE + caminho, data=json.dumps(dados).encode() if dados is not None else None,
                  headers=cabecalhos)
    with urlopen(req, timeout=15) as resposta:
        return resposta, json.loads(resposta.read())


def cookie_papel(email, esperado):
    resposta, _ = requisicao("/reconecta/auth/login",
                            dados={"identificador": email, "senha": "DastSenha123"})
    cabecalho_cookie = resposta.headers.get("Set-Cookie", "")
    if "HttpOnly" not in cabecalho_cookie or "SameSite=Lax" not in cabecalho_cookie:
        raise RuntimeError("cookie local sem proteções de sessão esperadas")
    cookie = cabecalho_cookie.split(";", 1)[0]
    if not cookie.startswith("session="):
        raise RuntimeError("login local não gerou cookie de sessão")
    _, dados = requisicao("/reconecta/auth/me", cookie=cookie)
    usuario = dados.get("usuario", dados)
    if esperado not in usuario.get("perfis", []) and usuario.get("tipo") != esperado:
        raise RuntimeError("cookie local não autenticou o papel esperado")
    return cookie


def spec_parcial(spec, rotas, destino):
    parcial = dict(spec)
    parcial["host"] = "app:5000"
    parcial["schemes"] = ["http"]
    parcial["paths"] = {rota: {metodo: valor for metodo, valor in spec["paths"][rota].items()
                                if metodo == "get"}
                        for rota in sorted(rotas)}
    if not all(parcial["paths"].values()):
        raise RuntimeError("swagger.json não contém todos os GETs esperados")
    destino.write_text(json.dumps(parcial, ensure_ascii=False), encoding="utf-8")


def auth_config(cookie, destino):
    destino.write_text("\n".join((
        "replacer.full_list(0).description=contexo_sessao_ficticia",
        "replacer.full_list(0).enabled=true",
        "replacer.full_list(0).matchtype=REQ_HEADER",
        "replacer.full_list(0).matchstr=Cookie",
        "replacer.full_list(0).regex=false",
        f"replacer.full_list(0).replacement={cookie}", "")), encoding="utf-8")


def resumir_zap(arquivos):
    varreduras = {}
    total = {nome: 0 for nome in RISCO.values()}
    versoes = set()
    conhecidas = set(json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))["paths"])
    for nome, arquivo in arquivos.items():
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
        if not bruto.get("site"):
            raise RuntimeError(f"ZAP {nome}: relatório sem alvo varrido")
        if bruto.get("@version"):
            versoes.add(bruto["@version"])
        alertas = []
        for site in bruto.get("site", []):
            for alerta in site.get("alerts", []):
                severidade = RISCO.get(str(alerta.get("riskcode")), "DESCONHECIDA")
                if severidade == "DESCONHECIDA":
                    raise RuntimeError(f"ZAP {nome}: severidade desconhecida")
                total[severidade] = total.get(severidade, 0) + 1
                rotas = {urlsplit(instancia.get("uri", "")).path
                         for instancia in alerta.get("instances", [])}
                rotas_resumidas = sorted(rota if rota in conhecidas or rota == "/"
                                        else "fora_do_swagger" for rota in rotas)
                alertas.append({"id": alerta.get("pluginid"), "nome": alerta.get("alert"),
                                "severidade": severidade,
                                "ocorrencias": len(alerta.get("instances", [])),
                                "rotas": sorted(set(rotas_resumidas))[:8]})
        varreduras[nome] = {"alertas": alertas, "quantidade": len(alertas)}
    return {"ferramenta": "OWASP ZAP stable", "versao": ", ".join(sorted(versoes)),
            "data": datetime.now(timezone.utc).isoformat(),
            "alvo": "Compose SQLite efêmero local",
            "escopo": "baseline público + GETs do swagger.json por papel fictício",
            "varreduras": varreduras, "por_severidade": total}


def main():
    projecto = f"reconecta-r18-codex-{os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="reconecta-dast-") as temporario:
        trabalho = Path(temporario)
        ambiente = {**os.environ, "DAST_WORK_DIR": str(trabalho)}
        spec = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
        spec_parcial(spec, PUBLICAS, trabalho / "swagger-publico.json")
        for papel, (_, _, rotas) in PAPEIS.items():
            spec_parcial(spec, rotas, trabalho / f"swagger-{papel}.json")
        iniciado = True  # o projeto é exclusivo; limpar mesmo se o up falhar no meio
        try:
            compose(projecto, ambiente, "up", "--build", "-d", "--wait", "app")
            _, saude = requisicao("/reconecta/saude")
            if saude.get("status") != "ok":
                raise RuntimeError("instância de prova não saudável")
            entrada = (RAIZ / "scripts" / "seed_dast.py").read_text(encoding="utf-8")
            compose(projecto, ambiente, "exec", "-T", "app", "python", "-", entrada=entrada)

            arquivos = {}
            def zap(nome, ferramenta, *opcoes):
                relatorio = f"zap-{nome}.json"
                porta_zap = 8190 + ("baseline", "publico", "doador", "empresa", "ong").index(nome)
                compose(projecto, ambiente, "run", "-T", "--rm", "--no-deps", "zap",
                        ferramenta, *opcoes, "-P", str(porta_zap), "-T", "5",
                        "-J", relatorio, "-I", "-s",
                        tolerar_avisos=True, segredo=True)
                caminho = trabalho / relatorio
                if not caminho.is_file():
                    raise RuntimeError(f"ZAP não produziu {relatorio}")
                arquivos[nome] = caminho
                print(f"ZAP {nome}: relatório recebido", flush=True)

            zap("baseline", "zap-baseline.py", "-t", "http://app:5000/", "-m", "1")
            zap("publico", "zap-api-scan.py", "-t", "/zap/wrk/swagger-publico.json",
                "-f", "openapi")
            for papel, (email, esperado, _) in PAPEIS.items():
                auth_config(cookie_papel(email, esperado), trabalho / f"auth-{papel}.prop")
                zap(papel, "zap-api-scan.py", "-t", f"/zap/wrk/swagger-{papel}.json",
                    "-f", "openapi", "-z", f"-configfile /zap/wrk/auth-{papel}.prop")

            SAIDA.mkdir(parents=True, exist_ok=True)
            resumo = resumir_zap(arquivos)
            resumo["sessoes_ficticias_verificadas"] = sorted(PAPEIS)
            (SAIDA / "zap.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
            print(f"ZAP por severidade: {resumo['por_severidade']}", flush=True)
            # O sensor grava por requisição; docker cp lê apenas a pasta desse
            # contêiner efêmero, sem consultar o banco do host.
            iast = trabalho / "iast"
            iast.mkdir()
            compose(projecto, ambiente, "cp", "app:/tmp/iast/.", str(iast))
            comando([sys.executable, str(RAIZ / "scripts" / "resumo_iast.py"), str(iast),
                     "--saida", str(SAIDA / "iast-dast.json")],
                    ambiente=ambiente)
            if resumo["por_severidade"].get("ALTA", 0) or resumo["por_severidade"].get("CRITICA", 0):
                raise RuntimeError("ZAP encontrou alerta ALTA/CRITICA")
        finally:
            if iniciado:
                compose(projecto, ambiente, "down", "-v", segredo=True)


if __name__ == "__main__":
    main()
