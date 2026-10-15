"""Geo e rotas: localização sem rede, distância no casamento, avisos por proximidade e rota."""
import itertools
import json
import os
import random
from datetime import timedelta

import pytest
import requests

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from foto_oferta import com_foto  # noqa: E402
import geo  # noqa: E402
from conexao import casar  # noqa: E402
from eventos import Evento  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from models import Doacao, Estabelecimento, Excedente, ItemDoacao, ItemExcedente, db  # noqa: E402

# Pontos reais aproximados (lat, lon) para fixar coordenadas de endereço no cache.
PAULISTA = (-23.5615, -46.6560)
PINHEIROS = (-23.5670, -46.6930)      # ~3,8 km da Paulista
SANTO_ANDRE = (-23.6639, -46.5383)    # ~17 km
CAMPINAS = (-22.9056, -47.0608)       # ~84 km
RIO = (-22.9068, -43.1729)            # ~360 km


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def org(nome, cnpj, endereco, *, ong=False, alimentar=False, ponto=None):
    item = Estabelecimento(nome=nome, cnpj=cnpj, email=f"{cnpj}@exemplo.test",
                           telefone="11999999999", endereco=endereco,
                           sem_fins_lucrativos=ong, atividade_alimentar=alimentar)
    db.session.add(item)
    if ponto:
        geo.gravar(endereco, (*ponto, "endereco", "teste"))
    db.session.flush()
    return item


def pedido_de(organizacao, nome="Pão", categoria="Padaria", quantidade=50, unidade="kg"):
    pedido = Doacao(estabelecimento_id=organizacao.id,
                    data_limite_retirada=agora_brasilia_sem_fuso() + timedelta(days=2))
    db.session.add(pedido)
    db.session.flush()
    db.session.add(ItemDoacao(doacao_id=pedido.id, nome=nome, categoria=categoria,
                              quantidade=quantidade, unidade_medida=unidade))
    return pedido


def sessao(cliente, tipo, id_):
    with cliente.session_transaction() as atual:
        atual["tipo"] = tipo
        atual["usuario_id"] = id_


