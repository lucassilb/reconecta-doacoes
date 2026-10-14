"""Matriz BOLA/IDOR da API em SQLite exclusivamente em memória.

O inventário vem do Swagger versionado. Qualquer escrita nova sem classificação
falha antes da primeira requisição. Não usa rede, banco configurado ou contas reais.
"""

import json
import os
import re
import sys
import tempfile
import argparse
from datetime import timedelta
from io import BytesIO
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
# Forçar isolamento antes de importar app (que cria as tabelas no import).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "chave-de-teste-bola-isolado"
os.environ["GROQ_API_KEY"] = ""
os.environ["GEO_EXTERNO"] = "0"
os.environ["OLLAMA_PERMITIR_DOCKER"] = "0"
os.environ["ADMIN_TOKEN"] = "token-de-teste-bola"
os.environ["RECONECTA_IAST"] = "0"

from app import app  # noqa: E402
from eventos import Evento  # noqa: E402
from fuso import agora_brasilia_sem_fuso, hoje_brasilia  # noqa: E402
from models import (Contribuicao, Doacao, Doador, Estabelecimento, Excedente,
                    Instituicao, ItemDoacao, ItemExcedente, db)  # noqa: E402
import IA  # noqa: E402
from Auth import _auditoria  # noqa: E402

_auditoria.disabled = True  # o relatório só registra códigos e papéis fictícios


# Chaves literais servem como revisão de escopo; os testes percorrem as operações
# realmente presentes em swagger.json. "publica" não transporta dados privados.
ESCRITAS = {
    "POST /reconecta/auth/login": "publica",
    "POST /reconecta/auth/logout": "sessao",
    "PUT /reconecta/auth/me": "sessao",
    "DELETE /reconecta/auth/me": "sessao",
    "POST /reconecta/cadastro/doador": "publica",
    "POST /reconecta/cadastro/empresa": "publica",
    "POST /reconecta/doacoes/": "admin",
    "PUT /reconecta/doacoes/{id}": "admin",
    "DELETE /reconecta/doacoes/{id}": "admin",
    "POST /reconecta/estabelecimentos/": "admin",
    "PUT /reconecta/estabelecimentos/{id}": "admin",
    "DELETE /reconecta/estabelecimentos/{id}": "admin",
    "POST /reconecta/excedentes": "papel",
    "DELETE /reconecta/excedentes/{excedente_id}": "objeto",
    "POST /reconecta/excedentes/{excedente_id}/cancelar-reserva": "objeto",
    "POST /reconecta/excedentes/{excedente_id}/confirmar-retirada": "objeto",
    "POST /reconecta/excedentes/{excedente_id}/reservar": "papel",
    "POST /reconecta/ia/interpretar-pedido": "papel",
    "POST /reconecta/ia/resumo-dashboard": "publica",
    "POST /reconecta/ia/risco-descarte": "publica",
    "POST /reconecta/ia/sugerir-destino": "sessao",
    "POST /reconecta/instituicoes/": "admin",
    "PUT /reconecta/instituicoes/{id}": "admin",
    "DELETE /reconecta/instituicoes/{id}": "admin",
    "POST /reconecta/notificacoes/lidas": "sessao",
    "POST /reconecta/painel/contribuicoes/{contribuicao_id}/nao-recebida": "objeto",
    "POST /reconecta/painel/contribuicoes/{contribuicao_id}/receber": "objeto",
    "POST /reconecta/painel/doacoes": "papel",
    "DELETE /reconecta/painel/doacoes/{doacao_id}": "objeto",
    "POST /reconecta/publico/doacoes/{doacao_id}/contribuicoes": "papel",
}

LEITURAS_PRIVADAS = {
    "GET /reconecta/auth/me",
    "GET /reconecta/auth/me/dados",
    "GET /reconecta/contribuicoes/{contribuicao_id}/foto",
    "GET /reconecta/excedentes/meus",
    "GET /reconecta/excedentes/reservas",
    "GET /reconecta/excedentes/rota",
    "GET /reconecta/notificacoes",
    "GET /reconecta/painel/doacoes",
    "GET /reconecta/painel/minhas-doacoes",
    "GET /reconecta/novidades",
    "GET /reconecta/excedentes/{excedente_id}",
    "GET /reconecta/estabelecimentos/",
    "GET /reconecta/estabelecimentos/{id}",
    "GET /reconecta/instituicoes/",
    "GET /reconecta/instituicoes/{id}",
}


