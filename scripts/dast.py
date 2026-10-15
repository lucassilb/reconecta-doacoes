"""ZAP baseline e API scan no Compose efêmero; nunca aceita URL de produção.

Uso: python scripts/dast.py. Requer Docker e porta local 5005 livre.
Escreve somente resumo sem cookies, payloads ou evidências em relatorios/seguranca.
"""

import copy
from collections import Counter
import json
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
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
POSTS = {
    "publico": {"/reconecta/auth/login", "/reconecta/ia/risco-descarte",
                "/reconecta/ia/sugerir-destino"},
    "doador": {"/reconecta/excedentes"},
    "empresa": {"/reconecta/painel/doacoes", "/reconecta/ia/interpretar-pedido"},
    "ong": {"/reconecta/notificacoes/lidas"},
}
RISCO = {"0": "INFORMATIVA", "1": "BAIXA", "2": "MEDIA", "3": "ALTA", "4": "CRITICA"}
# Oferta de excedente (rodada 19): multipart com `dados` (JSON) e `foto` obrigatória.
# JPEG mínimo, mas real (SOI, APP0, SOS, EOI): passa pela assinatura e pela limpeza de metadados.
JPEG_MINIMO = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
               b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34\xff\xd9")
ROTA_OFERTA = "/reconecta/excedentes"


def oferta_ficticia():
    """JSON da oferta do doador fictício, com prazo e validade futuros em Brasília."""
    agora = datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)
    return {"retirar_ate": (agora + timedelta(days=1)).isoformat(timespec="seconds"),
            "itens": [{"nome": "Arroz", "categoria": "Grãos e cereais", "quantidade": 2,
                       "unidade_medida": "kg",
                       "validade": (agora + timedelta(days=30)).date().isoformat()}],
            "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True,
            "nao_caseiro": True,
            "retirada": {"logradouro": "Rua Ficticia", "numero": "1",
                         "municipio": "São Paulo", "uf": "SP"}}


def multipart(campos, arquivos):
    """(corpo, Content-Type) de um multipart/form-data, sem dependências externas."""
    fronteira = "reconecta-dast-" + secrets.token_hex(12)
    partes = []
    for nome, valor in campos.items():
        partes += [f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n'.encode(),
                   valor.encode("utf-8"), b"\r\n"]
    for nome, (arquivo, tipo, dados) in arquivos.items():
        partes += [(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"; '
                    f'filename="{arquivo}"\r\nContent-Type: {tipo}\r\n\r\n').encode(), dados, b"\r\n"]
    partes.append(f"--{fronteira}--\r\n".encode())
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


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