def anuncio(horas=2):
    prazo = agora_brasilia_sem_fuso() + timedelta(hours=horas)
    return {"retirar_ate": prazo.isoformat(timespec="seconds"),
            "itens": [{"nome": "Pão", "categoria": "Padaria", "quantidade": 4,
                       "unidade_medida": "kg", "validade": (prazo.date() + timedelta(days=1)).isoformat()}],
            "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True}


# ---------------- funções puras ----------------

def test_endereco_do_cadastro_vira_partes_e_centroide_do_ibge():
    partes = geo.partes_endereco("AVENIDA PAULISTA, 1578, ANDAR 2 - BELA VISTA, SAO PAULO/SP - 01310200")
    assert partes == {"logradouro": "AVENIDA PAULISTA", "numero": "1578", "municipio": "SAO PAULO",
                      "uf": "SP", "cep": "01310200"}
    assert geo.partes_endereco("Rua A, S/N - Centro, Barueri/SP")["numero"] is None
    assert geo.centroide("SAO PAULO", "sp") == pytest.approx((-23.5329, -46.6395))
    assert geo.centroide("Campinas", "RJ") is None  # município inexistente na UF
    assert len(geo._municipios()) > 5500


def test_haversine_e_texto_da_distancia():
    assert geo.haversine_km(PAULISTA, RIO) == pytest.approx(361, abs=5)
    assert geo.haversine_km(PAULISTA, PAULISTA) == 0
    assert geo.texto_distancia(0.4) == "a menos de 1 km"
    assert geo.texto_distancia(3.44) == "a 3,4 km"
    assert geo.texto_distancia(84.6, True) == "a cerca de 85 km"
    assert geo.texto_distancia(0.0, True) == "na mesma cidade"


def _pedido_casar(id_, municipio_uf, km=None):
    pedido = {"id": id_, "empresa": {"nome": f"ONG {id_}", "municipio_uf": municipio_uf},
              "receber_ate": None, "estabelecimento_id": id_,
              "itens": [{"id": id_ * 10, "nome": "pão", "categoria": "Padaria",
                         "quantidade": 50, "unidade_medida": "kg", "faltam": 50}]}
    if km is not None:
        pedido["distancia_km"], pedido["distancia_aproximada"] = km, False
    return pedido


def test_casar_premia_proximidade_e_mostra_a_distancia():
    oferta = [{"nome": "pão", "categoria": "Padaria", "quantidade": 10, "unidade_medida": "kg"}]
    perto, medio, longe = (_pedido_casar(1, "Rio de Janeiro/RJ", 360),
                           _pedido_casar(2, "Santo André/SP", 16),
                           _pedido_casar(3, "São Paulo/SP", 3.8))
    sugestoes = casar(oferta, [perto, medio, longe], uf="SP")
    assert [s["pedido_id"] for s in sugestoes] == [3, 2, 1]
    assert "a 3,8 km" in sugestoes[0]["motivos"] and sugestoes[0]["distancia_km"] == 3.8
    assert "mesma UF" not in sugestoes[0]["motivos"]
    assert sugestoes[0]["pontuacao"] > sugestoes[1]["pontuacao"] > sugestoes[2]["pontuacao"]
    # sem distância anotada continua a regra de UF de antes
    sem_geo = casar(oferta, [_pedido_casar(4, "São Paulo/SP")], uf="SP")
    assert "mesma UF" in sem_geo[0]["motivos"] and "distancia_km" not in sem_geo[0]


def test_rota_2opt_chega_no_otimo_em_casos_pequenos():
    sorteio = random.Random(7)
    for _ in range(25):
        partida = (sorteio.uniform(-24, -23), sorteio.uniform(-47, -46))
        pontos = [(sorteio.uniform(-24, -23), sorteio.uniform(-47, -46)) for _ in range(6)]
        ordem = geo.ordenar_rota(partida, pontos)
        assert sorted(ordem) == list(range(6))
        otimo = min(geo._comprimento(partida, pontos, list(p)) for p in itertools.permutations(range(6)))
        assert geo._comprimento(partida, pontos, ordem) <= otimo * 1.08
    # caso em que o vizinho mais próximo cruza o caminho e o 2-opt desfaz
    partida = (0.0, 0.0)
    pontos = [(0.0, 1.0), (0.0, -1.1), (0.0, 2.0), (0.0, -2.2)]
    ordem = geo.ordenar_rota(partida, pontos)
    vizinho = [0, 1, 2, 3]
    assert geo._comprimento(partida, pontos, ordem) < geo._comprimento(partida, pontos, vizinho)
    assert geo.ordenar_rota(partida, []) == []


# ---------------- consulta externa (simulada, nunca rede de verdade) ----------------

class _Resposta:
    def __init__(self, dados):
        self.dados = dados

    def raise_for_status(self):
        pass

    def json(self):
        return self.dados


def test_geocodificar_usa_nominatim_brasilapi_e_cai_no_centroide(monkeypatch):
    endereco = "Avenida Paulista, 1578 - Bela Vista, São Paulo/SP - 01310200"
    chamadas = []
    monkeypatch.setattr(geo, "INTERVALO_NOMINATIM", 0)

    def falso(url, params=None, timeout=None, headers=None, allow_redirects=None):
        chamadas.append((url, headers["User-Agent"]))
        if "nominatim" in url:
            return _Resposta(respostas["nominatim"])
        return _Resposta(respostas["brasilapi"])

    monkeypatch.setattr(geo.requests, "get", falso)
    respostas = {"nominatim": [{"lat": "-23.5615", "lon": "-46.6560"}], "brasilapi": {}}
    assert geo.geocodificar(endereco) == (-23.5615, -46.656, "endereco", "nominatim")
    assert "ReConecta" in chamadas[0][1]
    # Nominatim vazio → CEP da BrasilAPI
    respostas = {"nominatim": [], "brasilapi": {"location": {"coordinates": {
        "latitude": "-23.5617", "longitude": "-46.6553"}}}}
    assert geo.geocodificar(endereco)[2:] == ("cep", "brasilapi")
    # CEP devolvendo a sede do município não conta como precisão de CEP
    respostas = {"nominatim": [], "brasilapi": {"location": {"coordinates": {
        "latitude": "-23.5329", "longitude": "-46.6395"}}}}
    assert geo.geocodificar(endereco)[2:] == ("municipio", "ibge")
    # resultado em outra cidade (> 60 km da sede) é descartado
    respostas = {"nominatim": [{"lat": "-22.9068", "lon": "-43.1729"}], "brasilapi": {}}
    assert geo.geocodificar(endereco)[2:] == ("municipio", "ibge")

    def fora_do_ar(*_a, **_k):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(geo.requests, "get", fora_do_ar)
    assert geo.geocodificar(endereco)[2:] == ("municipio", "ibge")
    assert geo.geocodificar("Endereço sem município") is None


def test_cache_nao_troca_precisao_melhor_por_pior_e_localizar_nao_usa_rede(monkeypatch):
    endereco = "Rua A, 1 - Centro, Campinas/SP - 13010000"
    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: pytest.fail("localizar não pode usar rede"))
    with app.app_context():
        assert geo.localizar(endereco).precisao == "municipio"
        geo.gravar(endereco, (*CAMPINAS, "endereco", "nominatim"))
        geo.gravar(endereco, (0.0, 0.0, "municipio", "ibge"))
        db.session.commit()
        ponto = geo.localizar(endereco)
        assert (tuple(ponto), ponto.precisao) == (CAMPINAS, "endereco")
        assert geo.Geolocalizacao.query.count() == 1


