"""Localização aproximada de organizações, distância e rota de coleta, sem API paga.

Ordem das fontes para um endereço (texto "Logradouro, nº - Bairro, Município/UF - CEP"):
1. cache na tabela `geolocalizacoes` (chave = SHA-256 do endereço normalizado);
2. centróide do município (data/municipios.csv, IBGE, offline e instantâneo);
3. em segundo plano, quando `GEO_EXTERNO` não é "0": Nominatim/OpenStreetMap
   (1 consulta por segundo, User-Agent próprio) e BrasilAPI CEP v2. O resultado
   refinado substitui o centróide no cache.

Nenhuma rota espera a rede: quem precisa de coordenada usa o cache ou o centróide e
pede o refinamento à fila. Se a rede falhar, fica o centróide e nada é bloqueado.
"""

import csv
import hashlib
import logging
import math
import os
import queue
import re
import threading
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

import requests
from sqlalchemy import event, inspect as inspecionar
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, object_session

from conexao import texto_distancia  # noqa: F401  (reexportado)
from models import Estabelecimento, _utc_naive, db

RAIZ = Path(__file__).resolve().parent
USER_AGENT = "ReConecta/1.0 (projeto academico; +https://github.com/lucassilb/reconecta-doacoes)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
BRASILAPI_CEP = "https://brasilapi.com.br/api/cep/v2/{cep}"
INTERVALO_NOMINATIM = 1.1  # política de uso: no máximo 1 consulta por segundo
TIMEOUT = (3, 5)
LIMITE_FILA = 500
# Um resultado de endereço a mais de 60 km da sede do município informado é descartado.
DESVIO_MAXIMO_KM = 60
# Coordenada de CEP a menos de 1 km da sede do município costuma ser a própria sede.
SEDE_KM = 1.0

log = logging.getLogger("reconecta.geo")


class Geolocalizacao(db.Model):
    __tablename__ = "geolocalizacoes"
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(64), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    precisao = db.Column(db.String(12), nullable=False)  # endereco | cep | municipio
    fonte = db.Column(db.String(20), nullable=False)      # nominatim | brasilapi | ibge
    atualizado_em = db.Column(db.DateTime, nullable=False, default=_utc_naive)


# ---------------- texto ----------------

def _sem_acento(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or ""))
                   if not unicodedata.combining(c))


def _normalizar(texto):
    return re.sub(r"\s+", " ", _sem_acento(texto).lower()).strip()


def chave(endereco):
    return hashlib.sha256(_normalizar(endereco).encode("utf-8")).hexdigest()


def partes_endereco(endereco):
    """Separa o texto gravado no cadastro (Cadastro._endereco_texto)."""
    resultado = {"logradouro": None, "numero": None, "municipio": None, "uf": None, "cep": None}
    pedacos = [p.strip() for p in str(endereco or "").split(" - ") if p.strip()]
    for pedaco in pedacos:
        if re.fullmatch(r"\d{5}-?\d{3}", pedaco):
            resultado["cep"] = pedaco.replace("-", "")
            continue
        local = pedaco.rsplit(",", 1)[-1].strip()
        achado = re.fullmatch(r"([^,/]+)/([A-Za-z]{2})", local)
        if achado and resultado["municipio"] is None:
            resultado["municipio"], resultado["uf"] = achado.group(1).strip(), achado.group(2).upper()
            continue
        if resultado["logradouro"] is None:
            campos = [c.strip() for c in pedaco.split(",")]
            resultado["logradouro"] = campos[0] or None
            if len(campos) > 1 and re.match(r"^\d+[A-Za-z]?$", campos[1]):
                resultado["numero"] = campos[1]
    return resultado


# ---------------- municípios (IBGE) ----------------