def requisicao(caminho, *, dados=None, cookie=None, corpo=None, tipo=None):
    cabecalhos = {"Accept": "application/json"}
    if dados is not None:
        cabecalhos["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode()
    elif corpo is not None:
        cabecalhos["Content-Type"] = tipo
    if cookie:
        cabecalhos["Cookie"] = cookie
    req = Request(BASE + caminho, data=corpo, headers=cabecalhos)
    with urlopen(req, timeout=15) as resposta:
        bruto = resposta.read()
        return resposta, json.loads(bruto) if "json" in resposta.headers.get("Content-Type", "") else bruto


def provar_oferta_multipart(cookie):
    """Antes do scan do doador: a oferta em multipart publica (201) e a foto volta só para o
    dono; o JSON antigo, sem foto, é recusado com campos.foto."""
    corpo, tipo = multipart({"dados": json.dumps(oferta_ficticia(), ensure_ascii=False)},
                            {"foto": ("validade.jpg", "image/jpeg", JPEG_MINIMO)})
    resposta, criado = requisicao(ROTA_OFERTA, cookie=cookie, corpo=corpo, tipo=tipo)
    if resposta.status != 201 or "foto_url" not in criado:
        raise RuntimeError("oferta multipart do doador fictício não foi publicada")
    resposta, foto = requisicao(criado["foto_url"], cookie=cookie)
    if resposta.headers.get("Content-Type") != "image/jpeg" or not foto.startswith(b"\xff\xd8"):
        raise RuntimeError("foto da oferta não voltou para o dono")
    try:
        requisicao(ROTA_OFERTA, cookie=cookie, dados=oferta_ficticia())
    except HTTPError as erro:
        if erro.code != 400 or "foto" not in json.loads(erro.read()).get("campos", {}):
            raise RuntimeError("JSON sem foto não foi recusado em campos.foto") from None
    else:
        raise RuntimeError("JSON sem foto publicou a oferta")
    return {"multipart_com_foto": 201, "foto_do_dono": 200, "json_sem_foto": 400}


def respostas_da_oferta(registro, diretas=("201", "400")):
    """Status do POST da oferta no access log do gunicorn (método, caminho, status, bytes),
    sem as duas requisições da prova direta (201 multipart e 400 do JSON sem foto)."""
    contagem = Counter(re.findall(r"POST /reconecta/excedentes (\d{3}) ", registro))
    contagem.subtract(diretas)
    return {status: total for status, total in sorted(contagem.items()) if total > 0}


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


def spec_parcial(spec, rotas, destino, posts=()):
    parcial = dict(spec)
    parcial["host"] = "app:5000"
    parcial["schemes"] = ["http"]
    parcial["paths"] = {}
    for rota in sorted(set(rotas) | set(posts)):
        metodos = ({"get"} if rota in rotas else set()) | ({"post"} if rota in posts else set())
        parcial["paths"][rota] = {
            chave: copy.deepcopy(valor) for chave, valor in spec["paths"][rota].items()
            if chave in metodos or chave == "parameters"}
    oferta = parcial["paths"].get(ROTA_OFERTA, {}).get("post")
    if oferta:
        # o campo `dados` parte de uma oferta válida; o ZAP varia a partir dela
        for parametro in oferta.get("parameters", []):
            if parametro.get("in") == "formData" and parametro.get("name") == "dados":
                parametro["default"] = json.dumps(oferta_ficticia(), ensure_ascii=False)
    for rota in rotas:
        if "get" not in parcial["paths"][rota]:
            raise RuntimeError(f"swagger.json sem GET esperado: {rota}")
    for rota in posts:
        if "post" not in parcial["paths"][rota]:
            raise RuntimeError(f"swagger.json sem POST esperado: {rota}")
    destino.write_text(json.dumps(parcial, ensure_ascii=False), encoding="utf-8")


def auth_config(cookie, destino):
    destino.write_text("\n".join((
        "replacer.full_list(0).description=contexo_sessao_ficticia",
        "replacer.full_list(0).enabled=true",
        "replacer.full_list(0).matchtype=REQ_HEADER",
        "replacer.full_list(0).matchstr=Cookie",
        "replacer.full_list(0).regex=false",
        f"replacer.full_list(0).replacement={cookie}", "")), encoding="utf-8")


# Regra 40018 (SQL Injection por diferença de resposta) nas rotas que LEEM o texto enviado:
# a resposta muda com qualquer texto, então "AND 1=1" x "AND 1=2" parece injeção. Só vira
# falso positivo se o IAST da MESMA varredura não viu nenhum SQL com dado da requisição.
FALSOS_POSITIVOS_CONDICIONAIS = {
    "40018": {"/reconecta/ia/interpretar-pedido", "/reconecta/ia/sugerir-destino",
              "/reconecta/ia/risco-descarte"},
}


def aplicar_falsos_positivos(resumo, iast):
    """Rebaixa alertas da lista acima quando o IAST confirma que não houve SQL contaminado."""
    if iast.get("achados"):
        return resumo
    rebaixados = []
    for nome, varredura in resumo["varreduras"].items():
        for alerta in varredura["alertas"]:
            rotas = FALSOS_POSITIVOS_CONDICIONAIS.get(str(alerta["id"]))
            if (rotas and alerta["severidade"] in ("ALTA", "CRITICA")
                    and set(alerta["rotas"]) <= rotas):
                resumo["por_severidade"][alerta["severidade"]] -= 1
                resumo["por_severidade"]["FALSO_POSITIVO"] = resumo["por_severidade"].get("FALSO_POSITIVO", 0) + 1
                rebaixados.append({"varredura": nome, "id": alerta["id"], "nome": alerta["nome"],
                                   "severidade_original": alerta["severidade"], "rotas": alerta["rotas"]})
                alerta["severidade"] = "FALSO_POSITIVO"
    if rebaixados:
        resumo["falsos_positivos"] = {
            "justificativa": ("rota lê o texto e devolve o que entendeu; o sensor IAST da mesma "
                              f"varredura observou {iast.get('eventos', {}).get('sql_observado', 0)} "
                              "SQLs e nenhum com dado da requisição"),
            "alertas": rebaixados}
    return resumo


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
            "escopo": "baseline público + GETs e POSTs selecionados do swagger.json por papel fictício",
            "varreduras": varreduras, "por_severidade": total}