def test_cadastro_agenda_refinamento_depois_do_commit_e_nao_bloqueia(monkeypatch):
    agendados = []
    monkeypatch.setattr(geo, "agendar", agendados.append)
    with app.app_context():
        nova = org("ONG Nova", "12345678000195", "Rua B, 2 - Centro, Santos/SP - 11010000", ong=True)
        assert agendados == []  # nada antes do commit
        db.session.commit()
        assert agendados == ["Rua B, 2 - Centro, Santos/SP - 11010000"]
        nova.telefone = "11888888888"
        db.session.commit()
        assert len(agendados) == 1  # editar outro campo não reconsulta
        nova.endereco = "Rua C, 3 - Centro, Santos/SP - 11010000"
        db.session.commit()
        assert agendados[-1].startswith("Rua C")


def test_fila_desligada_nos_testes_e_trabalhador_grava(monkeypatch):
    with app.app_context():
        assert geo.agendar("Rua A, 1 - Centro, Santos/SP") is False  # GEO_EXTERNO=0
    monkeypatch.setenv("GEO_EXTERNO", "1")
    monkeypatch.setattr(geo, "geocodificar", lambda e: (*PAULISTA, "endereco", "nominatim"))
    with app.app_context():
        assert geo.agendar("Rua A, 1 - Centro, Santos/SP") is True
    geo._fila.join()
    with app.app_context():
        assert geo.localizar("Rua A, 1 - Centro, Santos/SP", refinar=False).precisao == "endereco"


# ---------------- assistente e excedentes ----------------

