"""Foto do alimento mostrando a validade na oferta de excedente (rodada 19).

Antes (main a4a5427), POST /reconecta/excedentes publicava só com JSON e a oferta não tinha
foto: quem recebia via apenas "Arroz, validade 2026-12-01", digitado por quem doou. A doação
para pedido (contribuição) já exigia foto. Agora a oferta exige foto (JPEG, PNG ou WebP
reais pela assinatura, até 5 MB), guardada no banco sem metadados, que só quem publicou e
ONGs logadas veem.
"""
import io
import json
import os
import struct
import zlib
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

os.environ["DATABASE_URL"] = "sqlite://"

from app import app  # noqa: E402
from foto_oferta import JPEG, com_foto  # noqa: E402
from fuso import agora_brasilia_sem_fuso  # noqa: E402
from models import Doador, Estabelecimento, Excedente, db  # noqa: E402
from test_integridade_banco import postgres_temporario  # noqa: E402,F401  (fixture opcional)

GPS = b"GPSLatitude -22.9056 GPSLongitude -47.0608"
# o mesmo JPEG com um bloco EXIF (APP1) e um comentário (COM) que celulares gravam
JPEG_EXIF = (JPEG[:2] + b"\xff\xe1" + struct.pack(">H", 2 + 6 + len(GPS)) + b"Exif\x00\x00" + GPS
             + b"\xff\xfe\x00\x0dmaria@x.com" + JPEG[2:])


