"""Gate de autorização por objeto em processo isolado e banco em memória."""

import json
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / "scripts" / "avaliar_autorizacao.py"
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def executar(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          cwd=RAIZ, env={**os.environ, "DATABASE_URL": "sqlite://"},
                          capture_output=True, text=True, timeout=60,
                          creationflags=FLAGS)


def test_matriz_dinamica_em_sqlite_isolado(tmp_path):
    saida = tmp_path / "autorizacao.json"
    resultado = executar("--output", saida)
    assert resultado.returncode == 0, resultado.stderr[-2000:]
    matriz = json.loads(saida.read_text(encoding="utf-8"))
    assert matriz["banco"] == "SQLite em memória"
    assert matriz["contas_ficticias"] == 6
    assert matriz["falhas"] == 0
    assert matriz["requisicoes_verificadas"] >= 170
    assert all(linha["obtido"] in linha["esperado"] for linha in matriz["matriz"])
    assert all("@" not in json.dumps(linha) for linha in matriz["matriz"])


def test_escrita_nova_no_swagger_exige_cenario(tmp_path):
    spec = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
    spec["paths"]["/reconecta/privado/novo"] = {"post": {"responses": {"200": {"description": "ok"}}}}
    alterado = tmp_path / "swagger-com-rota-nova.json"
    alterado.write_text(json.dumps(spec), encoding="utf-8")
    resultado = executar("--inventory", alterado)
    assert resultado.returncode != 0
    assert "POST /reconecta/privado/novo" in resultado.stderr