def inventario(swagger=None):
    swagger = swagger or json.loads((RAIZ / "swagger.json").read_text(encoding="utf-8"))
    operacoes = {f"{metodo.upper()} {rota}" for rota, metodos in swagger["paths"].items()
                 for metodo in metodos if metodo in ("get", "post", "put", "patch", "delete")}
    escritas = {op for op in operacoes if op.split(" ", 1)[0] != "GET"}
    faltantes = escritas - ESCRITAS.keys()
    obsoletas = ESCRITAS.keys() - escritas
    leituras_faltantes = LEITURAS_PRIVADAS - operacoes
    if faltantes or obsoletas or leituras_faltantes:
        raise AssertionError(f"Swagger mudou: escritas sem matriz={sorted(faltantes)}; "
                             f"obsoletas={sorted(obsoletas)}; leituras ausentes={sorted(leituras_faltantes)}")
    return sorted(operacoes)


def semear():
    prazo = agora_brasilia_sem_fuso() + timedelta(days=2)
    validade = hoje_brasilia() + timedelta(days=3)
    usuarios = {}
    for perfil, nome, indice in (("ong", "ONG Um", 1), ("ong", "ONG Dois", 2),
                                 ("empresa", "Mercado Um", 1), ("empresa", "Mercado Dois", 2)):
        chave = f"{perfil}{indice}"
        usuarios[chave] = Estabelecimento(
            nome=nome, cnpj=f"{indice + (0 if perfil == 'ong' else 2):014d}",
            email=f"{chave}@bola.invalid", telefone="11999999999",
            endereco="Rua Teste, 7 - Centro, São Paulo/SP - 01000000",
            sem_fins_lucrativos=perfil == "ong", atividade_alimentar=perfil == "empresa")
    for indice in (1, 2):
        chave = f"doador{indice}"
        usuarios[chave] = Doador(nome=f"Pessoa {indice}", cpf=f"{indice:011d}",
                                 email=f"{chave}@bola.invalid", telefone="11999999999")
    db.session.add_all(usuarios.values())
    db.session.flush()

    objetos = {}

    def excedente(chave, publicador, reservante=None):
        tipo = "doador_id" if publicador.startswith("doador") else "estabelecimento_id"
        item = Excedente(**{tipo: usuarios[publicador].id}, retirar_ate=prazo,
                         retirada_endereco="Rua Segredo, 21 - Centro, São Paulo/SP - 01000000"
                         if tipo == "doador_id" else None,
                         status="RESERVADO" if reservante else "DISPONIVEL",
                         reservado_por_id=usuarios[reservante].id if reservante else None)
        db.session.add(item)
        db.session.flush()
        db.session.add(ItemExcedente(excedente_id=item.id, nome="Pão", categoria="Padaria",
                                    quantidade=4, unidade_medida="kg", validade=validade))
        objetos[chave] = item.id

    excedente("reservado1", "empresa1", "ong1")
    excedente("reservado2", "empresa2", "ong2")
    excedente("reservado3", "empresa1", "ong2")
    excedente("cancelavel", "empresa1")
    excedente("livre1", "empresa1")
    excedente("livre2", "empresa2")
    excedente("pessoa1", "doador1")
    excedente("pessoa2", "doador2")

    def pedido(chave, ong, com_item=True):
        item = Doacao(estabelecimento_id=usuarios[ong].id,
                      data_limite_retirada=prazo, status="DISPONIVEL")
        db.session.add(item)
        db.session.flush()
        if com_item:
            alimento = ItemDoacao(doacao_id=item.id, nome="Pão", categoria="Padaria",
                                  quantidade=5, unidade_medida="kg", validade=validade)
            db.session.add(alimento)
            db.session.flush()
            objetos[f"item_{chave}"] = alimento.id
        objetos[chave] = item.id

    pedido("pedido1", "ong1")
    pedido("pedido2", "ong2")
    pedido("pedido_vazio", "ong1", False)
    pedido("pedido_admin", "ong2", False)
    for chave, pedido_chave, doador in (("entrega", "pedido1", "doador1"),
                                        ("nao_recebida", "pedido1", "doador1"),
                                        ("terceiro", "pedido2", "doador2")):
        item = Contribuicao(doacao_id=objetos[pedido_chave],
                            item_doacao_id=objetos[f"item_{pedido_chave}"],
                            doador_id=usuarios[doador].id, alimento="Pão", categoria="Padaria",
                            quantidade=2, unidade_medida="kg", validade=validade,
                            respostas='{"dentro_validade":"sim"}',
                            foto_arquivo="a" * 32 + ".jpg", foto_dados=b"\xff\xd8\xff\xd9",
                            status="ACEITA")
        db.session.add(item)
        db.session.flush()
        objetos[chave] = item.id
    for chave, usuario in usuarios.items():
        tipo = "doador" if chave.startswith("doador") else "empresa"
        db.session.add(Evento(tipo="teste.privado", publico=False, dest_tipo=tipo,
                              dest_id=usuario.id, dados=json.dumps({"marcador": chave})))
    objetos["legacy_instituicao"] = Instituicao(nome="Legado", cnpj="99999999999999",
                                                email="legado@bola.invalid", telefone="11999999999",
                                                endereco="Rua Teste, 1")
    db.session.add(objetos["legacy_instituicao"])
    db.session.commit()
    objetos["legacy_instituicao"] = objetos["legacy_instituicao"].id
    return {chave: usuario.id for chave, usuario in usuarios.items()}, objetos


