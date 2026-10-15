"""O plano DAST mantém o alvo local e trata alertas pela severidade real do ZAP."""

import json
import os
import subprocess
import sys
import pytest

from scripts.dast import (JPEG_MINIMO, PUBLICAS, PAPEIS, POSTS, RAIZ, ROTA_OFERTA, multipart,
                          oferta_ficticia, respostas_da_oferta, resumir_zap, spec_parcial)


def test_semente_recusa_execucao_fora_do_compose_efemero():
    ambiente = {**os.environ, "RECONECTA_DAST": "0", "DATABASE_URL": "sqlite://"}
    resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "seed_dast.py")],
                               cwd=RAIZ, env=ambiente, capture_output=True, text=True,
                               timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert resultado.returncode != 0
    assert "SQLite efêmero" in resultado.stderr


def test_spec_zap_usa_gets_e_posts_locais_do_swagger(tmp_path):
    swagger = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
    for nome, rotas in [("publico", PUBLICAS), *[(p, dados[2]) for p, dados in PAPEIS.items()]]:
        saida = tmp_path / f"{nome}.json"
        spec_parcial(swagger, rotas, saida, POSTS[nome])
        preparado = json.loads(saida.read_text(encoding="utf-8"))
        assert preparado["host"] == "app:5000"
        assert preparado["schemes"] == ["http"]
        assert set(preparado["paths"]) == rotas | POSTS[nome]
        for rota, operacoes in preparado["paths"].items():
            assert ("get" in operacoes) == (rota in rotas)
            assert ("post" in operacoes) == (rota in POSTS[nome])


def test_resumo_zap_preserva_alta_sem_evidencia_ou_cookie(tmp_path):
    arquivo = tmp_path / "zap.json"
    arquivo.write_text(json.dumps({"site": [{"alerts": [
        {"pluginid": "40018", "alert": "SQL Injection", "riskcode": "3",
         "instances": [{"requestHeader": "Cookie: session=segredo", "evidence": "cpf"}]},
        {"pluginid": "10020", "alert": "Header", "riskcode": "1", "instances": [{}]},
    ]}]}), encoding="utf-8")
    resumo = resumir_zap({"publico": arquivo})
    assert resumo["por_severidade"]["ALTA"] == 1
    assert resumo["por_severidade"]["BAIXA"] == 1
    assert "segredo" not in json.dumps(resumo)
    assert "cpf" not in json.dumps(resumo)


def test_resumo_zap_recusa_relatorio_sem_alvo(tmp_path):
    arquivo = tmp_path / "vazio.json"
    arquivo.write_text('{"site": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="sem alvo"):
        resumir_zap({"publico": arquivo})


def test_spec_do_doador_parte_de_oferta_valida_em_multipart(tmp_path):
    """Rodada 19: a oferta é multipart (dados + foto); o ZAP parte de um `dados` válido."""
    swagger = json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
    saida = tmp_path / "doador.json"
    spec_parcial(swagger, PAPEIS["doador"][2], saida, POSTS["doador"])
    post = json.loads(saida.read_text(encoding="utf-8"))["paths"][ROTA_OFERTA]["post"]
    assert post["consumes"] == ["multipart/form-data"]
    parametros = {p["name"]: p for p in post["parameters"]}
    assert parametros["foto"]["type"] == "file" and parametros["foto"]["in"] == "formData"
    assert json.loads(parametros["dados"]["default"])["itens"][0]["nome"] == "Arroz"
    # o swagger.json original não é alterado
    assert "default" not in json.dumps(swagger["paths"][ROTA_OFERTA]["post"]["parameters"])


def test_corpo_multipart_do_dast_publica_e_json_sem_foto_e_recusado(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app import app
    from models import Doador, db
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        doador = Doador(nome="Doador Ficticio", cpf="52998224725", email="doador@dast.invalid",
                        telefone="11900000001")
        db.session.add(doador)
        db.session.commit()
        doador_id = doador.id
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["tipo"], sessao["usuario_id"] = "doador", doador_id
    corpo, tipo = multipart({"dados": json.dumps(oferta_ficticia(), ensure_ascii=False)},
                            {"foto": ("validade.jpg", "image/jpeg", JPEG_MINIMO)})
    criado = cliente.post(ROTA_OFERTA, data=corpo, content_type=tipo)
    assert criado.status_code == 201, criado.json
    assert cliente.get(criado.json["foto_url"]).data == JPEG_MINIMO
    antigo = cliente.post(ROTA_OFERTA, json=oferta_ficticia())
    assert antigo.status_code == 400 and "foto" in antigo.json["campos"]


def test_contagem_do_access_log_desconta_a_prova_direta():
    registro = "\n".join(["app-1  | POST /reconecta/excedentes 201 512 9ms",
                           "app-1  | POST /reconecta/excedentes 400 120 2ms",
                           "app-1  | POST /reconecta/excedentes 400 120 2ms",
                           "app-1  | POST /reconecta/excedentes/7/reservar 403 80 1ms",
                           "app-1  | GET /reconecta/excedentes 200 2 1ms"])
    assert respostas_da_oferta(registro) == {"400": 1}


def _resumo_com_sqli(rotas):
    return {"varreduras": {"empresa": {"alertas": [
        {"id": "40018", "nome": "SQL Injection", "severidade": "ALTA", "ocorrencias": 1, "rotas": rotas}]}},
        "por_severidade": {"ALTA": 1, "CRITICA": 0}}


def test_sqli_em_rota_de_texto_so_vira_falso_positivo_com_iast_limpo():
    from scripts.dast import aplicar_falsos_positivos

    limpo = {"eventos": {"sql_observado": 10}, "achados": []}
    resumo = aplicar_falsos_positivos(_resumo_com_sqli(["/reconecta/ia/interpretar-pedido"]), limpo)
    assert resumo["por_severidade"]["ALTA"] == 0
    assert resumo["falsos_positivos"]["alertas"][0]["id"] == "40018"

    sujo = {"achados": [{"tipo": "sql_com_dado_da_requisicao", "severidade": "ALTA"}]}
    assert aplicar_falsos_positivos(_resumo_com_sqli(["/reconecta/ia/interpretar-pedido"]), sujo)[
        "por_severidade"]["ALTA"] == 1

    outra_rota = aplicar_falsos_positivos(_resumo_com_sqli(["/reconecta/auth/login"]), limpo)
    assert outra_rota["por_severidade"]["ALTA"] == 1