def test_assistente_usa_distancia_da_empresa_e_da_localizacao_do_doador():
    with app.app_context():
        perto = org("ONG Pinheiros", "11111111000191", "Rua P, 1 - Pinheiros, São Paulo/SP", ong=True, ponto=PINHEIROS)
        longe = org("ONG Campinas", "22222222000191", "Rua C, 1 - Centro, Campinas/SP", ong=True, ponto=CAMPINAS)
        padaria = org("Padaria", "33333333000191", "Av P, 1 - Bela Vista, São Paulo/SP", alimentar=True, ponto=PAULISTA)
        pedido_de(longe, nome="pão", quantidade=60, unidade="unidade")
        pedido_de(perto, nome="pão", quantidade=40, unidade="unidade")
        from models import Doador
        pessoa = Doador(nome="Ana", cpf="52998224725", email="ana@exemplo.test", telefone="11999999999")
        db.session.add(pessoa)
        db.session.commit()
        padaria_id, pessoa_id = padaria.id, pessoa.id
    cliente = app.test_client()
    sessao(cliente, "empresa", padaria_id)
    corpo = cliente.post("/reconecta/ia/sugerir-destino", json={"texto": "sobraram 30 pães"}).json
    assert corpo["origem"] == {"precisao": "endereco"}
    assert [s["organizacao"] for s in corpo["sugestoes"]] == ["ONG Pinheiros", "ONG Campinas"]
    assert "a 3,8 km" in corpo["sugestoes"][0]["motivos"]
    assert corpo["sugestoes"][1]["distancia_km"] == pytest.approx(84, abs=2)

    pessoa_cliente = app.test_client()
    sessao(pessoa_cliente, "doador", pessoa_id)
    sem_local = pessoa_cliente.post("/reconecta/ia/sugerir-destino", json={"texto": "tenho 30 pães"}).json
    assert sem_local["origem"] is None and "distancia_km" not in sem_local["sugestoes"][0]
    em_campinas = pessoa_cliente.post("/reconecta/ia/sugerir-destino", json={
        "texto": "tenho 30 pães", "origem": {"latitude": CAMPINAS[0], "longitude": CAMPINAS[1]}}).json
    assert em_campinas["origem"] == {"precisao": "dispositivo"}
    assert em_campinas["sugestoes"][0]["organizacao"] == "ONG Campinas"
    assert "a menos de 1 km" in em_campinas["sugestoes"][0]["motivos"]
    fora = pessoa_cliente.post("/reconecta/ia/sugerir-destino", json={
        "texto": "tenho 30 pães", "origem": {"latitude": 48.85, "longitude": 2.35}}).json
    assert fora["origem"] is None  # fora do Brasil: ignorado
    with app.app_context():
        assert geo.Geolocalizacao.query.count() == 3  # a localização do doador não é gravada


def test_avisos_de_excedente_vao_das_ongs_mais_proximas_com_distancia():
    with app.app_context():
        mercado = org("Mercado", "44444444000191", "Av P, 2 - Bela Vista, São Paulo/SP", alimentar=True, ponto=PAULISTA)
        ongs = {
            "campinas": org("ONG Campinas", "55555555000191", "Rua C, 2 - Centro, Campinas/SP", ong=True, ponto=CAMPINAS),
            "pinheiros": org("ONG Pinheiros", "66666666000191", "Rua P, 2 - Pinheiros, São Paulo/SP", ong=True, ponto=PINHEIROS),
            "santo_andre": org("ONG ABC", "77777777000191", "Rua S, 2 - Centro, Santo André/SP", ong=True, ponto=SANTO_ANDRE),
            "rio": org("ONG Rio", "88888888000191", "Rua R, 2 - Centro, Rio de Janeiro/RJ", ong=True, ponto=RIO),
        }
        for ong in ongs.values():
            pedido_de(ong)
        db.session.commit()
        mercado_id = mercado.id
        esperados = [ongs[n].id for n in ("pinheiros", "santo_andre", "campinas")]
    cliente = app.test_client()
    sessao(cliente, "empresa", mercado_id)
    assert cliente.post("/reconecta/excedentes", data=com_foto(anuncio())).status_code == 201
    with app.app_context():
        privados = Evento.query.filter_by(tipo="excedente.publicado", publico=False).order_by(Evento.id).all()
        assert [e.dest_id for e in privados] == esperados  # Rio fica fora (outra UF e > 50 km)
        dados = [json.loads(e.dados) for e in privados]
        assert [d["distancia"] for d in dados] == ["a 3,8 km", "a 17 km", "a 84 km"]
        publico = Evento.query.filter_by(tipo="excedente.publicado", publico=True).one()
        assert "distancia" not in json.loads(publico.dados)


