"""Provas de privacidade (LGPD): consentimento, exportação e anonimização."""
import json
import os
from datetime import date, datetime, timedelta

import pytest

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, ItemDoacao, db  # noqa: E402
from scripts.resumo_sast import _trivy_bloqueantes, resumir  # noqa: E402


CNPJ = "47508411000156"
CPF = "52998224725"
SENHA = "Segredo123"
CORPO_DOADOR = {"nome": "Maria Souza", "cpf": CPF, "email": "maria@exemplo.com",
                "telefone": "11999998888", "senha": SENHA}


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


@pytest.fixture
def cliente():
    return app.test_client()


def _empresa_consultada():
    return {
        "cnpj": CNPJ, "cnpj_formatado": "47.508.411/0001-56",
        "razao_social": "MERCADO REAL", "nome_fantasia": "Mercado Real",
        "situacao": "ATIVA", "ativo": True,
        "cnae_principal": {"codigo": "4711301", "descricao": "Hipermercados"},
        "atividades_alimentares": [], "relacionado_alimentacao": True,
        "natureza_juridica": {"codigo": "2062"}, "sem_fins_lucrativos": False,
        "endereco": {"logradouro": "AV EXEMPLO", "numero": "10", "complemento": "",
                     "bairro": "CENTRO", "municipio": "BARUERI", "uf": "SP", "cep": "06400000"},
        "email": None, "telefone": None, "fonte": "teste",
    }


def _cadastrar_doador(cliente, **extras):
    return cliente.post("/reconecta/cadastro/doador", json={**CORPO_DOADOR, **extras})


def _cadastrar_empresa(cliente, monkeypatch, **extras):
    monkeypatch.setattr("Cadastro.consultar_cnpj", lambda _: _empresa_consultada())
    return cliente.post("/reconecta/cadastro/empresa", json={
        "cnpj": CNPJ, "email": "empresa@exemplo.com", "telefone": "11999998888",
        "senha": SENHA, **extras})


def test_cadastro_sem_aceite_recusa_sem_consultar_receita(cliente, monkeypatch):
    monkeypatch.setattr("Cadastro.consultar_cnpj",
                        lambda _: pytest.fail("não consulta a Receita sem aceite"))
    for aceite in ({}, {"aceite_privacidade": False}, {"aceite_privacidade": "sim"}):
        resposta = _cadastrar_doador(cliente, **aceite)
        assert resposta.status_code == 400
        assert "privacidade" in resposta.json["campos"]
        resposta = _cadastrar_empresa(cliente, monkeypatch, **aceite)
        assert resposta.status_code == 400
        assert "privacidade" in resposta.json["campos"]
    with app.app_context():
        assert Doador.query.count() == Estabelecimento.query.count() == 0


def test_aceite_grava_versao_e_data(cliente, monkeypatch):
    assert _cadastrar_doador(cliente, aceite_privacidade=True).status_code == 201
    assert _cadastrar_empresa(cliente, monkeypatch, aceite_privacidade=True).status_code == 201
    with app.app_context():
        doador = Doador.query.one()
        empresa = Estabelecimento.query.one()
        for conta in (doador, empresa):
            assert conta.consentimento_versao == "2026-10-14"
            assert conta.consentimento_em is not None
    me = cliente.get("/reconecta/auth/me").json
    assert me["consentimento"]["versao"] == "2026-10-14"


def test_exportacao_traz_titular_e_registros(cliente):
    assert _cadastrar_doador(cliente, aceite_privacidade=True).status_code == 201
    with app.app_context():
        empresa = Estabelecimento(nome="ONG Luz", cnpj="11111111000191",
                                  email="ong@teste.local", telefone="11000000000",
                                  endereco="Rua A, 1 - Centro, Osasco/SP - 06000000",
                                  sem_fins_lucrativos=True)
        db.session.add(empresa)
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id, status="DISPONIVEL",
                        data_limite_retirada=datetime.now() + timedelta(days=3))
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Grãos e cereais",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.flush()
        doador = Doador.query.one()
        db.session.add(Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id,
            doador_id=doador.id, alimento="Arroz", categoria="Grãos e cereais",
            quantidade=2, unidade_medida="kg", validade=date.today(),
            respostas="{}", foto_arquivo="a.jpg", status="ACEITA"))
        db.session.commit()
    resposta = cliente.get("/reconecta/auth/me/dados")
    assert resposta.status_code == 200
    dados = resposta.json
    assert dados["titular"]["cpf"] == CPF
    assert dados["titular"]["consentimento"]["versao"] == "2026-10-14"
    assert dados["doacoes_feitas"][0]["alimento"] == "Arroz"
    assert dados["politica_versao"]