def cliente(usuarios, ator):
    cliente_ = app.test_client()
    if ator != "anonimo":
        with cliente_.session_transaction() as sessao:
            sessao["tipo"] = "doador" if ator.startswith("doador") else "empresa"
            sessao["usuario_id"] = usuarios[ator]
    return cliente_


def main(saida=None):
    operacoes = inventario()
    app.config["TESTING"] = True
    resultados = []
    with tempfile.TemporaryDirectory(prefix="reconecta-bola-") as temporario:
        app.instance_path = temporario  # cópia local de foto também fica efêmera
        # Autorização da IA sem dependência de modelo/serviço externo.
        IA.interpretar_pedido = lambda texto: {
            "itens": [{"nome": "Pão", "categoria": "Padaria", "quantidade": 1,
                       "unidade_medida": "kg"}], "fonte": "teste", "modelo": "teste"}
        with app.app_context():
            usuarios, ids = semear()

            def email_de(ator):
                modelo = Doador if ator.startswith("doador") else Estabelecimento
                return db.session.get(modelo, usuarios[ator]).email

            def prova(metodo, rota, ator, esperado, *, json_=None, data=None,
                      conferir=None, admin=False, classificacao="objeto"):
                resposta = cliente(usuarios, ator).open(
                    rota, method=metodo, json=json_, data=data,
                    headers={"X-Admin-Token": os.environ["ADMIN_TOKEN"]} if admin else None)
                db.session.expire_all()
                codigos = {esperado} if isinstance(esperado, int) else set(esperado)
                if resposta.status_code not in codigos:
                    raise AssertionError(f"{metodo} {rota} [{ator}]: {resposta.status_code}; "
                                         f"esperado {sorted(codigos)}; corpo={resposta.get_json(silent=True)}")
                if conferir:
                    conferir(resposta.get_json(silent=True))
                resultados.append({"metodo": metodo, "rota": rota, "ator": ator,
                                   "classe": classificacao, "esperado": sorted(codigos),
                                   "obtido": resposta.status_code})
                return resposta

            # Leitura privada: filtros devem conter apenas objetos da sessão.
            def ids_em(dados, chave):
                return {item[chave] for item in dados}

            for ator, esperado, meu in (("ong1", 200, "pedido1"),
                                         ("ong2", 200, "pedido2"),
                                         ("doador1", 403, None), ("anonimo", 401, None)):
                prova("GET", "/reconecta/painel/doacoes", ator, esperado,
                      conferir=(lambda d, x=ids[meu]:
                               (_ for _ in ()).throw(AssertionError("pedido alheio"))
                               if x not in ids_em(d, "id") or
                               (ids["pedido2"] if x == ids["pedido1"] else ids["pedido1"]) in ids_em(d, "id")
                               else None) if meu else None)

            for ator, esperado, incluidos, ausentes in (
                    ("doador1", 200, {ids["entrega"], ids["nao_recebida"]}, {ids["terceiro"]}),
                    ("doador2", 200, {ids["terceiro"]}, {ids["entrega"]}),
                    ("ong1", 200, set(), {ids["terceiro"]}),
                    ("anonimo", 401, set(), set())):
                prova("GET", "/reconecta/painel/minhas-doacoes", ator, esperado,
                      conferir=(lambda d, sim=incluidos, nao=ausentes:
                               (_ for _ in ()).throw(AssertionError("contribuição alheia"))
                               if not sim <= ids_em(d, "id") or nao & ids_em(d, "id") else None)
                      if esperado == 200 else None)

            for ator, esperado, meu, alheio in (("empresa1", 200, ids["cancelavel"], ids["livre2"]),
                                                ("empresa2", 200, ids["livre2"], ids["cancelavel"]),
                                                ("doador1", 200, ids["pessoa1"], ids["pessoa2"]),
                                                ("anonimo", 401, None, None)):
                prova("GET", "/reconecta/excedentes/meus", ator, esperado,
                      conferir=(lambda d, sim=meu, nao=alheio:
                               (_ for _ in ()).throw(AssertionError("excedente alheio"))
                               if sim not in ids_em(d, "id") or nao in ids_em(d, "id") else None)
                      if esperado == 200 else None)

            for rota in ("/reconecta/excedentes/reservas", "/reconecta/excedentes/rota"):
                for ator, esperado, meu, alheio in (("ong1", 200, ids["reservado1"], ids["reservado2"]),
                                                    ("ong2", 200, ids["reservado2"], ids["reservado1"]),
                                                    ("empresa1", 200 if rota.endswith("/reservas") else 403,
                                                     None, None),
                                                    ("anonimo", 401, None, None)):
                    def conferir_reserva(d, sim=meu, nao=alheio, caminho=rota):
                        lista = d["paradas"] + d["sem_localizacao"] if caminho.endswith("/rota") else d
                        chave = "excedente_id" if caminho.endswith("/rota") else "id"
                        achados = ids_em(lista, chave)
                        assert (sim in achados if sim is not None else not achados), "reserva própria ausente"
                        assert nao not in achados, "rota/reserva alheia"
                    prova("GET", rota, ator, esperado,
                          conferir=conferir_reserva if esperado == 200 else None)

            for ator, esperado, marcador in (("ong1", 200, "ong1"),
                                              ("ong2", 200, "ong2"),
                                              ("doador1", 200, "doador1"),
                                              ("anonimo", 401, None)):
                prova("GET", "/reconecta/notificacoes", ator, esperado,
                      conferir=(lambda d, m=marcador:
                               (_ for _ in ()).throw(AssertionError("notificação alheia"))
                               if {x["dados"]["marcador"] for x in d["notificacoes"]} != {m} else None)
                      if esperado == 200 else None)
                prova("GET", "/reconecta/novidades?desde=0", ator, 200,
                      conferir=(lambda d, m=marcador:
                               (_ for _ in ()).throw(AssertionError("evento privado alheio"))
                               if {x["dados"]["marcador"] for x in d["eventos"]} != {m}
                               else None) if marcador else
                      (lambda d: (_ for _ in ()).throw(AssertionError("evento sem login"))
                       if d["eventos"] else None))
            for ator, esperado in (("ong1", 200), ("ong2", 200),
                                    ("doador1", 200), ("anonimo", 401)):
                prova("POST", "/reconecta/notificacoes/lidas", ator, esperado,
                      json_={"ate_id": 10**6}, classificacao="sessao")

            for ator, esperado, email in (("ong1", 200, "ong1@bola.invalid"),
                                           ("ong2", 200, "ong2@bola.invalid"),
                                           ("doador1", 200, "doador1@bola.invalid"),
                                           ("anonimo", 401, None)):
                prova("GET", "/reconecta/auth/me", ator, esperado,
                      conferir=(lambda d, e=email: (_ for _ in ()).throw(AssertionError("perfil alheio"))
                               if d["email"] != e else None) if email else None)
                prova("GET", "/reconecta/auth/me/dados", ator, esperado,
                      conferir=(lambda d, e=email: (_ for _ in ()).throw(AssertionError("exportação alheia"))
                               if d["titular"]["email"] != e else None) if email else None)

            for ator, esperado in (("doador1", 200), ("doador2", 404),
                                    ("empresa1", 404), ("anonimo", 404), ("ong1", 200)):
                prova("GET", f"/reconecta/contribuicoes/{ids['entrega']}/foto", ator, esperado)

            for ator, esperado, privado in (("doador1", 200, True),
                                             ("doador2", 200, False),
                                             ("empresa2", 200, False),
                                             ("anonimo", 200, False)):
                prova("GET", f"/reconecta/excedentes/{ids['pessoa1']}", ator, esperado,
                      conferir=lambda d, sim=privado: assert_privado_excedente(d, sim))

            # GETs legados são públicos em campos básicos, mas e-mail/telefone
            # só devem aparecer com token administrativo válido.
            for grupo, identificador in (("estabelecimentos", usuarios["empresa1"]),
                                         ("instituicoes", ids["legacy_instituicao"])):
                for caminho in (f"/reconecta/{grupo}/", f"/reconecta/{grupo}/{identificador}"):
                    for ator in ("empresa1", "empresa2", "doador1", "anonimo"):
                        prova("GET", caminho, ator, 200,
                              conferir=lambda d: assert_contato(d, False),
                              classificacao="admin_leitura")
                    prova("GET", caminho, "anonimo", 200, admin=True,
                          conferir=lambda d: assert_contato(d, True),
                          classificacao="admin_leitura")

            # Operações por objeto: negativas antes da ação legítima para não
            # confundir autorização com transição de estado (409).
            for sufixo, alvo, dono, colega, outro, sucesso in (
                    ("/cancelar-reserva", "reservado1", "ong1", "ong2", "doador1", 200),
                    ("/confirmar-retirada", "reservado2", "empresa2", "empresa1", "doador1", 200),
                    ("", "cancelavel", "empresa1", "empresa2", "doador1", 204)):
                metodo = "DELETE" if not sufixo else "POST"
                rota = f"/reconecta/excedentes/{ids[alvo]}{sufixo}"
                for ator, esperado in ((colega, 404), (outro, 404), ("anonimo", 401), (dono, sucesso)):
                    prova(metodo, rota, ator, esperado)

            # O publicador também pode cancelar a reserva; usar outro objeto.
            prova("POST", f"/reconecta/excedentes/{ids['reservado3']}/cancelar-reserva",
                  "empresa1", 200)

            for acao, alvo in (("receber", "entrega"), ("nao-recebida", "nao_recebida")):
                rota = f"/reconecta/painel/contribuicoes/{ids[alvo]}/{acao}"
                for ator, esperado in (("ong2", 404), ("doador1", 403),
                                        ("anonimo", 401), ("ong1", 200)):
                    prova("POST", rota, ator, esperado)

            rota = f"/reconecta/painel/doacoes/{ids['pedido_vazio']}"
            for ator, esperado in (("ong2", 404), ("doador1", 403),
                                    ("anonimo", 401), ("ong1", 204)):
                prova("DELETE", rota, ator, esperado)

            # Criar/reservar são capacidades por perfil; outro titular do mesmo
            # perfil também pode criar o próprio objeto ou reservar oferta livre.
            prazo = (agora_brasilia_sem_fuso() + timedelta(days=1)).isoformat()
            validade = (hoje_brasilia() + timedelta(days=2)).isoformat()
            item = {"nome": "Pão", "categoria": "Padaria", "quantidade": 1,
                    "unidade_medida": "kg"}
            for ator, esperado in (("ong1", 201), ("ong2", 201),
                                    ("doador1", 403), ("anonimo", 401)):
                prova("POST", "/reconecta/painel/doacoes", ator, esperado,
                      json_={"receber_ate": prazo, "itens": [item]}, classificacao="papel")
            for ator, esperado in (("ong1", 200), ("ong2", 200),
                                    ("doador1", 403), ("anonimo", 401)):
                prova("POST", "/reconecta/ia/interpretar-pedido", ator, esperado,
                      json_={"texto": "Preciso de pão hoje"}, classificacao="papel")
            for ator, esperado in (("empresa1", 200), ("doador1", 200),
                                    ("ong1", 200), ("anonimo", 401)):
                prova("POST", "/reconecta/ia/sugerir-destino", ator, esperado,
                      json_={"texto": "Tenho pão fresco para doar"}, classificacao="sessao")
            for ator, esperado, alvo in (("ong1", 200, "livre1"),
                                          ("ong2", 200, "livre2"),
                                          ("empresa1", 403, "pessoa1"),
                                          ("doador1", 403, "livre2"),
                                          ("anonimo", 401, "pessoa1")):
                prova("POST", f"/reconecta/excedentes/{ids[alvo]}/reservar", ator,
                      esperado, classificacao="papel")

            for ator, esperado in (("empresa1", 201), ("empresa2", 201),
                                    ("doador1", 201), ("anonimo", 401)):
                corpo = {"retirar_ate": prazo, "itens": [{**item, "validade": validade}],
                         "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True}
                if ator == "doador1":
                    corpo.update(nao_caseiro=True, retirada={"logradouro": "Rua Teste",
                                 "numero": "7", "bairro": "Centro", "municipio": "São Paulo",
                                 "uf": "SP", "cep": "01000000"})
                prova("POST", "/reconecta/excedentes", ator, esperado,
                      json_=corpo, classificacao="papel")

            for ator, esperado in (("doador1", 201), ("doador2", 201),
                                    ("ong1", 409), ("anonimo", 401)):
                formulario = {"item_id": str(ids["item_pedido1"]), "quantidade": "1",
                              "validade": validade, "foto": (BytesIO(b"\xff\xd8\xff\xd9"), "foto.jpg"),
                              **{chave: "sim" for chave in (
                                  "dentro_validade", "embalagem_ok", "armazenado_ok", "nao_caseiro")}}
                prova("POST", f"/reconecta/publico/doacoes/{ids['pedido1']}/contribuicoes",
                      ator, esperado, data=formulario, classificacao="papel")

            for ator in ("ong1", "ong2", "empresa1", "empresa2", "doador1", "doador2"):
                novo = f"{ator}.novo@bola.invalid"
                prova("PUT", "/reconecta/auth/me", ator, 200,
                      json_={"email": novo}, classificacao="sessao",
                      conferir=lambda d, e=novo: assert_email(d, e))
                assert email_de(ator) == novo
            prova("PUT", "/reconecta/auth/me", "anonimo", 401,
                  json_={"email": "anonimo@bola.invalid"}, classificacao="sessao")

            # Rotas administrativas legadas: o token, não o cookie, é o dono.
            # Todo perfil e a sessão ausente recebem 401 sem X-Admin-Token.
            exemplos = {"doacoes": ids["pedido1"], "estabelecimentos": usuarios["empresa1"],
                        "instituicoes": ids["legacy_instituicao"]}
            for operacao, classe in ESCRITAS.items():
                if classe != "admin":
                    continue
                metodo, modelo = operacao.split(" ", 1)
                grupo = modelo.split("/")[2]
                rota_admin = modelo.replace("{id}", str(exemplos[grupo]))
                for ator in ("ong1", "ong2", "empresa1", "doador1", "anonimo"):
                    prova(metodo, rota_admin, ator, 401, json_={}, classificacao="admin")

            prova("PUT", f"/reconecta/doacoes/{ids['pedido1']}", "anonimo", 200,
                  json_={"status": "DISPONIVEL"}, admin=True, classificacao="admin")
            prova("DELETE", f"/reconecta/doacoes/{ids['pedido_admin']}", "anonimo", 200,
                  admin=True, classificacao="admin")
            prova("POST", "/reconecta/doacoes/", "anonimo", 201,
                  json_={"estabelecimento_id": usuarios["ong1"],
                         "data_limite_retirada": prazo, "status": "DISPONIVEL"},
                  admin=True, classificacao="admin")

            # Logout não exige sessão e só encerra a sessão do solicitante.
            for ator in ("ong1", "ong2", "doador1", "anonimo"):
                prova("POST", "/reconecta/auth/logout", ator, 204, classificacao="sessao")

            # Exclusão da própria conta por último: cada usuário pode excluir
            # só a si. Outro usuário chamar /me exclui apenas a própria conta.
            for ator in ("ong1", "ong2", "empresa1", "empresa2", "doador1", "doador2"):
                outros = {nome: email_de(nome) for nome in usuarios if nome != ator}
                prova("DELETE", "/reconecta/auth/me", ator, 204, classificacao="sessao")
                assert email_de(ator).endswith("@removido.invalid")
                assert all(email_de(nome) == endereco for nome, endereco in outros.items())
            prova("DELETE", "/reconecta/auth/me", "anonimo", 401,
                  classificacao="sessao")

    # O relatório contém apenas nomes de papéis, caminhos normalizados e códigos.
    def normalizar(rota):
        return re.sub(r"/[0-9]+(?=/|\?|$)", "/{id}", rota.split("?", 1)[0])

    exercitadas = {f"{linha['metodo']} {normalizar(linha['rota'])}" for linha in resultados}
    for operacao, classe in ESCRITAS.items():
        if classe != "publica" and re.sub(r"/{[^}]+}", "/{id}", operacao) not in exercitadas:
            raise AssertionError(f"Escrita privada classificada sem prova dinâmica: {operacao}")
    for operacao in LEITURAS_PRIVADAS:
        if re.sub(r"/{[^}]+}", "/{id}", operacao) not in exercitadas:
            raise AssertionError(f"Leitura privada classificada sem prova dinâmica: {operacao}")

    relatorio = {
        "fonte": "swagger.json", "banco": "SQLite em memória", "contas_ficticias": 6,
        "operacoes_swagger": len(operacoes), "escritas_classificadas": len(ESCRITAS),
        "leituras_privadas_classificadas": len(LEITURAS_PRIVADAS),
        "requisicoes_verificadas": len(resultados), "falhas": 0,
        "classes": {classe: sorted(op for op, tipo in ESCRITAS.items() if tipo == classe)
                    for classe in sorted(set(ESCRITAS.values()))},
        "matriz": [{**linha, "rota": normalizar(linha["rota"])} for linha in resultados],
    }
    destino = Path(saida) if saida else RAIZ / "relatorios" / "seguranca" / "autorizacao.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    return relatorio


def assert_email(dados, esperado):
    assert dados["email"] == esperado, "atualização de perfil alheio"


def assert_privado_excedente(dados, autorizado):
    assert ("retirada_informada" in dados) == autorizado, "endereço privado do publicador"


def assert_contato(dados, admin):
    registros = dados if isinstance(dados, list) else [dados]
    assert registros, "CRUD legado vazio"
    for registro in registros:
        assert ("email" in registro and "telefone" in registro) == admin, "contato administrativo exposto"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Saída JSON da prova")
    parser.add_argument("--inventory", type=Path, help="Validar somente um Swagger alternativo")
    args = parser.parse_args()
    if args.inventory:
        print(f"Swagger classificado: {len(inventario(json.loads(args.inventory.read_text(encoding='utf-8'))))} operações")
    else:
        resumo = main(args.output)
        print(f"BOLA/IDOR: {resumo['requisicoes_verificadas']} requisições; "
              f"{resumo['escritas_classificadas']} escritas do Swagger classificadas; 0 falhas")
