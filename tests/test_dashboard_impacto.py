"""Provas dos indicadores novos, sempre em SQLite descartável."""
import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
import Dashboard  # noqa: E402
from Dashboard import converter_kg, conversoes_kg  # noqa: E402
from models import (Contribuicao, Doacao, Doador, Estabelecimento, Excedente,
                    ItemDoacao, ItemExcedente, db)  # noqa: E402
from scripts.resumo_sast import contar_stride, contar_trivy, resumir  # noqa: E402


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def organizacao(nome, cnpj, uf):
    return Estabelecimento(nome=nome, cnpj=cnpj, email=f"{nome}@teste.local",
                           telefone="11111111111", endereco=f"Rua Um, 1 - Centro, Cidade/{uf} - 00000000",
                           sem_fins_lucrativos=True)


def test_conversao_por_unidade_e_categoria():
    tabela = conversoes_kg()
    assert converter_kg(250, "Outros", "g", tabela) == (0.250, "medido")
    assert converter_kg(2, "Hortifrúti", "caixa", tabela) == (20, "estimado")
    assert converter_kg(2, "Outros", "sem_regra", tabela) is None


def test_impacto_conta_so_entregue_e_retirado_por_uf_e_match():
    with app.app_context():
        sp = organizacao("ongsp", "12345678000195", "SP")
        pe = organizacao("ongpe", "23456789000189", "PE")
        mercado = organizacao("mercado", "34567890000110", "SP")
        doador = Doador(nome="Pessoa", cpf="52998224725", email="pessoa@teste.local", telefone="11111111111")
        db.session.add_all([sp, pe, mercado, doador])
        db.session.flush()
        inicio = datetime(2026, 10, 12, 12)
        pedidos = [Doacao(estabelecimento_id=ong.id, data_cadastro=inicio,
                          data_limite_retirada=datetime(2026, 10, 30)) for ong in (sp, pe)]
        db.session.add_all(pedidos)
        db.session.flush()
        itens = [ItemDoacao(doacao_id=pedidos[0].id, nome="Arroz", categoria="Grãos e cereais",
                            quantidade=10, unidade_medida="kg"),
                 ItemDoacao(doacao_id=pedidos[1].id, nome="Pão", categoria="Padaria",
                            quantidade=30, unidade_medida="unidade")]
        db.session.add_all(itens)
        db.session.flush()
        for idx, quantidade, status, hora in [(0, 2, "ENTREGUE", 14), (0, 5, "ACEITA", 15),
                                               (1, 10, "ENTREGUE", 13)]:
            item = itens[idx]
            db.session.add(Contribuicao(doacao_id=item.doacao_id, item_doacao_id=item.id,
                doador_id=doador.id, alimento=item.nome, categoria=item.categoria,
                quantidade=quantidade, unidade_medida=item.unidade_medida,
                validade=date(2026, 10, 30), respostas="{}", foto_arquivo="a.jpg",
                status=status, criado_em=datetime(2026, 10, 12, hora)))
        for status, minutos in [("RETIRADO", 60), ("RESERVADO", 30)]:
            e = Excedente(estabelecimento_id=mercado.id, reservado_por_id=pe.id,
                          retirar_ate=datetime(2026, 10, 30), status=status,
                          criado_em=inicio, reservado_em=inicio.replace(
                              hour=13 if minutos == 60 else 12,
                              minute=0 if minutos == 60 else 30))
            if status == "RETIRADO":
                e.itens = [ItemExcedente(nome="Verdura", categoria="Hortifrúti",
                         quantidade=2, unidade_medida="caixa", validade=date(2026, 10, 30)),
                           ItemExcedente(nome="Feijão", categoria="Grãos e cereais",
                         quantidade=1000, unidade_medida="g", validade=date(2026, 10, 30))]
            db.session.add(e)
        db.session.commit()

    resposta = app.test_client().get("/reconecta/dashboard/impacto")
    assert resposta.status_code == 200
    dados = resposta.json
    assert dados["peso"] == {"kg_medido": 3, "kg_estimado": 20.8,
                              "refeicoes_estimadas": 48, "itens_sem_conversao": 0}
    ufs = {r["uf"]: r for r in dados["refeicoes"]["por_uf"]}
    assert ufs["SP"]["kg_medido"] == 2
    assert ufs["PE"]["kg_medido"] == 1
    assert ufs["PE"]["kg_estimado"] == 20.8
    assert {r["regiao"] for r in dados["refeicoes"]["por_regiao"]} == {"Sudeste", "Nordeste"}
    assert dados["match"] == {"pedido_min": 120, "pedido_amostras": 3,
                              "excedente_min": 45, "excedente_amostras": 2,
                              "combinado_min": 90, "combinado_amostras": 5}
    assert sum(sum(dia) for dia in dados["calor_doacoes"]["valores"]) == 3
    assert dados["ia"]["metricas"]["acuracia_top1"] >= dados["ia"]["limiares"]["acuracia_top1"]
    assert "pessoa@" not in resposta.get_data(as_text=True)


