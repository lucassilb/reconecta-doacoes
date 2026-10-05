import json
import os
from datetime import date, timedelta

import pytest
import requests

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
import IA  # noqa: E402
import llm_service  # noqa: E402
from models import Doador, Estabelecimento, db  # noqa: E402


class RespostaOllama:
    def __init__(self, conteudo):
        self.conteudo = conteudo

    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": self.conteudo}}


@pytest.fixture(autouse=True)
def ambiente_sem_rede(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODELO", "qwen2.5:3b")
    IA._acessos.clear()

    def fora(*_args, **_kwargs):
        raise requests.ConnectionError("fora do ar")

    monkeypatch.setattr(requests.Session, "post", fora)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield
    IA._acessos.clear()


def _usuario(tipo):
    with app.app_context():
        if tipo == "empresa":
            usuario = Estabelecimento(nome="Empresa Segredo", cnpj="12345678000195",
                email="privado@exemplo.com", telefone="11999998888",
                endereco="Rua Privada, 10 - CENTRO, BARUERI/SP")
        else:
            usuario = Doador(nome="Pessoa Segredo", cpf="52998224725",
                email="pessoa@exemplo.com", telefone="11988887777")
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


def _cliente_autenticado(tipo):
    identificador = _usuario(tipo)
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["tipo"] = tipo
        sessao["usuario_id"] = identificador
    return cliente


TEXTO = "Precisamos de 100 caixas de leite e 100 pães até sexta-feira"


def test_interpretar_pedido_aceita_saida_valida_e_envia_ao_ollama_local(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    texto = "Precisamos de 100 caixas de leite até sexta-feira"
    chamadas = []
    saida = {"itens": [{"nome": "Leite", "categoria": "Laticínios",
                        "quantidade": 100, "unidade_medida": "caixa"}],
             "receber_ate": llm_service._prazo_regras(texto),
             "observacoes": "Conferir disponibilidade."}

    def responder(_self, url, **kwargs):
        chamadas.append((url, kwargs))
        return RespostaOllama(json.dumps(saida))

    monkeypatch.setattr(requests.Session, "post", responder)
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": texto})
    assert resposta.status_code == 200
    assert resposta.json == {**saida, "itens": [{**saida["itens"][0], "quantidade": 100.0}],
                             "fonte": "llm", "modelo": "qwen2.5:3b"}
    assert chamadas[0][0] == "http://localhost:11434/api/chat"
    corpo = chamadas[0][1]["json"]
    assert corpo["model"] == "qwen2.5:3b"
    assert corpo["format"]["properties"]["itens"]["items"]["properties"]["categoria"]["enum"] == llm_service.CATEGORIAS
    assert corpo["format"]["properties"]["itens"]["items"]["properties"]["unidade_medida"]["enum"] == llm_service.UNIDADES
    assert corpo["stream"] is False
    assert corpo["options"]["temperature"] == 0.2
    assert corpo["messages"][1]["content"] == texto
    assert date.today().isoformat() in corpo["messages"][0]["content"]
    assert "2 kg de arroz e 3 caixas de leite" in corpo["messages"][0]["content"]
    assert chamadas[0][1]["allow_redirects"] is False


def test_categoria_invalida_normalizada_e_maximo_de_dez_itens(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    itens = [{"nome": "leite", "categoria": "Categoria inventada", "quantidade": 1,
              "unidade_medida": "caixas"}] * 12
    assert len(llm_service._validar_pedido({"itens": itens})["itens"]) == 10
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama(json.dumps({"itens": itens})))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200
    assert len(resposta.json["itens"]) == 2
    assert resposta.json["itens"][0]["categoria"] == "Laticínios"
    assert resposta.json["itens"][1]["categoria"] == "Padaria"
    assert resposta.json["fonte"] == "llm"
    assert resposta.json["receber_ate"] == llm_service._prazo_regras(TEXTO)


def test_objeto_plano_de_um_item_e_aceito_sem_data_passada(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    plano = {"nome": "Leite", "categoria": "Laticínios", "quantidade": "100",
             "unidade_medida": "caixa", "receber_ate": "2022-07-15",
             "observacoes": ""}
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama(json.dumps(plano)))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={
        "texto": "Precisamos de 100 caixas de leite até sexta-feira"})
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "llm"
    assert resposta.json["itens"] == [{"nome": "Leite", "categoria": "Laticínios",
                                      "quantidade": 100.0, "unidade_medida": "caixa"}]
    assert resposta.json["receber_ate"] == llm_service._prazo_regras("até sexta-feira")


def test_objeto_plano_com_segundo_item_em_observacoes_recupera_dois(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    plano = {"nome": "Leite", "categoria": "Laticínios", "quantidade": "100",
             "unidade_medida": "caixa", "receber_ate": "2022-07-15",
             "observacoes": "100 pães"}
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama(json.dumps(plano)))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200 and resposta.json["fonte"] == "llm"
    assert [(i["nome"].lower(), i["quantidade"], i["unidade_medida"])
            for i in resposta.json["itens"]] == [
                ("leite", 100.0, "caixa"), ("pães", 100.0, "unidade")]
    assert resposta.json["receber_ate"] == llm_service._prazo_regras(TEXTO)


def test_modelo_erra_unidade_quantidade_e_dia_e_e_corrigido(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    saida = {"itens": [
        {"nome": "Leite", "categoria": "Laticínios", "quantidade": 100,
         "unidade_medida": "caixa"},
        {"nome": "Pés", "categoria": "Padaria", "quantidade": 1,
         "unidade_medida": "caixa"}],
        "receber_ate": (date.today() + timedelta(days=5)).isoformat(),
        "observacoes": ""}
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama(json.dumps(saida)))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200 and resposta.json["fonte"] == "llm"
    assert [(i["nome"].lower(), i["quantidade"], i["unidade_medida"], i["categoria"])
            for i in resposta.json["itens"]] == [
                ("leite", 100.0, "caixa", "Laticínios"),
                ("pães", 100.0, "unidade", "Padaria")]
    assert resposta.json["receber_ate"] == llm_service._prazo_regras(TEXTO)


def test_prazo_dia_do_mes_e_removido_do_nome_do_item():
    texto = "50 kg de arroz, 30 kg de feijão e 20 litros de leite para o dia 20"
    dados = llm_service._pedido_regras(texto)
    assert [(item["nome"], item["quantidade"], item["unidade_medida"])
            for item in dados["itens"]] == [
                ("arroz", 50.0, "kg"), ("feijão", 30.0, "kg"),
                ("leite", 20.0, "L")]
    assert dados["receber_ate"] is not None


@pytest.mark.parametrize("resposta_modelo", ["{quebrado", json.dumps({"itens": []})])
def test_json_quebrado_ou_sem_itens_usa_regras(resposta_modelo, monkeypatch):
    cliente = _cliente_autenticado("empresa")
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama(resposta_modelo))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "regras" and resposta.json["modelo"] is None
    assert [(i["nome"], i["categoria"], i["quantidade"], i["unidade_medida"])
            for i in resposta.json["itens"]] == [
                ("leite", "Laticínios", 100.0, "caixa"),
                ("pães", "Padaria", 100.0, "unidade")]
    assert resposta.json["receber_ate"] is not None


