"""Pessoa física (CPF) também consegue doar quando não há pedido aberto: publica o que
sobrou como excedente, uma ONG reserva e ela confirma a retirada.

Antes (main 58cd1ee), o único caminho do CPF era doar para um pedido aberto. Sem pedido
(o estado do site público), o assistente respondia "Nenhum pedido aberto combina" sem ação,
e POST /reconecta/excedentes devolvia 403 APENAS_EMPRESAS.
"""
import json
import os
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from foto_oferta import com_foto  # noqa: E402
from eventos import Evento  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from models import Doador, Estabelecimento, Excedente, db  # noqa: E402
from test_integridade_banco import postgres_temporario  # noqa: E402,F401  (fixture opcional)


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield


def contas():
    with app.app_context():
        ong = Estabelecimento(nome="ONG Prato Cheio", cnpj="11444777000161", email="ong@exemplo.test",
                              telefone="11999999999", endereco="Av. Paulista, 1578 - Bela Vista, São Paulo/SP - 01310200",
                              sem_fins_lucrativos=True, atividade_alimentar=False)
        pessoa = Doador(nome="Joana Lima", cpf="52998224725", email="joana@exemplo.test", telefone="11988887777")
        db.session.add_all([ong, pessoa])
        db.session.commit()
        return ong.id, pessoa.id


def cliente(tipo, id_):
    c = app.test_client()
    with c.session_transaction() as s:
        s["tipo"], s["usuario_id"] = tipo, id_
    return c


def oferta(**extra):
    prazo = agora_brasilia_sem_fuso() + timedelta(hours=6)
    corpo = {"retirar_ate": prazo.isoformat(timespec="seconds"),
             "itens": [{"nome": "Arroz", "categoria": "Grãos e cereais", "quantidade": 5,
                        "unidade_medida": "kg", "validade": (prazo.date() + timedelta(days=60)).isoformat()}],
             "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True, "nao_caseiro": True,
             "retirada": {"logradouro": "Rua Barão de Jaguara", "numero": "1000", "bairro": "Centro",
                          "municipio": "Campinas", "uf": "SP", "cep": "13015-001"}}
    corpo.update(extra)
    return corpo


def test_pessoa_fisica_publica_ong_reserva_e_ela_confirma_a_retirada():
    ong_id, pessoa_id = contas()
    pessoa, ong = cliente("doador", pessoa_id), cliente("empresa", ong_id)

    publicado = pessoa.post("/reconecta/excedentes", data=com_foto(oferta()))
    assert publicado.status_code == 201, publicado.json  # antes: 403 APENAS_EMPRESAS
    id_ = publicado.json["id"]
    assert publicado.json["meu"] is True
    assert publicado.json["empresa"] == {"nome": "Pessoa física", "municipio_uf": "Campinas/SP", "pessoa_fisica": True}
    assert publicado.json["retirada_informada"] == "Rua Barão de Jaguara, 1000 - Centro, Campinas/SP - 13015001"

    # público: sem nome nem endereço da pessoa
    lista = app.test_client().get("/reconecta/excedentes").json
    assert [x["id"] for x in lista] == [id_]
    texto_publico = json.dumps(lista, ensure_ascii=False) + json.dumps(
        app.test_client().get(f"/reconecta/excedentes/{id_}").json, ensure_ascii=False)
    assert "Joana" not in texto_publico and "Barão de Jaguara" not in texto_publico
    assert app.test_client().get("/reconecta/excedentes?uf=SP").json[0]["id"] == id_

    reservado = ong.post(f"/reconecta/excedentes/{id_}/reservar")
    assert reservado.status_code == 200, reservado.json  # NULL != id não pode barrar a reserva
    assert reservado.json["retirada"]["endereco"].startswith("Rua Barão de Jaguara, 1000")
    assert ong.get("/reconecta/excedentes/rota").json["paradas"][0]["empresa"] == "Pessoa física"

    minha = pessoa.get(f"/reconecta/excedentes/{id_}").json
    assert minha["reservado_por"]["nome"] == "ONG Prato Cheio" and minha["status"] == "RESERVADO"
    assert [x["id"] for x in pessoa.get("/reconecta/excedentes/meus").json] == [id_]

    retirado = pessoa.post(f"/reconecta/excedentes/{id_}/confirmar-retirada")
    assert retirado.status_code == 200 and retirado.json["status"] == "RETIRADO"
    with app.app_context():
        privados = {(e.tipo, e.dest_tipo, e.dest_id) for e in Evento.query.filter_by(publico=False).all()}
        assert ("excedente.reservado", "doador", pessoa_id) in privados
        assert ("excedente.retirado", "doador", pessoa_id) in privados
        assert ("excedente.retirado", "empresa", ong_id) in privados
        publico = Evento.query.filter_by(tipo="excedente.publicado", publico=True).one()
        assert json.loads(publico.dados)["organizacao"] == "Pessoa física"


