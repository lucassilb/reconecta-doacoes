"""Provas isoladas do sensor, sem deixar audit hook global na suíte principal."""

import json
import os
from pathlib import Path
import subprocess
import sys


RAIZ = Path(__file__).resolve().parent.parent


def _executar(tmp_path, codigo):
    ambiente = {**os.environ, "DATABASE_URL": "sqlite://", "GROQ_API_KEY": "",
                "RECONECTA_IAST": "1", "RECONECTA_IAST_REPORT_DIR": str(tmp_path),
                "GEO_EXTERNO": "0"}
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=ambiente,
                               capture_output=True, text=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode == 0, resultado.stderr
    arquivos = list(tmp_path.glob("iast-*.json"))
    assert len(arquivos) == 1
    return json.loads(arquivos[0].read_text(encoding="utf-8"))


def test_iast_observa_sql_parametrizado_sem_achado(tmp_path):
    relatorio = _executar(tmp_path, '''
from app import app
from models import db
from sqlalchemy import text
def consultar():
    db.session.execute(text("SELECT :valor"), {"valor": "marcador_seguro_123"}).scalar()
    return "ok"
app.add_url_rule("/_iast_seguro", view_func=consultar)
assert app.test_client().get("/_iast_seguro?valor=marcador_seguro_123").status_code == 200
''')
    assert relatorio["eventos"]["sql_observado"] >= 1
    assert relatorio["achados"] == []


def test_iast_sinaliza_sql_literal_e_sinks_sem_expor_payload(tmp_path):
    relatorio = _executar(tmp_path, '''
import sys
from app import app
from models import db
from sqlalchemy import text
from flask import request
def consultar():
    valor = request.args["valor"]
    db.session.execute(text("SELECT '" + valor + "'")).scalar()
    sys.audit("socket.connect", None, ("203.0.113.1", 443))
    sys.audit("open", "/fora-do-projeto/segredo", "r", 0)
    sys.audit("subprocess.Popen", "programa-ficticio", [], None, None)
    sys.audit("compile", valor, "<prova-iast>")
    return "ok"
app.add_url_rule("/_iast_prova", view_func=consultar)
assert app.test_client().get("/_iast_prova?valor=marcador_perigoso_123").status_code == 200
''')
    tipos = {achado["tipo"] for achado in relatorio["achados"]}
    assert {"sql_literal_com_dado_da_requisicao", "socket_fora_da_allowlist",
            "arquivo_fora_das_pastas_permitidas", "processo_iniciado",
            "codigo_com_dado_da_requisicao"} <= tipos
    assert "marcador_perigoso_123" not in json.dumps(relatorio)


def test_iast_desligado_sem_variavel(tmp_path):
    ambiente = {**os.environ, "DATABASE_URL": "sqlite://", "GROQ_API_KEY": "",
                "RECONECTA_IAST": "0", "RECONECTA_IAST_REPORT_DIR": str(tmp_path)}
    resultado = subprocess.run([sys.executable, "-c", "from app import app; "
                              "assert app.test_client().get('/reconecta/saude').status_code == 200"],
                              cwd=RAIZ, env=ambiente, capture_output=True, text=True,
                              timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode == 0, resultado.stderr
    assert not list(tmp_path.glob("iast-*.json"))


def test_iast_nao_confunde_valor_com_nome_de_coluna():
    from iast_sensor import _contaminado
    assert not _contaminado("SELECT unidade_medida FROM itens_doacao", ("unidade",))
    assert _contaminado("SELECT 'unidade'", ("unidade",))


def test_iast_aceita_tabelas_de_sistema_so_de_leitura_e_mantem_alerta_no_resto():
    # no Linux do CI, a página inicial abre /etc/mime.types (mimetypes) e os fusos (zoneinfo)
    import mimetypes
    import zoneinfo

    import iast_sensor

    assert all(iast_sensor._dentro(f) for f in mimetypes.knownfiles)
    for pasta in zoneinfo.TZPATH:
        assert iast_sensor._dentro(os.path.join(pasta, "America", "Sao_Paulo"))
    fora = "C:/Windows/win.ini" if os.name == "nt" else "/etc/passwd"
    assert not iast_sensor._dentro(fora)