def test_ollama_fora_usa_regras_sem_fingir_ia():
    cliente = _cliente_autenticado("empresa")
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "regras" and resposta.json["modelo"] is None


def test_url_remota_bloqueada_antes_de_qualquer_requisicao(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    monkeypatch.setenv("OLLAMA_URL", "https://api.exemplo.com")
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        pytest.fail("Não deve haver chamada externa"))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200 and resposta.json["fonte"] == "regras"


def test_modelo_de_nuvem_nao_e_chamado(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    monkeypatch.setenv("OLLAMA_MODELO", "outro:cloud")
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        pytest.fail("Modelo de nuvem não deve ser chamado"))
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert resposta.status_code == 200 and resposta.json["fonte"] == "regras"


def test_texto_do_pedido_remove_identificadores_comuns_do_prompt(monkeypatch):
    cliente = _cliente_autenticado("empresa")
    chamadas = []

    def responder(_self, _url, **kwargs):
        chamadas.append(kwargs["json"]["messages"][1]["content"])
        return RespostaOllama(json.dumps({"itens": [{"nome": "Leite",
            "categoria": "Laticínios", "quantidade": 100, "unidade_medida": "caixa"}]}))

    monkeypatch.setattr(requests.Session, "post", responder)
    resposta = cliente.post("/reconecta/ia/interpretar-pedido", json={
        "texto": "100 caixas de leite. Fale com nome@exemplo.com ou 11999998888. CPF 52998224725."})
    assert resposta.status_code == 200
    assert "nome@exemplo.com" not in chamadas[0]
    assert "11999998888" not in chamadas[0]
    assert "52998224725" not in chamadas[0]


