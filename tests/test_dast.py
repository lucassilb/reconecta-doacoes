"""O plano DAST mantém o alvo local e trata alertas pela severidade real do ZAP."""

import json
import os
import subprocess
import sys
import pytest

from scripts.dast import PUBLICAS, PAPEIS, POSTS, RAIZ, resumir_zap, spec_parcial


def test_semente_recusa_execucao_fora_do_compose_efemero():
    ambiente = {**os.environ, "RECONECTA_DAST": "0", "DATABASE_URL": "sqlite://"}
    resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "seed_dast.py")],
                               cwd=RAIZ, env=ambiente, capture_output=True, text=True,
                               timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode != 0
    assert "SQLite efêmero" in resultado.stderr


def test_spec_zap_usa_gets_e_posts_locais_do_swagger(tmp_path):
    swagger = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
    for nome, rotas in [("publico", PUBLICAS), *[(p, dados[2]) for p, dados in PAPEIS.items()]]:
        saida = tmp_path / f"{nome}.json"
        spec_parcial(swagger, rotas, saida, POSTS[nome])
        preparado = json.loads(saida.read_text(encoding="utf-8"))
        assert preparado["host"] == "app:5000"
        assert preparado["schemes"] == ["http"]
        assert set(preparado["paths"]) == rotas | POSTS[nome]
        for rota, operacoes in preparado["paths"].items():
            assert ("get" in operacoes) == (rota in rotas)
            assert ("post" in operacoes) == (rota in POSTS[nome])


def test_resumo_zap_preserva_alta_sem_evidencia_ou_cookie(tmp_path):
    arquivo = tmp_path / "zap.json"
    arquivo.write_text(json.dumps({"site": [{"alerts": [
        {"pluginid": "40018", "alert": "SQL Injection", "riskcode": "3",
         "instances": [{"requestHeader": "Cookie: session=segredo", "evidence": "cpf"}]},
        {"pluginid": "10020", "alert": "Header", "riskcode": "1", "instances": [{}]},
    ]}]}), encoding="utf-8")
    resumo = resumir_zap({"publico": arquivo})
    assert resumo["por_severidade"]["ALTA"] == 1
    assert resumo["por_severidade"]["BAIXA"] == 1
    assert "segredo" not in json.dumps(resumo)
    assert "cpf" not in json.dumps(resumo)


def test_resumo_zap_recusa_relatorio_sem_alvo(tmp_path):
    arquivo = tmp_path / "vazio.json"
    arquivo.write_text('{"site": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="sem alvo"):
        resumir_zap({"publico": arquivo})
