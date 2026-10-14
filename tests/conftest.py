"""Testes nunca consultam serviços de geocodificação externos (Nominatim, BrasilAPI)."""
import os

os.environ["GEO_EXTERNO"] = "0"
os.environ["GROQ_API_KEY"] = ""  # a suíte só usa respostas Groq simuladas
