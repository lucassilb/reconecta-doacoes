"""Contrato do provedor gratuito; todas as respostas HTTP são simuladas."""

import json

import pytest
import requests

import llm_service as llm


class Resposta:
    def __init__(self, status=200, conteudo=None, headers=None):
        self.status_code = status
        self.conteudo = conteudo
        self.headers = headers or {}

    def json(self):
        return {"choices": [{"message": {"content": self.conteudo}}]}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-de-teste-nao-real")
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    with llm._groq_lock:
        llm._groq_minuto.clear()
        llm._groq_dia.update(data=None, requisicoes=0, tokens=0)
        llm._groq_estado.update(falhas=0, aberto_ate=0.0)
    monkeypatch.setattr(llm, "_chamar_ollama", lambda *_a, **_k: None)


def pedido_valido():
    return {"itens": [{"nome": "Leite", "categoria": "Laticínios", "quantidade": 100,
                       "unidade_medida": "caixa"}], "receber_ate": None, "observacoes": ""}


def test_groq_strict_prioritario_com_texto_sanitizado_e_sem_chave_no_log(monkeypatch, caplog):
    chamadas = []

    def post(sessao, url, **kwargs):
        chamadas.append((sessao.trust_env, url, kwargs))
        return Resposta(conteudo=json.dumps(pedido_valido()))

    monkeypatch.setattr(requests.Session, "post", post)
    texto = "100 caixas de leite. Fale com nome@exemplo.com, 11999998888, CPF 52998224725."
    saida = llm.interpretar_pedido(texto)
    assert saida["fonte"] == "llm" and saida["modelo"] == "groq:openai/gpt-oss-20b"
    sem_proxy, url, kwargs = chamadas[0]
    assert sem_proxy is False and url == llm.GROQ_URL
    assert kwargs["allow_redirects"] is False and kwargs["timeout"] == (2, 8)
    assert kwargs["headers"]["Authorization"] == "Bearer chave-de-teste-nao-real"
    corpo = kwargs["json"]
    assert corpo["response_format"]["json_schema"]["strict"] is True
    esquema = corpo["response_format"]["json_schema"]["schema"]
    assert esquema["required"] == ["itens", "receber_ate", "observacoes"]
    assert esquema["additionalProperties"] is False
    assert esquema["properties"]["itens"]["items"]["additionalProperties"] is False
    enviado = json.dumps(corpo, ensure_ascii=False)
    assert all(x not in enviado for x in ("nome@exemplo.com", "11999998888", "52998224725", "chave-de-teste"))
    assert "chave-de-teste" not in caplog.text


@pytest.mark.parametrize("conteudo", ["{quebrado", json.dumps({"itens": []}),
                                        json.dumps({"itens": [{"nome": "Leite"}]})])
def test_json_invalido_ou_fora_do_esquema_cai_nas_regras(monkeypatch, conteudo):
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k: Resposta(conteudo=conteudo))
    saida = llm.interpretar_pedido("100 caixas de leite")
    assert saida["fonte"] == "regras" and saida["itens"][0]["quantidade"] == 100


def test_429_abre_disjuntor_sem_retry_ou_espera(monkeypatch):
    chamadas = []

    def post(*_args, **_kwargs):
        chamadas.append(1)
        return Resposta(status=429, headers={"retry-after": "32"})

    monkeypatch.setattr(requests.Session, "post", post)
    assert llm.interpretar_pedido("100 caixas de leite")["fonte"] == "regras"
    assert llm._groq_estado["aberto_ate"] > llm.time.monotonic() + 30
    assert llm.interpretar_pedido("100 caixas de leite")["fonte"] == "regras"
    assert len(chamadas) == 1


@pytest.mark.parametrize("erro", [500, 401, 403, "timeout"])
def test_falhas_sem_vazar_chave_e_ollama_como_fallback(monkeypatch, caplog, erro):
    def post(*_args, **_kwargs):
        if erro == "timeout":
            raise requests.Timeout("detalhe privado")
        return Resposta(status=erro)

    monkeypatch.setattr(requests.Session, "post", post)
    monkeypatch.setattr(llm, "_chamar_ollama", lambda *_a, **_k: pedido_valido())
    saida = llm.interpretar_pedido("100 caixas de leite")
    assert saida["fonte"] == "llm" and saida["modelo"] == "qwen2.5:3b"
    assert "chave-de-teste" not in caplog.text and "detalhe privado" not in caplog.text
    assert "Groq indisponível" in caplog.text


def test_tres_falhas_abrem_disjuntor_e_resposta_valida_reseta_contador(monkeypatch):
    chamadas = []

    def post(*_args, **_kwargs):
        chamadas.append(1)
        return Resposta(status=500)

    monkeypatch.setattr(requests.Session, "post", post)
    for _ in range(4):
        assert llm.interpretar_pedido("100 caixas de leite")["fonte"] == "regras"
    assert len(chamadas) == 3
    assert llm._groq_estado["aberto_ate"] > llm.time.monotonic()


def test_guarda_de_orcamento_e_modelo_free(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "modelo-fora-do-free")
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k: pytest.fail("rede inesperada"))
    assert llm.interpretar_pedido("100 caixas de leite")["fonte"] == "regras"
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    with llm._groq_lock:
        llm._groq_dia.update(data=llm.hoje_brasilia(), requisicoes=900, tokens=0)
    assert llm.interpretar_pedido("100 caixas de leite")["fonte"] == "regras"


def test_sem_chave_usa_ollama(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k: pytest.fail("rede inesperada"))
    monkeypatch.setattr(llm, "_chamar_ollama", lambda *_a, **_k: pedido_valido())
    assert llm.interpretar_pedido("100 caixas de leite")["modelo"] == "qwen2.5:3b"


def test_resumo_do_dashboard_usa_groq_com_apenas_agregados(monkeypatch):
    chamadas = []

    def post(_self, _url, **kwargs):
        chamadas.append(kwargs["json"])
        return Resposta(conteudo=json.dumps({
            "resumo": "Há 2 pedidos abertos. A meta está em 50%. Houve 3 doações.",
            "recomendacoes": ["Divulgue pedidos abertos."]}))

    monkeypatch.setattr(requests.Session, "post", post)
    dashboard = {"gerado_em": "2026-10-14T12:00:00", "indicadores": {
        "pedidos_abertos": 2, "percentual_atendimento": 50},
        "por_categoria": [], "por_dia": [], "alertas": [], "segredo": "Pessoa Segredo"}
    saida = llm.resumir_dashboard(dashboard)
    assert saida["fonte"] == "llm" and saida["modelo"] == "groq:openai/gpt-oss-20b"
    assert "Pessoa Segredo" not in json.dumps(chamadas, ensure_ascii=False)


def test_resposta_incoerente_do_groq_tenta_ollama(monkeypatch):
    monkeypatch.setattr(requests.Session, "post", lambda *_a, **_k:
                        Resposta(conteudo=json.dumps({**pedido_valido(), "itens": [
                            {"nome": "Arroz", "categoria": "Grãos e cereais", "quantidade": 100,
                             "unidade_medida": "kg"}]})))
    monkeypatch.setattr(llm, "_chamar_ollama", lambda *_a, **_k: pedido_valido())
    saida = llm.interpretar_pedido("100 caixas de leite")
    assert saida["modelo"] == "qwen2.5:3b" and llm._groq_estado["falhas"] == 1