def test_pessoa_fisica_precisa_de_endereco_e_de_declarar_que_nao_e_caseiro():
    _, pessoa_id = contas()
    pessoa = cliente("doador", pessoa_id)
    sem_nada = pessoa.post("/reconecta/excedentes", json=oferta(nao_caseiro=False, retirada=None))
    assert sem_nada.status_code == 400
    assert {"nao_caseiro", "retirada.logradouro", "retirada.numero", "retirada.municipio"} <= set(sem_nada.json["campos"])
    cidade_errada = pessoa.post("/reconecta/excedentes", json=oferta(retirada={
        "logradouro": "Rua A", "numero": "1", "municipio": "Campinas", "uf": "RJ"}))
    assert cidade_errada.status_code == 400 and "retirada.municipio" in cidade_errada.json["campos"]
    with app.app_context():
        assert Excedente.query.count() == 0


def test_outra_pessoa_nao_gerencia_e_pessoa_fisica_nao_reserva():
    ong_id, pessoa_id = contas()
    with app.app_context():
        outra = Doador(nome="Bia", cpf="11144477735", email="bia@exemplo.test", telefone="11977776666")
        db.session.add(outra)
        db.session.commit()
        outra_id = outra.id
    id_ = cliente("doador", pessoa_id).post("/reconecta/excedentes", data=com_foto(oferta())).json["id"]
    intrusa = cliente("doador", outra_id)
    assert intrusa.delete(f"/reconecta/excedentes/{id_}").status_code == 404
    assert intrusa.post(f"/reconecta/excedentes/{id_}/reservar").status_code == 403
    assert intrusa.get(f"/reconecta/excedentes/{id_}").json["meu"] is False
    assert intrusa.get("/reconecta/excedentes/meus").json == []
    assert cliente("doador", pessoa_id).delete(f"/reconecta/excedentes/{id_}").status_code == 204


def test_assistente_oferece_publicar_para_pessoa_fisica():
    _, pessoa_id = contas()
    resposta = cliente("doador", pessoa_id).post("/reconecta/ia/sugerir-destino", json={"texto": "tenho 5 kg de arroz"})
    assert resposta.status_code == 200
    assert resposta.json["sugestoes"] == []  # nenhum pedido aberto, como no site público
    assert resposta.json["pode_publicar_excedente"] is True  # antes: False → beco sem saída