def main():
    projecto = f"reconecta-r18-codex-{os.getpid()}"
    with tempfile.TemporaryDirectory(prefix="reconecta-dast-") as temporario:
        trabalho = Path(temporario)
        ambiente = {**os.environ, "DAST_WORK_DIR": str(trabalho)}
        spec = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
        spec_parcial(spec, PUBLICAS, trabalho / "swagger-publico.json", POSTS["publico"])
        for papel, (_, _, rotas) in PAPEIS.items():
            spec_parcial(spec, rotas, trabalho / f"swagger-{papel}.json", POSTS[papel])
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
            oferta = None
            for papel, (email, esperado, _) in PAPEIS.items():
                cookie = cookie_papel(email, esperado)
                if papel == "doador":
                    oferta = provar_oferta_multipart(cookie)
                    print(f"Oferta multipart do doador: {oferta}", flush=True)
                auth_config(cookie, trabalho / f"auth-{papel}.prop")
                zap(papel, "zap-api-scan.py", "-t", f"/zap/wrk/swagger-{papel}.json",
                    "-f", "openapi", "-z", f"-configfile /zap/wrk/auth-{papel}.prop")

            SAIDA.mkdir(parents=True, exist_ok=True)
            resumo = resumir_zap(arquivos)
            resumo["sessoes_ficticias_verificadas"] = sorted(PAPEIS)
            # o access log (gunicorn.conf.py) só tem método, caminho sem query, status e bytes
            registro = compose(projecto, ambiente, "logs", "--no-color", "app", segredo=True).stdout
            resumo["oferta_multipart"] = {"prova_direta": oferta,
                                          "respostas_post_durante_o_scan": respostas_da_oferta(registro)}
            print(f"POST da oferta durante o scan: {resumo['oferta_multipart']['respostas_post_durante_o_scan']}",
                  flush=True)
            resumo["operacoes_no_swagger"] = {
                nome: {"GET": sorted(rotas), "POST": sorted(POSTS[nome])}
                for nome, rotas in [("publico", PUBLICAS),
                                    *[(p, dados[2]) for p, dados in PAPEIS.items()]]}
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
            iast_dast = json.loads((SAIDA / "iast-dast.json").read_text(encoding="utf-8"))
            resumo = aplicar_falsos_positivos(resumo, iast_dast)
            (SAIDA / "zap.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
            print(f"ZAP após triagem com o IAST: {resumo['por_severidade']}", flush=True)
            if resumo["por_severidade"].get("ALTA", 0) or resumo["por_severidade"].get("CRITICA", 0):
                raise RuntimeError("ZAP encontrou alerta ALTA/CRITICA")
        finally:
            if iniciado:
                compose(projecto, ambiente, "down", "-v", segredo=True)


if __name__ == "__main__":
    main()
