"""Sensor IAST leve, somente para provas locais com RECONECTA_IAST=1.

Observa sinks durante uma requisição. Não bloqueia operações nem registra payload,
SQL, caminho, host externo ou identificadores de pessoas.
"""

import atexit
from collections import Counter
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading

from flask import request
from sqlalchemy import event


_contexto = ContextVar("reconecta_iast", default=None)
_contagens = Counter()
_achados = []
_lock = threading.Lock()
_instalado = False
_raiz = Path(__file__).resolve().parent
_permitidas = tuple(p.resolve() for p in (_raiz, Path(tempfile.gettempdir()),
                                         Path(sys.prefix)))
_hosts_locais = {"127.0.0.1", "::1", "localhost", "db", "app", "ollama"}


def _dentro(caminho):
    try:
        alvo = Path(caminho).resolve()
        return any(alvo == base or base in alvo.parents for base in _permitidas)
    except (OSError, TypeError, ValueError):
        return False


def _valores(valor):
    if isinstance(valor, dict):
        for item in valor.values():
            yield from _valores(item)
    elif isinstance(valor, (list, tuple)):
        for item in valor:
            yield from _valores(item)
    elif isinstance(valor, str):
        texto = valor.strip()
        if 6 <= len(texto) <= 512:
            yield texto.casefold()


def _marcar_requisicao():
    dados = []
    dados.extend(request.args.values())
    dados.extend(request.form.values())
    dados.extend((request.view_args or {}).values())
    if request.is_json:
        dados.append(request.get_json(silent=True))
    taints = tuple(dict.fromkeys(v for dado in dados for v in _valores(dado)))[:40]
    _contexto.set((request.url_rule.rule if request.url_rule else "rota_desconhecida", taints))


def _limpar_requisicao(_erro):
    _contexto.set(None)
    _salvar()


def _registrar(tipo, severidade=None):
    contexto = _contexto.get()
    if contexto is None:
        return
    with _lock:
        _contagens[tipo] += 1
        if severidade and len(_achados) < 100:
            _achados.append({"tipo": tipo, "severidade": severidade,
                             "rota": contexto[0]})


def _contaminado(texto, taints):
    texto = texto.casefold()
    # Evita confundir valor "unidade" com a coluna unidade_medida. O valor
    # precisa aparecer como token/literal, não como parte de um identificador.
    return any(re.search(r"(?<![\w])" + re.escape(valor) + r"(?![\w])", texto)
               for valor in taints)


def _auditoria(evento, argumentos):
    contexto = _contexto.get()
    if contexto is None:
        return
    if evento in ("subprocess.Popen", "os.system"):
        _registrar("processo_iniciado", "ALTA")
    elif evento in ("compile", "exec"):
        _registrar("codigo_dinamico")
        fonte = argumentos[0] if argumentos else None
        if evento == "compile" and isinstance(fonte, (str, bytes)):
            if _contaminado(fonte.decode("utf-8", "ignore") if isinstance(fonte, bytes)
                            else fonte, contexto[1]):
                _registrar("codigo_com_dado_da_requisicao", "ALTA")
        elif evento == "exec" and hasattr(fonte, "co_consts"):
            literais = " ".join(v for v in fonte.co_consts if isinstance(v, str))
            if _contaminado(literais, contexto[1]):
                _registrar("codigo_com_dado_da_requisicao", "ALTA")
    elif evento == "open" and argumentos:
        caminho = argumentos[0]
        if isinstance(caminho, (str, bytes, os.PathLike)) and not _dentro(caminho):
            _registrar("arquivo_fora_das_pastas_permitidas", "ALTA")
    elif evento == "socket.connect" and len(argumentos) > 1:
        endereco = argumentos[1]
        if isinstance(endereco, tuple) and endereco and str(endereco[0]).lower() not in _hosts_locais:
            _registrar("socket_fora_da_allowlist", "ALTA")


def _sql(_conn, _cursor, statement, _parameters, _context, _executemany):
    contexto = _contexto.get()
    if contexto is None or not contexto[1]:
        return
    _registrar("sql_observado")
    # SQLAlchemy normalmente usa placeholders. O achado só ocorre se o valor da
    # requisição entrou literalmente no texto SQL, independentemente dos parâmetros.
    if re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", statement, re.I):
        if _contaminado(statement, contexto[1]):
            _registrar("sql_literal_com_dado_da_requisicao", "ALTA")


def snapshot():
    with _lock:
        return _snapshot_desbloqueado()


def _snapshot_desbloqueado():
    return {"versao": 1, "data": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(), "eventos": dict(_contagens),
            "achados": list(_achados)}


def _salvar():
    pasta = Path(os.getenv("RECONECTA_IAST_REPORT_DIR", tempfile.gettempdir()))
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"iast-{os.getpid()}.json"
    temporario = pasta / f".iast-{os.getpid()}.tmp"
    with _lock:
        temporario.write_text(json.dumps(_snapshot_desbloqueado(), ensure_ascii=False,
                                        indent=2) + "\n", encoding="utf-8")
        temporario.replace(destino)


def instalar(app, db):
    global _instalado
    if os.getenv("RECONECTA_IAST") != "1" or _instalado:
        return
    app.before_request(_marcar_requisicao)
    app.teardown_request(_limpar_requisicao)
    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", _sql)
    sys.addaudithook(_auditoria)
    atexit.register(_salvar)
    _instalado = True