def test_sast_e_stride_contam_achados_sem_confundir_residual_com_mitigado(tmp_path):
    assert contar_trivy({"Results": [{"Vulnerabilities": [{"Severity": "HIGH"}],
                                      "Secrets": [{}], "Misconfigurations": [{}, {}]}]}) == {
        "CRITICAL": 0, "HIGH": 1, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0,
        "segredos": 1, "configuracoes": 2}
    assert contar_stride("| S1 | risco | 2 | ✔ resolvido |\n| T2 | risco | 3 | ◐ residual |") == {
        "mitigados": 1, "residuais": 1, "fonte": "docs/stride.md; estado declarado por risco"}
    pasta = tmp_path / "relatorios" / "sast"
    pasta.mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "stride.md").write_text("| S1 | risco | 2 | ◐ aberto |", encoding="utf-8")
    (tmp_path / "docs" / "sast.md").write_text(
        "| pacote | CVE-2026-12345 | corrigido |\n| B104 | Corrigido |", encoding="utf-8")
    (pasta / "bandit.json").write_text(json.dumps({"generated_at": "2026-10-14",
          "results": [{"issue_severity": "MEDIUM"}]}), encoding="utf-8")
    resultado = resumir(tmp_path)
    assert resultado["ferramentas"]["bandit"]["severidades"]["MEDIUM"] == 1
    assert resultado["ferramentas"]["trivy-image"]["disponivel"] is False
    assert resultado["stride"]["residuais"] == 1
    assert resultado["correcoes_documentadas"]["cves_corrigidas"] == 1


def test_seguranca_publica_nao_inventa_contadores():
    resposta = app.test_client().get("/reconecta/dashboard/seguranca")
    assert resposta.status_code == 200
    assert resposta.json["controles"]["falhas_login"].startswith("Não medidas")
    assert resposta.json["sast"]["ferramentas"]["trivy-image"]["severidades"]["HIGH"] == 0
    gates = resposta.json["sast"]["gates"]
    assert gates
    assert all(set(gate) == {"rotulo", "resultado"} for gate in gates)
    assert all(gate["rotulo"] and gate["resultado"] in
               {"passou", "falhou", "sem_dados"} for gate in gates)
    assert "regra" not in resposta.get_data(as_text=True)
    assert "detalhe" not in resposta.get_data(as_text=True)


@pytest.mark.parametrize("cookie_seguro", [False, True])
def test_seguranca_declara_cabecalhos_da_resposta(monkeypatch, cookie_seguro):
    monkeypatch.setitem(app.config, "SESSION_COOKIE_SECURE", cookie_seguro)
    resposta = app.test_client().get("/reconecta/dashboard/seguranca")
    assert resposta.status_code == 200
    nomes = {"Content-Security-Policy", "X-Content-Type-Options",
             "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"}
    declarados = set(resposta.json["controles"]["cabecalhos"])
    assert declarados == nomes
    assert declarados == {nome for nome in nomes if resposta.headers.get(nome)}
    assert bool(resposta.headers.get("Strict-Transport-Security")) == cookie_seguro
    assert resposta.json["controles"]["hsts_condicional"] == cookie_seguro


def ong_em(nome, cnpj, endereco):
    return Estabelecimento(nome=nome, cnpj=cnpj, email=f"{nome}@teste.local",
                           telefone="11111111111", endereco=endereco, sem_fins_lucrativos=True)


