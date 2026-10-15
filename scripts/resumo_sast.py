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


def _trivy_bloqueantes(documento, severidades):
    """Achados que reprovam o gate: vulns corrigíveis, segredos e misconfigs nas
    severidades bloqueadas. Segredos do Trivy vêm sempre como CRITICAL."""
    total = 0
    for resultado in documento.get("Results", []):
        for vuln in resultado.get("Vulnerabilities") or []:
            if (vuln.get("Severity", "").upper() in severidades and
                    vuln.get("FixedVersion")):
                total += 1
        total += len(resultado.get("Secrets") or [])
        for misconfig in resultado.get("Misconfigurations") or []:
            if misconfig.get("Severity", "").upper() in severidades:
                total += 1
    return total


def _gate(nome, regra, resultado, detalhe):
    return {"gate": nome, "regra": regra, "resultado": resultado, "detalhe": detalhe}


def _metricas_ia(raiz):
    """metricas.json × limiares.json: True passa, False reprova, None sem dados."""
    pasta = raiz / "modelo"
    try:
        metricas = json.loads((pasta / "metricas.json").read_text(encoding="utf-8"))
        limiares = json.loads((pasta / "limiares.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "modelo/metricas.json ou limiares.json ausente"
    abaixo = []
    for chave, limiar in limiares.items():
        if isinstance(limiar, dict):
            medidos = metricas.get(chave) or {}
            abaixo += [f"{chave}.{sub}={medidos.get(sub)}<{ref}"
                       for sub, ref in limiar.items()
                       if isinstance(medidos.get(sub), (int, float))
                       and medidos[sub] < ref]
            continue
        medido = metricas.get(chave)
        if isinstance(medido, dict):
            medido = medido.get("acuracia")
        if isinstance(medido, (int, float)) and medido < limiar:
            abaixo.append(f"{chave}={medido}<{limiar}")
    if abaixo:
        return False, "abaixo do limiar: " + ", ".join(abaixo)
    return True, "todas as métricas com limiar atendem"


def _avaliar_gates(ferramentas, raiz):
    """Reproduz a regra de cada job do CI sobre os relatórios já gerados."""
    gates = []
    bandit = ferramentas.get("bandit", {})
    if bandit.get("disponivel"):
        altas = bandit.get("severidades", {}).get("HIGH", 0)
        gates.append(_gate("bandit-high",
                           "sast-bandit falha com qualquer achado de severidade HIGH",
                           "passou" if altas == 0 else "falhou",
                           f"{altas} achado(s) HIGH no último relatório"))
    else:
        gates.append(_gate("bandit-high",
                           "sast-bandit falha com qualquer achado de severidade HIGH",
                           "sem_dados", "relatório bandit.json ausente"))

    pasta = raiz / "relatorios" / "sast"
    fs = ferramentas.get("trivy-fs", {})
    if fs.get("disponivel"):
        bloqueantes = _trivy_bloqueantes(
            json.loads((pasta / "trivy-fs.json").read_text(encoding="utf-8")),
            {"HIGH", "CRITICAL"})
        gates.append(_gate("trivy-fs",
                           "sast-trivy falha em HIGH/CRITICAL com correção nos arquivos",
                           "passou" if bloqueantes == 0 else "falhou",
                           f"{bloqueantes} achado(s) bloqueante(s) (corrigível, segredo ou misconfig alta)"))
    else:
        gates.append(_gate("trivy-fs",
                           "sast-trivy falha em HIGH/CRITICAL com correção nos arquivos",
                           "sem_dados", "relatório trivy-fs.json ausente"))

    config = ferramentas.get("trivy-config", {})
    if config.get("disponivel"):
        bloqueantes = _trivy_bloqueantes(
            json.loads((pasta / "trivy-config.json").read_text(encoding="utf-8")),
            {"HIGH", "CRITICAL"})
        gates.append(_gate("trivy-config",
                           "sast-trivy falha em HIGH/CRITICAL na configuração (IaC)",
                           "passou" if bloqueantes == 0 else "falhou",
                           f"{bloqueantes} achado(s) bloqueante(s)"))
    else:
        gates.append(_gate("trivy-config",
                           "sast-trivy falha em HIGH/CRITICAL na configuração (IaC)",
                           "sem_dados", "relatório trivy-config.json ausente"))

    imagem = ferramentas.get("trivy-image", {})
    if imagem.get("disponivel"):
        bloqueantes = _trivy_bloqueantes(
            json.loads((pasta / "trivy-image.json").read_text(encoding="utf-8")),
            {"CRITICAL"})
        gates.append(_gate("trivy-imagem",
                           "sast-trivy falha em CRITICAL com correção na imagem Docker",
                           "passou" if bloqueantes == 0 else "falhou",
                           f"{bloqueantes} achado(s) bloqueante(s)"))
    else:
        gates.append(_gate("trivy-imagem",
                           "sast-trivy falha em CRITICAL com correção na imagem Docker",
                           "sem_dados", "relatório trivy-image.json ausente"))

    passou_ia, detalhe_ia = _metricas_ia(raiz)
    gates.append(_gate("ia-limiares",
                       "job ia falha se métricas caírem abaixo de modelo/limiares.json",
                       "passou" if passou_ia else "falhou" if passou_ia is False else "sem_dados",
                       detalhe_ia))

    seguranca = raiz / "relatorios" / "seguranca"
    semgrep = ferramentas.get("semgrep", {})
    if semgrep.get("disponivel"):
        erros = semgrep.get("severidades", {}).get("ERROR", 0)
        gates.append(_gate("semgrep-erro",
                           "sast-semgrep falha com achado de severidade ERROR",
                           "passou" if erros == 0 else "falhou",
                           f"{erros} achado(s) ERROR no último relatório"))
    else:
        gates.append(_gate("semgrep-erro",
                           "sast-semgrep falha com achado de severidade ERROR",
                           "sem_dados", "relatório semgrep.json ausente"))

    audit = ferramentas.get("pip-audit", {})
    if audit.get("disponivel"):
        vulns = audit.get("vulnerabilidades", 0)
        gates.append(_gate("sca-pip-audit",
                           "sca-pip-audit falha com qualquer CVE nas dependências",
                           "passou" if vulns == 0 else "falhou",
                           f"{vulns} vulnerabilidade(s) nas dependências"))
    else:
        gates.append(_gate("sca-pip-audit",
                           "sca-pip-audit falha com qualquer CVE nas dependências",
                           "sem_dados", "relatório pip-audit.json ausente"))

    leaks = ferramentas.get("gitleaks-dir", {})
    if leaks.get("disponivel"):
        achados = leaks.get("achados", 0)
        gates.append(_gate("segredos-gitleaks",
                           "segredos-gitleaks falha com qualquer segredo nos arquivos",
                           "passou" if achados == 0 else "falhou",
                           f"{achados} segredo(s) fora de .gitleaksignore"))
    else:
        gates.append(_gate("segredos-gitleaks",
                           "segredos-gitleaks falha com qualquer segredo nos arquivos",
                           "sem_dados", "relatório gitleaks-dir.json ausente"))
    return gates


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
    seguranca = raiz / "relatorios" / "seguranca"
    rel_semgrep = seguranca / "semgrep.json"
    if rel_semgrep.exists():
        doc = json.loads(rel_semgrep.read_text(encoding="utf-8-sig"))
        sev = Counter(r.get("extra", {}).get("severity", "UNKNOWN").upper()
                      for r in doc.get("results", []))
        arquivos["semgrep"] = {"disponivel": True, "severidades": dict(sev)}
    else:
        arquivos["semgrep"] = {"disponivel": False}
    rel_audit = seguranca / "pip-audit.json"
    if rel_audit.exists():
        doc = json.loads(rel_audit.read_text(encoding="utf-8"))
        deps = doc if isinstance(doc, list) else doc.get("dependencies", [])
        arquivos["pip-audit"] = {"disponivel": True,
                                 "vulnerabilidades": sum(len(d.get("vulns", [])) for d in deps)}
    else:
        arquivos["pip-audit"] = {"disponivel": False}
    for nome in ("gitleaks-dir", "gitleaks-git"):
        rel = seguranca / f"{nome}.json"
        arquivos[nome] = ({"disponivel": True,
                           "achados": len(json.loads(rel.read_text(encoding="utf-8")))}
                          if rel.exists() else {"disponivel": False})
    return {"ferramentas": arquivos,
            "gates": _avaliar_gates(arquivos, raiz),
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
