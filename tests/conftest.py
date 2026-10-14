"""Testes nunca consultam serviços de geocodificação externos (Nominatim, BrasilAPI)."""
import os

os.environ["GEO_EXTERNO"] = "0"