@lru_cache(maxsize=1)
def _municipios():
    tabela = {}
    with open(RAIZ / "data" / "municipios.csv", encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            tabela[(_normalizar(linha["nome"]), linha["uf"])] = (
                float(linha["latitude"]), float(linha["longitude"]))
    return tabela


def centroide(municipio, uf):
    if not municipio or not uf:
        return None
    return _municipios().get((_normalizar(municipio), uf.upper()))


# ---------------- distância ----------------

def haversine_km(a, b):
    """Distância em linha reta entre (lat, lon) e (lat, lon), em km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(h)))


# ---------------- localizar ----------------

class Ponto(tuple):
    """(latitude, longitude) com a precisão de onde veio."""

    def __new__(cls, latitude, longitude, precisao):
        ponto = super().__new__(cls, (float(latitude), float(longitude)))
        ponto.precisao = precisao
        return ponto


def localizar(endereco, *, refinar=True):
    """Coordenada do endereço pelo cache ou pelo centróide do município; None se não houver.

    Não acessa a rede: quando só há o centróide, o endereço vai para a fila de refinamento.
    """
    if not endereco:
        return None
    try:
        linha = Geolocalizacao.query.filter_by(chave=chave(endereco)).first()
    except SQLAlchemyError:
        linha = None
    if linha:
        if linha.precisao == "municipio" and refinar:
            agendar(endereco)
        return Ponto(linha.latitude, linha.longitude, linha.precisao)
    partes = partes_endereco(endereco)
    sede = centroide(partes["municipio"], partes["uf"])
    if refinar:
        agendar(endereco)
    return Ponto(*sede, "municipio") if sede else None


def distancia(origem, destino):
    """(km, aproximada) entre dois Pontos; (None, None) se faltar um deles."""
    if origem is None or destino is None:
        return None, None
    aproximada = "municipio" in (getattr(origem, "precisao", None), getattr(destino, "precisao", None))
    return haversine_km(origem, destino), aproximada


def localizar_estabelecimentos(ids):
    """{id: Ponto} numa consulta só (endereços lidos do banco)."""
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    linhas = db.session.query(Estabelecimento.id, Estabelecimento.endereco).filter(
        Estabelecimento.id.in_(ids)).all()
    return {id_: localizar(endereco) for id_, endereco in linhas}


def anotar_distancias(pedidos, origem):
    """Acrescenta distancia_km/distancia_aproximada aos pedidos (formato de conexao.casar)."""
    if origem is None:
        return pedidos
    pontos = localizar_estabelecimentos(p.get("estabelecimento_id") for p in pedidos)
    for pedido in pedidos:
        km, aproximada = distancia(origem, pontos.get(pedido.get("estabelecimento_id")))
        if km is not None:
            pedido["distancia_km"], pedido["distancia_aproximada"] = round(km, 2), aproximada
    return pedidos


def localizar_cep(cep):
    """Ponto de um CEP digitado pela pessoa (assistente), com cache.

    Consulta a BrasilAPI só quando o CEP não está no cache e a rede está ligada; a
    coordenada do CEP, ou a sede do município dele, fica guardada sob o hash do CEP,
    sem ligação com quem consultou. Devolve None se não der para localizar.
    """
    cep = re.sub(r"\D", "", str(cep or ""))
    if len(cep) != 8:
        return None
    k = chave("cep:" + cep)
    linha = Geolocalizacao.query.filter_by(chave=k).first()
    if linha:
        return Ponto(linha.latitude, linha.longitude, linha.precisao)
    if not _externo_ligado():
        return None
    try:
        dados = _get_json(BRASILAPI_CEP.format(cep=cep))
    except (requests.RequestException, ValueError) as erro:
        log.warning("geo: CEP não consultado (%s)", type(erro).__name__)
        return None
    if not isinstance(dados, dict):
        return None
    sede = centroide(dados.get("city"), dados.get("state"))
    coordenadas = (dados.get("location") or {}).get("coordinates") or {}
    resultado = None
    try:
        achado = (float(coordenadas["latitude"]), float(coordenadas["longitude"]))
    except (KeyError, TypeError, ValueError):
        achado = None
    if achado and sede and SEDE_KM <= haversine_km(sede, achado) <= DESVIO_MAXIMO_KM:
        resultado = (*achado, "cep", "brasilapi")
    elif sede:
        resultado = (*sede, "municipio", "ibge")
    if not resultado:
        return None
    linha = Geolocalizacao(chave=k, latitude=resultado[0], longitude=resultado[1],
                           precisao=resultado[2], fonte=resultado[3])
    try:
        db.session.add(linha)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()  # outra requisição gravou o mesmo CEP: vale a dela
    return Ponto(resultado[0], resultado[1], resultado[2])


def ponto_informado(valor):
    """Valida {"latitude", "longitude"} enviado pelo navegador (território brasileiro)."""
    if not isinstance(valor, dict):
        return None
    try:
        lat, lon = float(valor.get("latitude")), float(valor.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-34.0 <= lat <= 5.5 and -74.5 <= lon <= -28.5):
        return None
    return Ponto(round(lat, 4), round(lon, 4), "dispositivo")


# ---------------- consulta externa (fila em segundo plano) ----------------

_ultimo_nominatim = 0.0
_trava_nominatim = threading.Lock()


def _externo_ligado():
    return os.getenv("GEO_EXTERNO", "1") != "0"


def _get_json(url, params=None):
    resposta = requests.get(url, params=params, timeout=TIMEOUT,
                            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                            allow_redirects=False)
    resposta.raise_for_status()
    return resposta.json()


def _nominatim(partes):
    global _ultimo_nominatim
    if not partes["municipio"] or not partes["logradouro"]:
        return None
    rua = " ".join(p for p in (partes["numero"], partes["logradouro"]) if p)
    params = {"format": "jsonv2", "limit": 1, "countrycodes": "br", "street": rua,
              "city": partes["municipio"], "state": partes["uf"]}
    with _trava_nominatim:
        espera = INTERVALO_NOMINATIM - (time.monotonic() - _ultimo_nominatim)
        if espera > 0:
            time.sleep(espera)
        try:
            dados = _get_json(NOMINATIM, params)
        finally:
            _ultimo_nominatim = time.monotonic()
    if isinstance(dados, list) and dados:
        return float(dados[0]["lat"]), float(dados[0]["lon"])
    return None


def _brasilapi(cep):
    if not cep:
        return None
    dados = _get_json(BRASILAPI_CEP.format(cep=cep))
    coordenadas = ((dados or {}).get("location") or {}).get("coordinates") or {}
    if coordenadas.get("latitude") and coordenadas.get("longitude"):
        return float(coordenadas["latitude"]), float(coordenadas["longitude"])
    return None


def geocodificar(endereco, *, externo=True):
    """Resolve o endereço consultando as fontes; devolve (lat, lon, precisao, fonte) ou None."""
    partes = partes_endereco(endereco)
    sede = centroide(partes["municipio"], partes["uf"])
    if externo:
        for fonte, consulta, precisao in (("nominatim", lambda: _nominatim(partes), "endereco"),
                                          ("brasilapi", lambda: _brasilapi(partes["cep"]), "cep")):
            try:
                achado = consulta()
            except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
                log.warning("geo: %s falhou (%s)", fonte, type(erro).__name__)
                continue
            if not achado:
                continue
            if sede:
                desvio = haversine_km(sede, achado)
                if desvio > DESVIO_MAXIMO_KM:
                    continue
                if precisao == "cep" and desvio < SEDE_KM:
                    break  # a "coordenada do CEP" é a sede: fica o centróide
            return achado[0], achado[1], precisao, fonte
    if sede:
        return sede[0], sede[1], "municipio", "ibge"
    return None


def gravar(endereco, resultado):
    """Insere ou atualiza o cache do endereço; não sobrescreve precisão melhor com pior."""
    if not resultado:
        return None
    ordem = {"municipio": 0, "cep": 1, "endereco": 2}
    lat, lon, precisao, fonte = resultado
    linha = Geolocalizacao.query.filter_by(chave=chave(endereco)).first()
    if linha and ordem.get(linha.precisao, 0) > ordem[precisao]:
        return linha
    if not linha:
        linha = Geolocalizacao(chave=chave(endereco))
        db.session.add(linha)
    linha.latitude, linha.longitude = lat, lon
    linha.precisao, linha.fonte, linha.atualizado_em = precisao, fonte, _utc_naive()
    return linha


_fila = queue.Queue(maxsize=LIMITE_FILA)
_na_fila = set()
_trava_fila = threading.Lock()
_trabalhador = None
_app = None


def agendar(endereco):
    """Pede o refinamento em segundo plano; ignora se a rede estiver desligada ou a fila cheia."""
    global _trabalhador, _app
    if not endereco or not _externo_ligado():
        return False
    try:
        from flask import current_app
        _app = current_app._get_current_object()
    except RuntimeError:
        return False
    k = chave(endereco)
    with _trava_fila:
        if k in _na_fila:
            return False
        try:
            _fila.put_nowait(endereco)
        except queue.Full:
            return False
        _na_fila.add(k)
        if _trabalhador is None or not _trabalhador.is_alive():
            _trabalhador = threading.Thread(target=_trabalhar, name="geo-refinar", daemon=True)
            _trabalhador.start()
    return True


def _trabalhar():
    while True:
        endereco = _fila.get()
        try:
            with _app.app_context():
                atual = Geolocalizacao.query.filter_by(chave=chave(endereco)).first()
                if not atual or atual.precisao == "municipio":
                    gravar(endereco, geocodificar(endereco))
                    db.session.commit()
        except Exception:  # o trabalhador não pode morrer por um endereço
            log.exception("geo: falha ao refinar um endereço")
        finally:
            with _trava_fila:
                _na_fila.discard(chave(endereco))
            _fila.task_done()


# Cadastro e edição de endereço disparam o refinamento depois do commit,
# sem tocar no fluxo do cadastro: se a rede falhar, nada muda para quem se cadastrou.
def _marcar(alvo):
    sessao = object_session(alvo)
    if sessao is not None and alvo.endereco:
        sessao.info.setdefault("geo_enderecos", set()).add(alvo.endereco)


@event.listens_for(Estabelecimento, "after_insert")
def _endereco_novo(_mapper, _conexao, alvo):
    _marcar(alvo)


@event.listens_for(Estabelecimento, "after_update")
def _endereco_editado(_mapper, _conexao, alvo):
    if inspecionar(alvo).attrs.endereco.history.has_changes():
        _marcar(alvo)


@event.listens_for(Session, "after_commit")
def _refinar_depois_do_commit(sessao):
    for endereco in sessao.info.pop("geo_enderecos", ()):
        agendar(endereco)


@event.listens_for(Session, "after_rollback")
def _descartar(sessao):
    sessao.info.pop("geo_enderecos", None)


# ---------------- rota de coleta ----------------

def _comprimento(partida, pontos, ordem, retorno=True):
    trajeto = [partida, *(pontos[i] for i in ordem)]
    total = sum(haversine_km(trajeto[i], trajeto[i + 1]) for i in range(len(trajeto) - 1))
    return total + (haversine_km(trajeto[-1], partida) if retorno and ordem else 0)


def ordenar_rota(partida, pontos, retorno=True):
    """Ordem de visita: vizinho mais próximo e depois 2-opt até não melhorar.

    `partida` e `pontos` são (lat, lon). Devolve a lista de índices de `pontos`.
    """
    restantes = list(range(len(pontos)))
    ordem, atual = [], partida
    while restantes:
        proximo = min(restantes, key=lambda i: (haversine_km(atual, pontos[i]), i))
        ordem.append(proximo)
        restantes.remove(proximo)
        atual = pontos[proximo]
    melhorou = True
    while melhorou and len(ordem) > 2:
        melhorou = False
        melhor = _comprimento(partida, pontos, ordem, retorno)
        for i in range(len(ordem) - 1):
            for j in range(i + 1, len(ordem)):
                candidata = ordem[:i] + ordem[i:j + 1][::-1] + ordem[j + 1:]
                comprimento = _comprimento(partida, pontos, candidata, retorno)
                if comprimento < melhor - 1e-9:
                    ordem, melhor, melhorou = candidata, comprimento, True
    # ida e volta: o percurso invertido tem o mesmo tamanho; começa pela parada mais perto
    if retorno and len(ordem) > 1 and (haversine_km(partida, pontos[ordem[-1]]) <
                                       haversine_km(partida, pontos[ordem[0]])):
        ordem.reverse()
    return ordem


def link_osm(trajeto):
    """Link do trecho a trecho no OpenStreetMap (ida entre dois pontos)."""
    (a, b) = trajeto
    return ("https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route="
            f"{a[0]:.5f}%2C{a[1]:.5f}%3B{b[0]:.5f}%2C{b[1]:.5f}")


def link_rota_completa(trajeto):
    """Rota com todas as paradas no mapa do OSRM (dados OpenStreetMap, sem chave)."""
    return "https://map.project-osrm.org/?" + "&".join(
        f"loc={lat:.5f}%2C{lon:.5f}" for lat, lon in trajeto) + "&srv=0"
