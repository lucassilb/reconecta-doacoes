"""Configuração do gunicorn lida automaticamente (./gunicorn.conf.py na pasta /app).

Log de acesso reduzido ao mínimo: método, caminho SEM query string, status, bytes e
duração. Sem IP, usuário, referer, user-agent nem query (%(h)s, %(u)s, %(f)s, %(a)s,
%(q)s, %(r)s ficam de fora). O caminho ainda passa pela máscara de registro.py
(ex.: /reconecta/cadastro/cnpj/<cnpj> sai como /reconecta/cadastro/cnpj/[cnpj]).
"""

import os

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").strip().lower() or "info"
access_log_format = '%(m)s %(U)s %(s)s %(b)s %(M)sms'