def test_exportacao_e_exclusao_exigem_login(cliente):
    assert cliente.get("/reconecta/auth/me/dados").status_code == 401
    assert cliente.delete("/reconecta/auth/me").status_code == 401


def test_exclusao_anonimiza_mantendo_estatistica(cliente):
    assert _cadastrar_doador(cliente, aceite_privacidade=True).status_code == 201
    with app.app_context():
        empresa = Estabelecimento(nome="ONG Luz", cnpj="11111111000191",
                                  email="ong@teste.local", telefone="11000000000",
                                  endereco="Rua A, 1 - Centro, Osasco/SP - 06000000",
                                  sem_fins_lucrativos=True)
        db.session.add(empresa)
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id, status="DISPONIVEL",
                        data_limite_retirada=datetime.now() + timedelta(days=3))
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Grãos e cereais",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.flush()
        doador = Doador.query.one()
        db.session.add(Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id,
            doador_id=doador.id, alimento="Arroz", categoria="Grãos e cereais",
            quantidade=2, unidade_medida="kg", validade=date.today(),
            respostas="{}", foto_arquivo="a.jpg", foto_dados=b"jpeg",
            status="ENTREGUE"))
        db.session.commit()

    assert cliente.delete("/reconecta/auth/me").status_code == 204
    assert cliente.get("/reconecta/auth/me").status_code == 401
    assert cliente.post("/reconecta/auth/login", json={
        "identificador": "maria@exemplo.com", "senha": SENHA}).status_code == 401
    with app.app_context():
        doador = Doador.query.one()
        assert (doador.nome, doador.telefone, doador.senha_hash) == ("Conta removida", "0", None)
        assert doador.email.endswith("@removido.invalid")
        assert doador.cpf != CPF and not doador.cpf.isdigit()
        contribuicao = Contribuicao.query.one()
        assert contribuicao.doador_id == doador.id  # estatística agregada preservada
        assert contribuicao.foto_dados is None
    # recadastro do mesmo CPF/e-mail continua possível (anonimização libera)
    assert _cadastrar_doador(cliente, aceite_privacidade=True).status_code == 201


def test_exclusao_empresa_remove_identificacao_dos_pedidos(cliente, monkeypatch):
    assert _cadastrar_empresa(cliente, monkeypatch, aceite_privacidade=True).status_code == 201
    with app.app_context():
        empresa = Estabelecimento.query.one()
        db.session.add(Doacao(estabelecimento_id=empresa.id, status="RETIRADA",
                              retirada_endereco="Rua da Empresa, 1",
                              retirada_municipio="Barueri", retirada_uf="SP",
                              data_limite_retirada=datetime.now() + timedelta(days=3)))
        db.session.commit()
    assert cliente.delete("/reconecta/auth/me").status_code == 204
    with app.app_context():
        empresa = Estabelecimento.query.one()
        assert empresa.nome == "Conta removida"
        assert empresa.cnpj != CNPJ and not empresa.cnpj.isdigit()
        assert empresa.endereco == "Endereço removido"
        pedido = Doacao.query.one()
        assert pedido.estabelecimento_id == empresa.id
        assert (pedido.retirada_endereco, pedido.retirada_municipio,
                pedido.retirada_uf) == (None, None, None)


def test_pagina_privacidade_e_rodape(cliente):
    resposta = cliente.get("/privacidade")
    assert resposta.status_code == 200
    texto = resposta.get_data(as_text=True)
    assert "Política de Privacidade" in texto and "LGPD" in texto