def test_migracao_sqlite_recria_excedentes_sem_perder_dados(tmp_path):
    from migracoes import _migrar_excedentes_pessoa_fisica
    engine = create_engine(f"sqlite:///{tmp_path / 'antigo.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome TEXT)"))
        c.execute(text("CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome TEXT)"))
        c.execute(text("""CREATE TABLE excedentes (
            id INTEGER PRIMARY KEY,
            estabelecimento_id INTEGER NOT NULL REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
            retirar_ate DATETIME NOT NULL, status VARCHAR(20) DEFAULT 'DISPONIVEL' NOT NULL,
            reservado_por_id INTEGER REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
            reservado_em DATETIME, retirado_em DATETIME, observacao VARCHAR(200), criado_em DATETIME NOT NULL)"""))
        c.execute(text("""CREATE TABLE itens_excedente (id INTEGER PRIMARY KEY,
            excedente_id INTEGER NOT NULL REFERENCES excedentes(id) ON DELETE CASCADE, nome TEXT)"""))
        c.execute(text("INSERT INTO estabelecimentos VALUES (1, 'Mercado')"))
        c.execute(text("INSERT INTO excedentes (id, estabelecimento_id, retirar_ate, status, observacao, criado_em) "
                       "VALUES (7, 1, '2030-01-01 10:00:00', 'DISPONIVEL', 'portaria', '2026-10-14 10:00:00')"))
        c.execute(text("INSERT INTO itens_excedente VALUES (1, 7, 'Pão')"))
    _migrar_excedentes_pessoa_fisica(engine)
    _migrar_excedentes_pessoa_fisica(engine)  # idempotente
    colunas = {c["name"]: c for c in inspect(engine).get_columns("excedentes")}
    assert colunas["estabelecimento_id"]["nullable"] and {"doador_id", "retirada_endereco"} <= set(colunas)
    with engine.connect() as c:
        assert c.execute(text("SELECT id, estabelecimento_id, observacao FROM excedentes")).all() == [(7, 1, "portaria")]
        assert c.execute(text("SELECT excedente_id FROM itens_excedente")).scalar() == 7
        assert "excedentes" in c.execute(text("SELECT sql FROM sqlite_master WHERE name='itens_excedente'")).scalar()
        assert c.execute(text("PRAGMA foreign_key_check")).all() == []


def test_postgresql_migra_excedentes_do_schema_publicado(postgres_temporario):
    """Schema da main 58cd1ee (o publicado): migra duas vezes, preserva o excedente e passa a aceitar PF."""
    from pathlib import Path
    from sqlalchemy.exc import IntegrityError
    from migracoes import aplicar_migracoes
    engine = postgres_temporario
    schema = (Path(__file__).parent / "fixtures" / "schema_main_58cd1ee.sql").read_text(encoding="utf-8")
    with engine.begin() as c:
        for comando in schema.split(";"):
            if comando.strip():
                c.execute(text(comando))
        c.execute(text("INSERT INTO estabelecimentos (id, nome, cnpj, email, telefone, endereco) VALUES "
                       "(1, 'ONG', '11444777000161', 'o@x.test', '1', 'Rua A, 1 - Centro, Campinas/SP')"))
        c.execute(text("INSERT INTO doadores (id, nome, cpf, email, telefone) VALUES (1, 'Joana', '52998224725', 'j@x.test', '1')"))
        c.execute(text("INSERT INTO excedentes (id, estabelecimento_id, retirar_ate) VALUES (5, 1, '2030-01-01')"))
        c.execute(text("INSERT INTO itens_excedente (excedente_id, nome, categoria, quantidade, unidade_medida, validade) "
                       "VALUES (5, 'Pão', 'Padaria', 2, 'kg', '2030-01-02')"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    colunas = {c["name"]: c for c in inspect(engine).get_columns("excedentes")}
    assert colunas["estabelecimento_id"]["nullable"] and {"doador_id", "retirada_endereco"} <= set(colunas)
    with engine.begin() as c:
        assert c.execute(text("SELECT estabelecimento_id FROM excedentes WHERE id = 5")).scalar() == 1
        c.execute(text("INSERT INTO excedentes (doador_id, retirada_endereco, retirar_ate) "
                       "VALUES (1, 'Rua B, 2 - Centro, Campinas/SP', '2030-01-01')"))
    for invalido in ("INSERT INTO excedentes (doador_id, retirar_ate) VALUES (1, '2030-01-01')",
                     "INSERT INTO excedentes (estabelecimento_id, doador_id, retirada_endereco, retirar_ate) "
                     "VALUES (1, 1, 'x', '2030-01-01')",
                     "INSERT INTO excedentes (retirar_ate) VALUES ('2030-01-01')"):
        with pytest.raises(IntegrityError):
            with engine.begin() as c:
                c.execute(text(invalido))