def entregar(ong, quantidade, unidade, doador):
    pedido = Doacao(estabelecimento_id=ong.id, data_cadastro=datetime(2026, 10, 12, 12),
                    data_limite_retirada=datetime(2026, 10, 30))
    db.session.add(pedido)
    db.session.flush()
    item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Grãos e cereais",
                      quantidade=quantidade, unidade_medida=unidade)
    db.session.add(item)
    db.session.flush()
    db.session.add(Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id, doador_id=doador.id,
                                alimento="Arroz", categoria="Grãos e cereais", quantidade=quantidade,
                                unidade_medida=unidade, validade=date(2026, 10, 30), respostas="{}",
                                foto_arquivo="a.jpg", status="ENTREGUE",
                                criado_em=datetime(2026, 10, 12, 14)))


def test_mapa_de_calor_agrega_por_municipio_sem_dado_pessoal():
    """Rodada 20: pontos por município de quem recebeu, só cidade/UF, sede IBGE e números."""
    with app.app_context():
        centro = ong_em("ongcentro", "12345678000195", "Rua Sigilosa, 10 - Sé, sao paulo/sp - 01001000")
        zona = ong_em("ongzona", "23456789000189", "Av. Reservada, 20 - Mooca, São Paulo/SP - 03101000")
        recife = ong_em("ongrecife", "45678901000102", "Rua Escondida, 5 - Boa Vista, Recife/PE - 50050000")
        sumida = ong_em("ongsumida", "56789012000148", "Rua Três, 3 - Centro, Cidade Inventada/MG - 30000000")
        mercado = ong_em("mercado", "34567890000110", "Rua Quatro, 4 - Centro, Campinas/SP - 13010000")
        doador = Doador(nome="Pessoa Secreta", cpf="52998224725", email="pessoa@teste.local",
                        telefone="11987654321")
        db.session.add_all([centro, zona, recife, sumida, mercado, doador])
        db.session.flush()
        entregar(centro, 10, "kg", doador)
        entregar(zona, 4, "kg", doador)
        entregar(sumida, 6, "kg", doador)
        retirado = Excedente(estabelecimento_id=mercado.id, reservado_por_id=recife.id,
                             retirar_ate=datetime(2026, 10, 30), status="RETIRADO",
                             criado_em=datetime(2026, 10, 12, 12),
                             reservado_em=datetime(2026, 10, 12, 13),
                             retirado_em=datetime(2026, 10, 12, 18))
        retirado.itens = [ItemExcedente(nome="Feijão", categoria="Grãos e cereais", quantidade=3000,
                                        unidade_medida="g", validade=date(2026, 10, 30))]
        # oferta reservada e ainda não retirada não é impacto
        reservado = Excedente(estabelecimento_id=mercado.id, reservado_por_id=recife.id,
                              retirar_ate=datetime(2026, 10, 30), status="RESERVADO",
                              criado_em=datetime(2026, 10, 12, 12),
                              reservado_em=datetime(2026, 10, 12, 13))
        reservado.itens = [ItemExcedente(nome="Feijão", categoria="Grãos e cereais", quantidade=50,
                                         unidade_medida="kg", validade=date(2026, 10, 30))]
        db.session.add_all([retirado, reservado])
        db.session.commit()

    resposta = app.test_client().get("/reconecta/dashboard/impacto")
    assert resposta.status_code == 200
    refeicoes = resposta.json["refeicoes"]
    assert refeicoes["por_municipio"] == [
        {"municipio": "São Paulo", "uf": "SP", "lat": -23.5329, "lon": -46.6395,
         "kg_medido": 14, "kg_estimado": 0, "refeicoes_estimadas": 28, "ongs": 2},
        {"municipio": "Recife", "uf": "PE", "lat": -8.04666, "lon": -34.8771,
         "kg_medido": 3, "kg_estimado": 0, "refeicoes_estimadas": 6, "ongs": 1},
    ]
    assert refeicoes["organizacoes_sem_municipio"] == 1  # cidade fora da tabela do IBGE
    ufs = {r["uf"]: r for r in refeicoes["por_uf"]}
    assert (ufs["SP"]["ongs"], ufs["PE"]["ongs"], ufs["MG"]["ongs"]) == (2, 1, 1)
    assert ufs["MG"]["refeicoes_estimadas"] == 12  # sem coordenada continua na UF
    texto = resposta.get_data(as_text=True)
    for pessoal in ("ongcentro", "ongzona", "ongrecife", "ongsumida", "Sigilosa", "Reservada", "Escondida", "Mooca", "01001000", "12345678000195",
                    "Pessoa Secreta", "52998224725", "11987654321", "@teste.local", "mercado"):
        assert pessoal not in texto, pessoal


