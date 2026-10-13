"""Refaz os relatórios SAST em relatorios/sast/ com um comando.

Uso (na raiz do repositório):
    python scripts/sast.py             # bandit + trivy fs + trivy config + trivy image
    python scripts/sast.py --so-bandit # só o Bandit
    python scripts/sast.py --sem-imagem# sem docker build/trivy image

Saídas: relatorios/sast/bandit.{json,txt,html}, trivy-fs.{txt,json},
trivy-config.{txt,json} e trivy-image.{txt,json}.
Bandit roda via `python -m bandit` do interpretador em uso (instale com
`uv pip install bandit` no venv). O binário do Trivy pode ser informado por
TRIVY=<caminho>; fora isso, procura no PATH. `trivy image` precisa do Docker
ligado e constrói `reconecta:sast` localmente se a imagem não existir.
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
SKIP_DIRS = (".git,__pycache__,instance,relatorios,tests/fixtures,.venv,venv")
IMAGEM = "reconecta:sast"


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


def _trivy_bin():
    binario = os.getenv("TRIVY") or shutil.which("trivy")
    if not binario or (not Path(binario).exists() and not shutil.which(binario)):
        print("trivy: binário não encontrado. Defina TRIVY=<caminho> ou ponha no PATH. "
              "Pulado.")
        return None
    return binario


def _trivy_saida(binario, args, nome):
    alvo = SAIDA / nome
    proc, _ = _rodar([binario, *args, "-o", str(alvo)])
    if not alvo.exists():
        print(f"trivy {nome}: falhou\n{proc.stderr.strip()}")
        return False
    print(f"trivy {nome}: {alvo.stat().st_size} bytes")
    return True


def _trivy(binario, com_imagem):
    ok = True
    fs = ["fs", "--scanners", "vuln,secret,misconfig", "--skip-dirs", SKIP_DIRS, "."]
    config = ["config", "--severity", "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL", "."]
    for formato in ("json", "table"):
        ext = "txt" if formato == "table" else formato
        ok = _trivy_saida(binario, [*fs, "--format", formato],
                          f"trivy-fs.{ext}") and ok
        ok = _trivy_saida(binario, [*config, "--format", formato],
                          f"trivy-config.{ext}") and ok
    if com_imagem:
        if not shutil.which("docker"):
            print("trivy image: docker não está no PATH. Pulado.")
            return ok
        existe = _rodar(["docker", "image", "inspect", IMAGEM])[0].returncode == 0
        if not existe:
            print(f"trivy image: construindo {IMAGEM} (docker build)...")
            proc, _ = _rodar(["docker", "build", "-t", IMAGEM, "."])
            if proc.returncode != 0:
                print(f"docker build falhou\n{proc.stderr.strip()[-800:]}")
                return False
        for formato in ("json", "table"):
            ext = "txt" if formato == "table" else formato
            ok = _trivy_saida(binario,
                              ["image", "--scanners", "vuln,secret,misconfig",
                               "--format", formato, IMAGEM],
                              f"trivy-image.{ext}") and ok
    return ok


def main():
    so_bandit = "--so-bandit" in sys.argv
    com_imagem = "--sem-imagem" not in sys.argv
    ok = _bandit()
    if not so_bandit:
        binario = _trivy_bin()
        if binario:
            ok = _trivy(binario, com_imagem) and ok
    print("SAST concluído." if ok else "SAST com falhas (ver mensagens acima).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
