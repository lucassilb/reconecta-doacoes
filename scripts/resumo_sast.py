"""Resume relatórios versionados de SAST e a matriz STRIDE sem rodar scanners."""

import json
import re
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SEVERIDADES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")


def contar_trivy(documento):
    contagem = Counter()
    for resultado in documento.get("Results", []):
        for item in resultado.get("Vulnerabilities") or []:
            contagem[item.get("Severity", "UNKNOWN").upper()] += 1
        contagem["segredos"] += len(resultado.get("Secrets") or [])
        contagem["configuracoes"] += len(resultado.get("Misconfigurations") or [])
    return {s: contagem[s] for s in SEVERIDADES} | {
        "segredos": contagem["segredos"], "configuracoes": contagem["configuracoes"]}


def contar_stride(texto):
    estados = Counter()
    for linha in texto.splitlines():
        if re.match(r"^\| [STRIDE]\d+\b", linha):
            estado = linha.rsplit("|", 2)[-2].strip()
            estados["mitigados" if estado.startswith("✔") else "residuais"] += 1
    return dict(estados) | {"fonte": "docs/stride.md; estado declarado por risco"}


def correcoes_documentadas(texto):
    linhas = [linha for linha in texto.splitlines() if linha.startswith("| ")]
    cves = sorted({cve for linha in linhas for cve in re.findall(r"CVE-\d{4}-\d+", linha)})
    return {"cves_corrigidas": len(cves), "cves": cves,
            "bandit_b104_corrigido": any("B104" in linha and "Corrigido" in linha for linha in linhas),
            "bandit_b608_justificado": any("B608 ×4" in linha and "Justificados" in linha for linha in linhas),
            "fonte": "docs/sast.md; correções históricas documentadas, distintas dos achados atuais"}


def resumir(raiz=RAIZ):
    pasta = raiz / "relatorios" / "sast"
    arquivos = {}
    for nome in ("bandit", "trivy-fs", "trivy-config", "trivy-image"):
        caminho = pasta / f"{nome}.json"
        if not caminho.exists():
            arquivos[nome] = {"disponivel": False}
            continue
        documento = json.loads(caminho.read_text(encoding="utf-8"))
        contagens = (Counter(r.get("issue_severity", "UNKNOWN").upper()
                             for r in documento.get("results", [])) if nome == "bandit"
                     else contar_trivy(documento))
        arquivos[nome] = {"disponivel": True,
                          "varredura_em": documento.get("generated_at") or documento.get("CreatedAt"),
                          "severidades": {s: contagens.get(s, 0) for s in SEVERIDADES}}
        if nome != "bandit":
            arquivos[nome]["segredos"] = contagens["segredos"]
            arquivos[nome]["configuracoes"] = contagens["configuracoes"]
    return {"ferramentas": arquivos,
            "stride": contar_stride((raiz / "docs" / "stride.md").read_text(encoding="utf-8")),
            "correcoes_documentadas": correcoes_documentadas(
                (raiz / "docs" / "sast.md").read_text(encoding="utf-8")),
            "nota": "Cada ferramenta mantém sua própria data; a imagem pode ser anterior ao código atual."}


if __name__ == "__main__":
    destino = RAIZ / "relatorios" / "sast" / "resumo.json"
    conteudo = json.dumps(resumir(), ensure_ascii=False, indent=2) + "\n"
    destino.write_text(conteudo, encoding="utf-8")
    # relatorios/ é excluído da imagem Docker; esta cópia acompanha o código.
    (RAIZ / "data" / "resumo_sast.json").write_text(conteudo, encoding="utf-8")
    print(destino)