def test_aviso_cruza_a_divisa_quando_a_ong_esta_perto_e_respeita_o_limite():
    import Excedentes
    with app.app_context():
        # Divisa SP × MG: Extrema/MG fica a ~30 km de Bragança Paulista/SP
        mercado = org("Mercado", "44444444000191", "Rua M, 1 - Centro, Bragança Paulista/SP", alimentar=True)
        vizinha = org("ONG Extrema", "55555555000191", "Rua E, 1 - Centro, Extrema/MG", ong=True)
        pedido_de(vizinha)
        db.session.commit()
        origem = geo.localizar(mercado.endereco, refinar=False)
        oferta = [{"nome": "Pão", "categoria": "Padaria", "quantidade": 3, "unidade_medida": "kg"}]
        proximas = Excedentes._ongs_proximas(oferta, "SP", mercado.id, origem)
        assert [p[0] for p in proximas] == [vizinha.id] and proximas[0][2] is True
        assert Excedentes._ongs_compativeis(oferta, "SP", mercado.id) == ()  # sem origem: só UF
        for numero in range(12):
            outra = org(f"ONG {numero}", f"9{numero:02d}45678000191"[:14], f"Rua {numero}, 1 - Centro, Bragança Paulista/SP", ong=True)
            pedido_de(outra)
        db.session.commit()
        assert len(Excedentes._ongs_proximas(oferta, "SP", mercado.id, origem)) == Excedentes.MAX_AVISOS


def test_pagina_do_excedente_mostra_distancia_so_para_outra_organizacao():
    with app.app_context():
        mercado = org("Mercado", "44444444000191", "Av P, 3 - Bela Vista, São Paulo/SP", alimentar=True, ponto=PAULISTA)
        ong = org("ONG ABC", "77777777000191", "Rua S, 3 - Centro, Santo André/SP", ong=True, ponto=SANTO_ANDRE)
        db.session.commit()
        mercado_id, ong_id = mercado.id, ong.id
    publicador = app.test_client()
    sessao(publicador, "empresa", mercado_id)
    id_ = publicador.post("/reconecta/excedentes", data=com_foto(anuncio())).json["id"]
    assert "distancia" not in publicador.get(f"/reconecta/excedentes/{id_}").json
    assert "distancia" not in app.test_client().get(f"/reconecta/excedentes/{id_}").json
    visitante_ong = app.test_client()
    sessao(visitante_ong, "empresa", ong_id)
    detalhe = visitante_ong.get(f"/reconecta/excedentes/{id_}").json
    assert detalhe["distancia"] == "a 17 km" and detalhe["distancia_km"] == pytest.approx(16.6, abs=0.5)


# ---------------- rota de coleta ----------------

def test_rota_de_coleta_ordena_reservas_da_ong():
    with app.app_context():
        ong = org("ONG Centro", "11111111000191", "Rua O, 1 - Bela Vista, São Paulo/SP", ong=True, ponto=PAULISTA)
        lojas = {nome: org(f"Loja {nome}", cnpj, f"Rua {nome}, 1 - Centro, {cidade}", alimentar=True, ponto=ponto)
                 for nome, cnpj, cidade, ponto in (
                     ("Campinas", "22222222000191", "Campinas/SP", CAMPINAS),
                     ("Pinheiros", "33333333000191", "São Paulo/SP", PINHEIROS),
                     ("ABC", "44444444000191", "Santo André/SP", SANTO_ANDRE),
                     ("SemMapa", "55555555000191", "Cidade Inventada/ZZ", None))}
        outra = org("Outra ONG", "66666666000191", "Rua X, 1 - Centro, São Paulo/SP", ong=True)
        agora = agora_brasilia_sem_fuso()
        for nome, loja in lojas.items():
            excedente = Excedente(estabelecimento_id=loja.id, retirar_ate=agora + timedelta(hours=5),
                                  status="RESERVADO", reservado_por_id=ong.id, reservado_em=agora)
            excedente.itens = [ItemExcedente(nome=f"Pão {nome}", categoria="Padaria", quantidade=2,
                                             unidade_medida="kg", validade=agora.date() + timedelta(days=1))]
            db.session.add(excedente)
        vencido = Excedente(estabelecimento_id=lojas["ABC"].id, retirar_ate=agora - timedelta(hours=1),
                            status="RESERVADO", reservado_por_id=ong.id, reservado_em=agora)
        de_outra = Excedente(estabelecimento_id=lojas["ABC"].id, retirar_ate=agora + timedelta(hours=5),
                             status="RESERVADO", reservado_por_id=outra.id, reservado_em=agora)
        db.session.add_all([vencido, de_outra])
        db.session.commit()
        ong_id, loja_id = ong.id, lojas["ABC"].id
    assert app.test_client().get("/reconecta/excedentes/rota").status_code == 401
    loja = app.test_client()
    sessao(loja, "empresa", loja_id)
    assert loja.get("/reconecta/excedentes/rota").status_code == 403
    cliente = app.test_client()
    sessao(cliente, "empresa", ong_id)
    rota = cliente.get("/reconecta/excedentes/rota").json
    assert sorted(p["empresa"] for p in rota["paradas"]) == ["Loja ABC", "Loja Campinas", "Loja Pinheiros"]
    # o percurso fechado é o menor entre todas as ordens possíveis
    pontos = [PINHEIROS, SANTO_ANDRE, CAMPINAS]
    otimo = min(geo._comprimento(PAULISTA, pontos, list(o)) for o in itertools.permutations(range(3)))
    assert rota["total_km"] == pytest.approx(otimo, abs=0.2)
    assert [p["ordem"] for p in rota["paradas"]] == [1, 2, 3]
    assert [s["empresa"] for s in rota["sem_localizacao"]] == ["Loja SemMapa"]
    assert rota["total_km"] == pytest.approx(rota["paradas"][-1]["acumulado_km"] + rota["retorno_km"], abs=0.11)
    assert rota["paradas"][0]["link_osm"].startswith("https://www.openstreetmap.org/directions?")
    assert rota["link_rota"].count("loc=") == 5  # partida, 3 paradas e volta
    assert rota["aproximada"] is False and "2-opt" in rota["metodo"]