def test_interpretar_pedido_401_403_400():
    anonimo = app.test_client().post("/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert anonimo.status_code == 401 and anonimo.json["codigo"] == "NAO_AUTENTICADO"
    doador = _cliente_autenticado("doador").post(
        "/reconecta/ia/interpretar-pedido", json={"texto": TEXTO})
    assert doador.status_code == 403 and doador.json["codigo"] == "APENAS_EMPRESAS"
    cliente = _cliente_autenticado("empresa")
    for corpo in ({}, {"texto": "1234"}, {"texto": "x" * 601}, {"texto": 12}, None):
        resposta = cliente.post("/reconecta/ia/interpretar-pedido",
                               **({"json": corpo} if corpo is not None else {}))
        assert resposta.status_code == 400
        assert "texto" in resposta.json["campos"]


def test_resumo_dashboard_fallback_publico_e_limite_por_ip():
    cliente = app.test_client()
    for _ in range(10):
        resposta = cliente.post("/reconecta/ia/resumo-dashboard")
        assert resposta.status_code == 200
        assert resposta.json["fonte"] == "regras" and resposta.json["modelo"] is None
        assert len(resposta.json["resumo"].split(". ")) == 3
    bloqueado = cliente.post("/reconecta/ia/resumo-dashboard")
    assert bloqueado.status_code == 429 and bloqueado.json["codigo"] == "LIMITE_IA"
    assert bloqueado.headers["Retry-After"] == "60"
    outro_ip = cliente.post("/reconecta/ia/resumo-dashboard",
                            environ_overrides={"REMOTE_ADDR": "127.0.0.2"})
    assert outro_ip.status_code == 200


def test_resumo_envia_somente_agregados_e_ignora_corpo_do_cliente(monkeypatch):
    privado = "privado@exemplo.com"
    painel = {"gerado_em": "2026-10-05T12:00:00",
              "indicadores": {"empresas": 1, "doadores": 2, "pedidos_abertos": 3,
                              "pedidos_encerrados": 0, "percentual_atendimento": 50.0},
              "por_categoria": [{"categoria": "Padaria", "pedido": 100.0, "recebido": 50.0}],
              "por_dia": [{"data": "2026-10-05", "doacoes": 2}],
              "top_empresas": [{"nome": privado, "municipio_uf": "Rua privada"}],
              "ultimas_doacoes": [{"empresa": privado, "item": "Pessoa Segredo"}],
              "alertas": [{"tipo": "PRAZO_PROXIMO", "mensagem": privado, "pedido_id": 5}]}
    monkeypatch.setattr(IA, "montar_dashboard", lambda: painel)
    chamadas = []

    def responder(_self, _url, **kwargs):
        chamadas.append(kwargs["json"])
        return RespostaOllama(json.dumps({
            "resumo": "Há três pedidos abertos. Metade da meta foi atendida. Acompanhe o progresso.",
            "recomendacoes": ["Divulgue os pedidos abertos."]}))

    monkeypatch.setattr(requests.Session, "post", responder)
    resposta = app.test_client().post("/reconecta/ia/resumo-dashboard",
                                      json={"email": privado, "cpf": "52998224725"})
    assert resposta.status_code == 200 and resposta.json["fonte"] == "llm"
    assert resposta.json["gerado_em"] == painel["gerado_em"]
    enviado = json.dumps(chamadas[0], ensure_ascii=False)
    assert privado not in enviado and "52998224725" not in enviado
    assert "Pessoa Segredo" not in enviado and "Rua privada" not in enviado
    assert json.loads(chamadas[0]["messages"][1]["content"])["indicadores"]["pedidos_abertos"] == 3


def test_resumo_invalido_retorna_fallback_deterministico(monkeypatch):
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        RespostaOllama('{"resumo":"curto","recomendacoes":[]}'))
    resposta = app.test_client().post("/reconecta/ia/resumo-dashboard")
    assert resposta.status_code == 200
    assert resposta.json["fonte"] == "regras" and resposta.json["modelo"] is None
    assert "pedidos abertos" in resposta.json["resumo"]