def _png(*extras):
    def pedaco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))
    ihdr = pedaco(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = pedaco(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    return (b"\x89PNG\r\n\x1a\n" + ihdr + b"".join(pedaco(t, d) for t, d in extras) + idat
            + pedaco(b"IEND", b""))


def _webp_com_exif():
    def pedaco(tipo, dados):
        return tipo + struct.pack("<I", len(dados)) + dados + (b"\x00" if len(dados) % 2 else b"")
    vp8x = pedaco(b"VP8X", bytes([0x08 | 0x04, 0, 0, 0]) + b"\x00\x00\x00\x00\x00\x00")
    corpo = b"WEBP" + vp8x + pedaco(b"VP8L", b"\x2f\x00\x00\x00\x00") + pedaco(b"EXIF", GPS) + pedaco(b"XMP ", b"<x>gps</x>")
    return b"RIFF" + struct.pack("<I", len(corpo)) + corpo


@pytest.fixture(autouse=True)
def banco():
    app.config["TESTING"] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
    from Excedentes import _cotas
    _cotas.clear()
    yield


def contas():
    with app.app_context():
        endereco = "Av. Paulista, 1578 - Bela Vista, São Paulo/SP - 01310200"
        registros = {
            "ong": Estabelecimento(nome="ONG Prato", cnpj="11444777000161", email="ong@x.test", telefone="1",
                                   endereco=endereco, sem_fins_lucrativos=True, atividade_alimentar=False),
            "ong2": Estabelecimento(nome="ONG Dois", cnpj="11222333000181", email="ong2@x.test", telefone="1",
                                    endereco=endereco, sem_fins_lucrativos=True, atividade_alimentar=False),
            "mercado": Estabelecimento(nome="Mercado", cnpj="45723174000110", email="m@x.test", telefone="1",
                                       endereco=endereco, sem_fins_lucrativos=False, atividade_alimentar=True),
            "pessoa": Doador(nome="Joana Lima", cpf="52998224725", email="joana@x.test", telefone="1"),
            "outra": Doador(nome="Bia Reis", cpf="11144477735", email="bia@x.test", telefone="1"),
        }
        db.session.add_all(registros.values())
        db.session.commit()
        return {chave: ("doador" if isinstance(r, Doador) else "empresa", r.id) for chave, r in registros.items()}


def cliente(conta=None):
    c = app.test_client()
    if conta:
        with c.session_transaction() as s:
            s["tipo"], s["usuario_id"] = conta
    return c


def oferta(pessoa_fisica=True):
    prazo = agora_brasilia_sem_fuso() + timedelta(hours=6)
    corpo = {"retirar_ate": prazo.isoformat(timespec="seconds"),
             "itens": [{"nome": "Arroz", "categoria": "Grãos e cereais", "quantidade": 5,
                        "unidade_medida": "kg", "validade": (prazo.date() + timedelta(days=60)).isoformat()}],
             "dentro_validade": True, "embalagem_ok": True, "armazenado_ok": True}
    if pessoa_fisica:
        corpo.update(nao_caseiro=True, retirada={"logradouro": "Rua Barão de Jaguara", "numero": "1000",
                                                 "bairro": "Centro", "municipio": "Campinas", "uf": "SP"})
    return corpo


def test_oferta_sem_foto_nao_publica_nem_no_json_antigo():
    c = contas()
    for conta, corpo in ((c["pessoa"], oferta()), (c["mercado"], oferta(False))):
        antigo = cliente(conta).post("/reconecta/excedentes", json=corpo)  # antes: 201 sem foto
        assert antigo.status_code == 400, antigo.json
        assert antigo.json["campos"] == {"foto": "Envie uma foto do alimento mostrando a validade (JPEG, PNG ou WebP)."}
        sem_arquivo = cliente(conta).post("/reconecta/excedentes", data={"dados": json.dumps(corpo)})
        assert sem_arquivo.status_code == 400 and "foto" in sem_arquivo.json["campos"]
    # erros de dados e de foto voltam juntos, cada um no seu campo
    junto = cliente(c["pessoa"]).post("/reconecta/excedentes", data={"dados": "não é json"})
    assert {"foto", "itens", "retirar_ate"} <= set(junto.json["campos"])
    with app.app_context():
        assert Excedente.query.count() == 0


@pytest.mark.parametrize("nome,conteudo", [
    ("validade.jpg", b"isto nao e uma foto"),
    ("validade.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ("validade.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20),       # assinatura PNG sem estrutura
    ("validade.jpg", JPEG[:12]),                                 # JPEG cortado
    ("validade.gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"),
    ("validade.heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"),
    ("validade.jpg", b""),
])
def test_foto_falsa_e_recusada_pela_assinatura(nome, conteudo):
    c = contas()
    resposta = cliente(c["pessoa"]).post("/reconecta/excedentes", data=com_foto(oferta(), conteudo, nome))
    assert resposta.status_code == 400, resposta.json
    assert resposta.json["campos"] == {"foto": "Envie uma foto JPEG, PNG ou WebP válida."}
    with app.app_context():
        assert Excedente.query.count() == 0


def test_limite_de_tamanho_da_foto():
    c = contas()
    pessoa = cliente(c["pessoa"])
    grande = JPEG[:-2] + b"\x00" * (5 * 1024 * 1024 - len(JPEG) + 1) + JPEG[-2:]  # 5 MB + 1 byte
    acima = pessoa.post("/reconecta/excedentes", data=com_foto(oferta(), grande))
    assert acima.status_code == 400 and acima.json["campos"] == {"foto": "A foto deve ter até 5 MB."}
    enorme = pessoa.post("/reconecta/excedentes", data=com_foto(oferta(), b"\xff\xd8\xff" + b"\x00" * (7 * 1024 * 1024)))
    assert enorme.status_code == 413 and "foto" in enorme.json["campos"]
    no_limite = JPEG[:-2] + b"\x00" * (5 * 1024 * 1024 - len(JPEG)) + JPEG[-2:]  # exatamente 5 MB
    assert pessoa.post("/reconecta/excedentes", data=com_foto(oferta(), no_limite)).status_code == 201


def test_metadados_saem_antes_de_gravar():
    """A foto do celular traz GPS no EXIF; ela vai para outras organizações."""
    c = contas()
    pessoa = cliente(c["pessoa"])
    casos = (("jpg", JPEG_EXIF, "image/jpeg"),
             ("png", _png((b"tEXt", b"GPS\x00" + GPS), (b"eXIf", GPS)), "image/png"),
             ("webp", _webp_com_exif(), "image/webp"))
    for tipo, foto, mime in casos:
        assert GPS in foto
        publicado = pessoa.post("/reconecta/excedentes", data=com_foto(oferta(), foto, f"v.{tipo}"))
        assert publicado.status_code == 201, publicado.json
        baixada = pessoa.get(publicado.json["foto_url"])
        assert baixada.status_code == 200 and baixada.mimetype == mime
        assert GPS not in baixada.data and b"maria@x.com" not in baixada.data and b"gps" not in baixada.data
        assert baixada.data[:3] == foto[:3]
    assert pessoa.get("/reconecta/excedentes/1/foto").data == JPEG  # sem EXIF, a JPEG fica igual à original
    webp = pessoa.get("/reconecta/excedentes/3/foto").data
    assert struct.unpack("<I", webp[4:8])[0] == len(webp) - 8 and webp[20] & 0x0C == 0


def test_so_quem_publicou_e_ongs_logadas_veem_a_foto():
    c = contas()
    publicado = cliente(c["pessoa"]).post("/reconecta/excedentes", data=com_foto(oferta()))
    assert publicado.status_code == 201
    id_, url = publicado.json["id"], publicado.json["foto_url"]
    assert url == f"/reconecta/excedentes/{id_}/foto"

    def ver(conta):
        return cliente(c[conta] if conta else None).get(url)

    for conta, esperado in (("pessoa", 200), ("ong", 200), ("ong2", 200),
                            ("outra", 404), ("mercado", 404), (None, 404)):
        resposta = ver(conta)
        assert resposta.status_code == esperado, conta
        detalhe = cliente(c[conta] if conta else None).get(f"/reconecta/excedentes/{id_}").json
        assert ("foto_url" in detalhe) == (esperado == 200), conta
        if esperado == 200:
            assert resposta.data == JPEG
            assert resposta.headers["X-Content-Type-Options"] == "nosniff"
            assert resposta.headers["Cache-Control"] == "private, no-store"
        else:
            assert resposta.json == {"codigo": "FOTO_NAO_ENCONTRADA", "mensagem": "Foto não encontrada."}
    # lista pública nunca leva a foto; id inexistente também é 404
    assert all("foto_url" not in x for x in cliente().get("/reconecta/excedentes").json)
    assert cliente(c["ong"]).get("/reconecta/excedentes/999/foto").status_code == 404

    # reservada: a ONG que reservou continua vendo; a outra ONG deixa de ver
    assert cliente(c["ong"]).post(f"/reconecta/excedentes/{id_}/reservar").status_code == 200
    assert ver("ong").status_code == 200 and ver("pessoa").status_code == 200
    assert ver("ong2").status_code == 404
    assert "foto_url" in cliente(c["ong"]).get("/reconecta/excedentes/reservas").json[0]
    assert "foto_url" in cliente(c["pessoa"]).get("/reconecta/excedentes/meus").json[0]


def test_empresa_publica_com_foto_e_oferta_antiga_sem_foto_continua_valida():
    c = contas()
    publicado = cliente(c["mercado"]).post("/reconecta/excedentes", data=com_foto(oferta(False), _png(), "v.png"))
    assert publicado.status_code == 201
    assert cliente(c["ong"]).get(publicado.json["foto_url"]).mimetype == "image/png"
    with app.app_context():
        antiga = Excedente(estabelecimento_id=c["mercado"][1], retirar_ate=agora_brasilia_sem_fuso() + timedelta(hours=3))
        db.session.add(antiga)
        db.session.commit()
        antiga_id = antiga.id
    detalhe = cliente(c["ong"]).get(f"/reconecta/excedentes/{antiga_id}")
    assert detalhe.status_code == 200 and "foto_url" not in detalhe.json
    assert cliente(c["mercado"]).get(f"/reconecta/excedentes/{antiga_id}/foto").status_code == 404


def test_lista_publica_nao_carrega_a_foto_do_banco():
    """foto_dados é carregada sob demanda: a vitrine não lê megabytes por oferta."""
    c = contas()
    cliente(c["pessoa"]).post("/reconecta/excedentes", data=com_foto(oferta()))
    from sqlalchemy import event
    consultas = []
    with app.app_context():
        ouvir = lambda *a: consultas.append(a[2])  # noqa: E731
        event.listen(db.engine, "before_cursor_execute", ouvir)
        try:
            assert len(app.test_client().get("/reconecta/excedentes").json) == 1
            cliente(c["ong"]).get("/reconecta/excedentes/1")
        finally:
            event.remove(db.engine, "before_cursor_execute", ouvir)
    assert consultas and not any("foto_dados" in sql for sql in consultas)


def test_lgpd_exporta_e_exclusao_apaga_a_foto():
    c = contas()
    for conta, corpo in (("pessoa", oferta()), ("mercado", oferta(False))):
        publicado = cliente(c[conta]).post("/reconecta/excedentes", data=com_foto(oferta() if conta == "pessoa" else corpo))
        assert publicado.status_code == 201
        id_ = publicado.json["id"]
        exportado = cliente(c[conta]).get("/reconecta/auth/me/dados").json
        assert exportado["excedentes_publicados"][0]["foto_validade"] == {
            "tipo": "jpg", "url": f"/reconecta/excedentes/{id_}/foto"}
        assert "foto_dados" not in json.dumps(exportado)
        assert cliente(c[conta]).delete("/reconecta/auth/me").status_code == 204
        with app.app_context():
            excedente = db.session.get(Excedente, id_)
            assert excedente.foto_dados is None and excedente.foto_tipo is None
        assert cliente(c["ong"]).get(f"/reconecta/excedentes/{id_}/foto").status_code == 404


def test_migracao_sqlite_acrescenta_colunas_sem_perder_ofertas(tmp_path):
    from migracoes import aplicar_migracoes
    engine = create_engine(f"sqlite:///{tmp_path / 'antigo.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE estabelecimentos (id INTEGER PRIMARY KEY, nome TEXT)"))
        c.execute(text("CREATE TABLE doadores (id INTEGER PRIMARY KEY, nome TEXT)"))
        c.execute(text("""CREATE TABLE excedentes (id INTEGER PRIMARY KEY,
            estabelecimento_id INTEGER REFERENCES estabelecimentos(id), doador_id INTEGER REFERENCES doadores(id),
            retirada_endereco VARCHAR(200), retirar_ate DATETIME NOT NULL,
            status VARCHAR(20) DEFAULT 'DISPONIVEL' NOT NULL, reservado_por_id INTEGER, reservado_em DATETIME,
            retirado_em DATETIME, observacao VARCHAR(200), criado_em DATETIME NOT NULL)"""))
        c.execute(text("INSERT INTO estabelecimentos VALUES (1, 'Mercado')"))
        c.execute(text("INSERT INTO excedentes (id, estabelecimento_id, retirar_ate, criado_em) "
                       "VALUES (7, 1, '2030-01-01 10:00:00', '2026-10-14 10:00:00')"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)  # idempotente
    colunas = {c["name"]: c for c in inspect(engine).get_columns("excedentes")}
    assert colunas["foto_tipo"]["nullable"] and colunas["foto_dados"]["nullable"]
    with engine.begin() as c:
        assert c.execute(text("SELECT id, foto_tipo, foto_dados FROM excedentes")).all() == [(7, None, None)]
        c.execute(text("UPDATE excedentes SET foto_tipo = 'jpg', foto_dados = :d WHERE id = 7"), {"d": JPEG})
        assert c.execute(text("SELECT foto_dados FROM excedentes")).scalar() == JPEG


@pytest.mark.parametrize("fixture", ["schema_main_a0ba325.sql", "schema_main_58cd1ee.sql"])
def test_postgresql_migra_o_schema_publicado(postgres_temporario, fixture):  # noqa: F811
    """a0ba325 é a main publicada (schema igual ao da a4a5427); 58cd1ee é anterior à pessoa física."""
    from migracoes import aplicar_migracoes
    engine = postgres_temporario
    schema = (Path(__file__).parent / "fixtures" / fixture).read_text(encoding="utf-8")
    with engine.begin() as c:
        for comando in schema.split(";"):
            if comando.strip():
                c.execute(text(comando))
        c.execute(text("INSERT INTO estabelecimentos (id, nome, cnpj, email, telefone, endereco) VALUES "
                       "(1, 'Mercado', '45723174000110', 'm@x.test', '1', 'Rua A, 1 - Centro, Campinas/SP')"))
        c.execute(text("INSERT INTO excedentes (id, estabelecimento_id, retirar_ate) VALUES (5, 1, '2030-01-01')"))
    aplicar_migracoes(engine)
    aplicar_migracoes(engine)
    colunas = {c["name"]: c for c in inspect(engine).get_columns("excedentes")}
    assert colunas["foto_tipo"]["nullable"] and colunas["foto_dados"]["nullable"]
    assert str(colunas["foto_dados"]["type"]).upper() == "BYTEA"
    with engine.begin() as c:
        assert c.execute(text("SELECT estabelecimento_id, foto_tipo FROM excedentes WHERE id = 5")).one() == (1, None)
        c.execute(text("UPDATE excedentes SET foto_tipo = 'jpg', foto_dados = :d WHERE id = 5"), {"d": JPEG})
        assert bytes(c.execute(text("SELECT foto_dados FROM excedentes WHERE id = 5")).scalar()) == JPEG
    # o schema.sql novo também roda por cima do publicado (ADD COLUMN IF NOT EXISTS)
    atual = (Path(__file__).parent.parent / "schema.sql").read_text(encoding="utf-8")
    with engine.begin() as c:
        for comando in atual.split(";"):
            if comando.strip():
                c.execute(text(comando))