def test_migracao_consentimento_idempotente(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from migracoes import aplicar_migracoes
    engine = create_engine(f"sqlite:///{tmp_path / 'legado.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome TEXT, "
                             "cpf TEXT, email TEXT, telefone TEXT, criado_em DATETIME)"))
        conexao.execute(text("INSERT INTO doadores VALUES (1, 'Maria', '1', 'm@x', '1', NULL)"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    assert {"consentimento_versao", "consentimento_em"} <= {
        c["name"] for c in inspect(engine).get_columns("doadores")}


def test_gates_reproduzem_regra_do_ci(tmp_path):
    pasta = tmp_path / "relatorios" / "sast"
    pasta.mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "stride.md").write_text("| S1 | r | 2 | ◐ aberto |", encoding="utf-8")
    (tmp_path / "docs" / "sast.md").write_text("| B104 | Corrigido |", encoding="utf-8")
    (tmp_path / "modelo").mkdir()
    (tmp_path / "modelo" / "metricas.json").write_text('{"acuracia_top1": 0.8}', encoding="utf-8")
    (tmp_path / "modelo" / "limiares.json").write_text('{"acuracia_top1": 0.85}', encoding="utf-8")
    (pasta / "bandit.json").write_text(json.dumps(
        {"results": [{"issue_severity": "HIGH"}]}), encoding="utf-8")
    (pasta / "trivy-fs.json").write_text(json.dumps({"Results": [
        {"Vulnerabilities": [{"Severity": "HIGH", "FixedVersion": "1.2.3"},
                             {"Severity": "HIGH"}]}]}), encoding="utf-8")
    resultado = resumir(tmp_path)
    gates = {g["gate"]: g for g in resultado["gates"]}
    assert gates["bandit-high"]["resultado"] == "falhou"
    # 1 vuln HIGH corrigível bloqueia; a HIGH sem correção não conta
    assert gates["trivy-fs"]["resultado"] == "falhou"
    assert "1 achado" in gates["trivy-fs"]["detalhe"]
    assert gates["trivy-config"]["resultado"] == "sem_dados"
    assert gates["trivy-imagem"]["resultado"] == "sem_dados"
    assert gates["ia-limiares"]["resultado"] == "falhou"


def test_trivy_bloqueantes_conta_segredos_e_misconfig():
    doc = {"Results": [{"Secrets": [{}],
                        "Misconfigurations": [{"Severity": "HIGH"}, {"Severity": "LOW"}],
                        "Vulnerabilities": [{"Severity": "CRITICAL", "FixedVersion": "2"}]}]}
    assert _trivy_bloqueantes(doc, {"HIGH", "CRITICAL"}) == 3


def test_impacto_expõe_refeicoes_por_mes(cliente):
    with app.app_context():
        empresa = Estabelecimento(nome="ONG Luz", cnpj="11111111000191",
                                  email="ong@teste.local", telefone="11000000000",
                                  endereco="Rua A, 1 - Centro, Osasco/SP - 06000000")
        doador = Doador(nome="Maria", cpf=CPF, email="m@x.local", telefone="11000000000")
        db.session.add_all([empresa, doador])
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id, status="RETIRADA",
                        data_limite_retirada=datetime(2026, 9, 30))
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Grãos e cereais",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.flush()
        db.session.add_all([
            Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id, doador_id=doador.id,
                         alimento="Arroz", categoria="Grãos e cereais", quantidade=5,
                         unidade_medida="kg", validade=date(2026, 9, 30), respostas="{}",
                         foto_arquivo="a.jpg", status="ENTREGUE",
                         criado_em=datetime(2026, 9, 15, 12)),
            Contribuicao(doacao_id=pedido.id, item_doacao_id=item.id, doador_id=doador.id,
                         alimento="Arroz", categoria="Grãos e cereais", quantidade=3,
                         unidade_medida="kg", validade=date(2026, 10, 30), respostas="{}",
                         foto_arquivo="a.jpg", status="ENTREGUE",
                         criado_em=datetime(2026, 10, 2, 12))])
        db.session.commit()
    resposta = cliente.get("/reconecta/dashboard/impacto")
    serie = resposta.json["refeicoes_mensal"]["serie"]
    assert serie == [{"mes": "2026-09", "kg": 5, "refeicoes": 10},
                     {"mes": "2026-10", "kg": 3, "refeicoes": 6}]


def test_exclusao_doador_apaga_endereco_da_oferta_e_exportacao_traz_ofertas(cliente):
    from models import Excedente

    assert _cadastrar_doador(cliente, aceite_privacidade=True).status_code == 201
    with app.app_context():
        doador = Doador.query.one()
        for status in ("DISPONIVEL", "RETIRADO"):
            ong = None
            if status == "RETIRADO":
                ong = Estabelecimento(nome="ONG Luz", cnpj="11111111000191",
                                      email="ong@teste.local", telefone="11000000000",
                                      endereco="Rua A, 1 - Centro, Osasco/SP - 06000000",
                                      sem_fins_lucrativos=True)
                db.session.add(ong)
                db.session.flush()
            db.session.add(Excedente(
                doador_id=doador.id, retirada_endereco="Rua da Maria, 10 - Centro, Osasco/SP - 06000000",
                retirar_ate=datetime.now() + timedelta(days=1), status=status,
                reservado_por_id=ong.id if ong else None, criado_em=datetime.now()))
        db.session.commit()

    exportado = cliente.get("/reconecta/auth/me/dados").json
    assert len(exportado["excedentes_publicados"]) == 2
    assert "Rua da Maria" in json.dumps(exportado, ensure_ascii=False)

    assert cliente.delete("/reconecta/auth/me").status_code == 204
    with app.app_context():
        ofertas = Excedente.query.order_by(Excedente.id).all()
        assert all(o.retirada_endereco == "Endereço removido" for o in ofertas)
        assert [o.status for o in ofertas] == ["CANCELADO", "RETIRADO"]
