"""Conversão entre eventos armazenados em UTC e prazos locais de Brasília."""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


BRASILIA = ZoneInfo("America/Sao_Paulo")


def agora_brasilia():
    return datetime.now(BRASILIA)


def hoje_brasilia():
    return agora_brasilia().date()


def agora_brasilia_sem_fuso():
    """Para comparar com prazos DATETIME gravados como hora local sem offset."""
    return agora_brasilia().replace(tzinfo=None)


def utc_para_brasilia(valor):
    """Converte evento DATETIME UTC sem timezone vindo do banco."""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(BRASILIA)


def iso_evento(valor):
    return utc_para_brasilia(valor).isoformat(timespec="seconds") if valor else None


def iso_prazo(valor):
    """Prazo DATETIME do formulário já representa a hora civil de Brasília."""
    return valor.replace(tzinfo=BRASILIA).isoformat(timespec="seconds") if valor else None


def inicio_dia_utc(dia):
    return (datetime.combine(dia, time.min, BRASILIA)
            .astimezone(timezone.utc).replace(tzinfo=None))