def test_contrato_do_mapa_por_municipio_e_por_uf():
    with app.app_context():
        ong = ong_em("ongbh", "12345678000195", "Rua A, 1 - Centro, Belo Horizonte/MG - 30110000")
        doador = Doador(nome="Pessoa", cpf="52998224725", email="p@teste.local", telefone="11111111111")
        db.session.add_all([ong, doador])
        db.session.flush()
        entregar(ong, 5, "kg", doador)
        db.session.commit()
    refeicoes = app.test_client().get("/reconecta/dashboard/impacto").json["refeicoes"]
    assert set(refeicoes) >= {"por_uf", "por_regiao", "por_municipio", "organizacoes_sem_municipio"}
    municipio, = refeicoes["por_municipio"]
    assert set(municipio) == {"municipio", "uf", "lat", "lon", "kg_medido", "kg_estimado",
                              "refeicoes_estimadas", "ongs"}
    assert isinstance(municipio["lat"], float) and isinstance(municipio["ongs"], int)
    uf, = refeicoes["por_uf"]
    assert set(uf) == {"uf", "kg_medido", "kg_estimado", "refeicoes_estimadas", "ongs"}


def test_sem_impacto_o_mapa_vem_vazio():
    refeicoes = app.test_client().get("/reconecta/dashboard/impacto").json["refeicoes"]
    assert refeicoes["por_municipio"] == [] and refeicoes["organizacoes_sem_municipio"] == 0


def test_malha_do_ibge_versionada_tem_27_ufs_e_fonte():
    raiz = Path(__file__).resolve().parents[1]
    arquivo = raiz / "static" / "geo" / "brasil.topo.json"
    assert arquivo.stat().st_size < 150 * 1024
    topo = json.loads(arquivo.read_text(encoding="utf-8"))
    ufs = {g["properties"]["uf"] for g in topo["objects"]["ufs"]["geometries"]}
    assert len(ufs) == 27 and {"SP", "DF", "AC", "RS", "AP"} <= ufs
    fontes = (raiz / "static" / "geo" / "FONTES.txt").read_text(encoding="utf-8")
    assert "servicodados.ibge.gov.br" in fontes and "Natural Earth" in fontes
    html = (raiz / "static" / "dashboard.html").read_text(encoding="utf-8")
    assert '/static/js/mapa-calor.js' in html and "tile" not in html.lower()


def test_demonstracao_espalha_o_mapa_pelas_cidades_mais_populosas():
    dados = json.loads((Path(__file__).resolve().parents[1] / "data" / "demonstracao.json")
                       .read_text(encoding="utf-8"))
    assert len(dados["organizacoes_ficticias"]) == 100 and "Censo 2022" in dados["fonte_populacao"]
    refeicoes = app.test_client().get("/reconecta/dashboard/impacto?modo=demonstracao").json["refeicoes"]
    cidades = {(m["municipio"], m["uf"]) for m in refeicoes["por_municipio"]}
    assert cidades <= {(o["cidade"], o["uf"]) for o in dados["organizacoes_ficticias"]}
    assert len(cidades) >= 80
    assert {Dashboard.REGIAO_UF[uf] for _, uf in cidades} == set(Dashboard.MACROREGIOES)
    # peso pela população: São Paulo é a cidade com mais refeições e o Sudeste supera o Norte
    assert refeicoes["por_municipio"][0]["municipio"] == "São Paulo"
    regioes = {r["regiao"]: r["refeicoes_estimadas"] for r in refeicoes["por_regiao"]}
    assert regioes["Sudeste"] > 3 * regioes["Norte"]
    assert refeicoes["organizacoes_sem_municipio"] == 0
    assert all(-34 < m["lat"] < 6 and -74 < m["lon"] < -34 and m["kg_medido"] + m["kg_estimado"] > 0
               for m in refeicoes["por_municipio"])
    # cada linha arredonda as próprias refeições: a diferença fica em até 1 por município
    assert sum(m["refeicoes_estimadas"] for m in refeicoes["por_municipio"]) == pytest.approx(
        sum(u["refeicoes_estimadas"] for u in refeicoes["por_uf"]), abs=len(cidades))
    assert "Exemplo" not in json.dumps(refeicoes)  # nomes das ONGs fictícias não vão para o mapa
