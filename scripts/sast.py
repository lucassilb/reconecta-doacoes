"""Refaz os relatórios SAST em relatorios/sast/ com um comando.

Uso (na raiz do repositório):
    python scripts/sast.py            # bandit + trivy
    python scripts/sast.py --so-bandit

Saídas: relatorios/sast/bandit.{json,txt,html} e trivy-fs.{txt,json}.
Bandit roda via `python -m bandit` do interpretador em uso (instale com
`uv pip install bandit` no venv). O binário do Trivy pode ser informado por
TRIVY=<caminho>; fora isso, procura no PATH.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "relatorios" / "sast"
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EXCLUIDOS = "./tests,./scripts,./.venv,./venv,./instance,./relatorios,./__pycache__"
BANDIT_ALVO = ["-r", ".", "-x", EXCLUIDOS]
TRIVY_ARGS = ["fs", "--scanners", "vuln,secret,misconfig",
              "--skip-dirs", ".git,__pycache__,instance,relatorios,tests/fixtures,"
              ".venv,venv", "."]


def _rodar(comando):
    inicio = time.monotonic()
    proc = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          creationflags=SEM_JANELA)
    return proc, time.monotonic() - inicio


def _bandit():
    SAIDA.mkdir(parents=True, exist_ok=True)
    for formato in ("json", "txt", "html"):
        alvo = SAIDA / f"bandit.{formato}"
        proc, _ = _rodar([sys.executable, "-m", "bandit", *BANDIT_ALVO,
                          "-f", formato, "-o", str(alvo)])
        if not alvo.exists():
            print(f"bandit {formato}: falhou\n{proc.stderr.strip()}")
            return False
        print(f"bandit {formato}: {alvo.name} ({alvo.stat().st_size} bytes)")
    try:
        dados = json.loads((SAIDA / "bandit.json").read_text(encoding="utf-8"))
        totais = dados.get("metrics", {}).get("_totals", {})
        resumo = {k: v for k, v in totais.items()
                  if k.startswith("SEVERITY") and isinstance(v, int) and v}
        print("bandit severidades:", resumo or "nenhum achado")
    except (OSError, ValueError):
        pass
    return True


def _trivy():
    binario = os.getenv("TRIVY") or shutil.which("trivy")
    if not binario or (not Path(binario).exists() and not shutil.which(binario)):
        print("trivy: binário não encontrado. Defina TRIVY=<caminho> ou ponha no PATH. "
              "Pulado.")
        return None
    SAIDA.mkdir(parents=True, exist_ok=True)
    for formato, nome in (("json", "trivy-fs.json"), ("table", "trivy-fs.txt")):
        alvo = SAIDA / nome
        proc, _ = _rodar([binario, *TRIVY_ARGS, "--format", formato,
                          "-o", str(alvo)])
        if not alvo.exists():
            print(f"trivy {formato}: falhou\n{proc.stderr.strip()}")
            return False
        print(f"trivy {formato}: {alvo.name} ({alvo.stat().st_size} bytes)")
    return True


def main():
    so_bandit = "--so-bandit" in sys.argv
    ok = _bandit()
    if not so_bandit:
        trivy = _trivy()
        ok = ok and trivy is not False
    print("SAST concluído." if ok else "SAST com falhas (ver mensagens acima).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
