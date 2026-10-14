"""Log mínimo: rede de segurança central que mascara dados pessoais em qualquer log.

`configurar_logs()` troca a fábrica de LogRecord do processo: toda mensagem (Flask,
gunicorn, Werkzeug, SQLAlchemy, módulos do projeto) e todo traceback passam por
`pii.mascarar` no momento em que o registro é criado, antes de qualquer handler.
Os módulos continuam responsáveis por não logar nome, endereço nem texto livre
(sem formato fixo, a máscara não os reconhece); veja docs/lgpd.md, "Logs".
"""

import logging
import os
import traceback

from pii import mascarar

_fabrica_original = None


def _registro_mascarado(*args, **kwargs):
    registro = _fabrica_original(*args, **kwargs)
    try:
        mensagem = registro.getMessage()
    except Exception:  # noqa: BLE001 - mensagem malformada não pode derrubar o log
        mensagem = str(registro.msg)
    registro.msg, registro.args = mascarar(mensagem), ()
    if registro.exc_info and registro.exc_info[0] is not None and not registro.exc_text:
        texto = "".join(traceback.format_exception(*registro.exc_info)).rstrip("\n")
        registro.exc_text = mascarar(texto)
    if registro.stack_info:
        registro.stack_info = mascarar(registro.stack_info)
    return registro


def configurar_logs(app=None):
    """Instala a máscara (uma vez por processo) e o nível INFO, ou LOG_LEVEL."""
    global _fabrica_original
    if _fabrica_original is None:
        _fabrica_original = logging.getLogRecordFactory()
        logging.setLogRecordFactory(_registro_mascarado)
    nivel = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if nivel not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        nivel = "INFO"
    if app is not None:
        app.logger.setLevel(nivel)
    for nome in ("reconecta", "llm_service"):
        logging.getLogger(nome).setLevel(nivel)
