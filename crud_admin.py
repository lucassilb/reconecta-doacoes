"""Autorização administrativa dos CRUDs legados do CP1."""

import hmac
import os

from flask import request


def token_admin_valido():
    configurado = os.getenv("ADMIN_TOKEN", "")
    recebido = request.headers.get("X-Admin-Token", "")
    return bool(configurado.strip() and
                hmac.compare_digest(recebido, configurado))


def exigir_admin():
    if not os.getenv("ADMIN_TOKEN", "").strip():
        return {"codigo": "ADMIN_DESATIVADO",
                "mensagem": "Escrita administrativa desativada: configure ADMIN_TOKEN."}, 403
    if not token_admin_valido():
        return {"codigo": "ADMIN_NAO_AUTORIZADO",
                "mensagem": "Informe um X-Admin-Token válido."}, 401
    return None