def test_cep_do_doador_localiza_com_cache_e_falha_sem_bloquear(monkeypatch):
    consultas = []

    def falso(url, params=None):
        consultas.append(url)
        if "13010" in url:
            return {"city": "Campinas", "state": "SP", "location": {"coordinates": {
                "latitude": str(CAMPINAS[0]), "longitude": str(CAMPINAS[1])}}}
        raise requests.ConnectionError("fora do ar")

    monkeypatch.setattr(geo, "_get_json", falso)
    with app.app_context():
        assert geo.localizar_cep("13010-001") is None  # GEO_EXTERNO=0: não consulta
        monkeypatch.setenv("GEO_EXTERNO", "1")
        ponto = geo.localizar_cep("13010-001")
        assert ponto.precisao == "municipio"  # a coordenada do CEP é a sede de Campinas
        assert geo.localizar_cep("13010001").precisao == "municipio"
        assert len(consultas) == 1  # segunda vez veio do cache
        assert geo.localizar_cep("99999999") is None  # serviço fora do ar
        assert geo.localizar_cep("123") is None
        linha = geo.Geolocalizacao.query.filter_by(chave=geo.chave("cep:13010001")).one()
        assert linha.fonte == "ibge"
        perto = org("ONG Campinas", "22222222000191", "Rua C, 1 - Centro, Campinas/SP", ong=True, ponto=CAMPINAS)
        pedido_de(perto, nome="pão", quantidade=40, unidade="unidade")
        from models import Doador
        pessoa = Doador(nome="Bia", cpf="52998224725", email="bia@exemplo.test", telefone="11999999999")
        db.session.add(pessoa)
        db.session.commit()
        pessoa_id = pessoa.id
    cliente = app.test_client()
    sessao(cliente, "doador", pessoa_id)
    corpo = cliente.post("/reconecta/ia/sugerir-destino", json={"texto": "tenho 30 pães", "cep": "13010-001"}).json
    assert corpo["origem"] == {"precisao": "municipio"}
    assert corpo["sugestoes"][0]["distancia"] == "na mesma cidade"
    falhou = cliente.post("/reconecta/ia/sugerir-destino", json={"texto": "tenho 30 pães", "cep": "99999999"})
    assert falhou.status_code == 200 and falhou.json["origem"] is None and falhou.json["sugestoes"]


def test_rota_comeca_pela_parada_mais_perto_quando_o_inverso_empata():
    partida = PAULISTA
    pontos = [SANTO_ANDRE, CAMPINAS, (-23.5559, -46.6579)]  # a terceira fica a 0,7 km da partida
    ordem = geo.ordenar_rota(partida, pontos)
    assert ordem[0] == 2
    assert geo._comprimento(partida, pontos, ordem) == pytest.approx(
        geo._comprimento(partida, pontos, ordem[::-1]))
