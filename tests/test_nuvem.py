"""Contratos de nuvem sem tocar em banco ou servico externo."""
import os
import asyncio
import json
import subprocess
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.engine import make_url

os.environ["DATABASE_URL"] = "sqlite://"
from app import _database_url, app  # noqa: E402
from Auth import _auditoria  # noqa: E402
from Contribuicoes import _tentativas_doacoes  # noqa: E402
from migracoes import _migrar_foto_contribuicao  # noqa: E402
from models import Contribuicao, Doacao, Doador, Estabelecimento, ItemDoacao, db  # noqa: E402

FOTO = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"


@pytest.fixture
def cliente(tmp_path):
    instancia, teste = app.instance_path, app.config["TESTING"]
    app.instance_path = str(tmp_path)
    app.config["TESTING"] = True
    _tentativas_doacoes.clear()
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
    yield app.test_client()
    with app.app_context():
        db.session.remove()
        db.drop_all()
    app.instance_path, app.config["TESTING"] = instancia, teste
    _tentativas_doacoes.clear()


def test_url_postgres_local_e_supabase():
    assert _database_url(None) == "sqlite:///reconecta.db"
    assert _database_url("sqlite://") == "sqlite://"
    local = make_url(_database_url("postgres://u:p@localhost:5432/dev"))
    assert local.drivername == "postgresql+psycopg"
    assert "sslmode" not in local.query
    remota = make_url(_database_url(
        "postgresql://u:p@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?application_name=reconecta"))
    assert remota.drivername == "postgresql+psycopg"
    assert remota.query["sslmode"] == "require"
    assert remota.query["application_name"] == "reconecta"
    colada = make_url(_database_url(
        "  postgresql://u:p%2Fx%40y@aws-1-sa-east-1.pooler.supabase.com:5432/postgres\n\n"))
    assert colada.database == "postgres"  # sem a quebra de linha colada no fim
    assert colada.password == "p/x@y"     # senha com símbolos convertidos na URL
    assert _database_url("  \n") == "sqlite:///reconecta.db"
    assert app.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_pre_ping"] is True


def test_saude_consulta_banco_e_sinaliza_falha(cliente, monkeypatch):
    resposta = cliente.get("/reconecta/saude")
    assert resposta.status_code == 200
    assert resposta.json == {"status": "ok", "banco": "ok"}
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "DENY"
    assert "unsafe-eval" not in resposta.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in resposta.headers
    monkeypatch.setitem(app.config, "SESSION_COOKIE_SECURE", True)
    assert cliente.get("/reconecta/saude").headers["Strict-Transport-Security"] == "max-age=31536000"

    def falhar(*_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("sem conexao"))

    monkeypatch.setattr(db.session, "execute", falhar)
    resposta = cliente.get("/reconecta/saude")
    assert resposta.status_code == 503
    assert resposta.json["banco"] == "indisponivel"


def test_migracao_foto_sqlite_idempotente_preserva_linha(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legado.db'}")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE contribuicoes (id INTEGER PRIMARY KEY, foto_arquivo TEXT NOT NULL)"))
        conexao.execute(text("INSERT INTO contribuicoes VALUES (1, 'antiga.jpg')"))
    _migrar_foto_contribuicao(engine)
    _migrar_foto_contribuicao(engine)
    assert sum(c["name"] == "foto_dados" for c in inspect(engine).get_columns("contribuicoes")) == 1
    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT foto_arquivo, foto_dados FROM contribuicoes")).one() == (
            "antiga.jpg", None)
    engine.dispose()


def test_nova_foto_no_banco_e_fallback_legado_com_acesso_privado(cliente):
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado", cnpj="47508411000156", email="mercado@example.org",
                                  telefone="11999998888", endereco="Rua A, 1")
        doador = Doador(nome="Maria", cpf="52998224725", email="maria@example.org",
                        telefone="11999997777")
        db.session.add_all([empresa, doador])
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id,
                        data_limite_retirada=datetime.now() + timedelta(days=3), status="DISPONIVEL")
        db.session.add(pedido)
        db.session.flush()
        item = ItemDoacao(doacao_id=pedido.id, nome="Arroz", categoria="Mercearia",
                          quantidade=10, unidade_medida="kg")
        db.session.add(item)
        db.session.commit()
        doador_id, pedido_id, item_id = doador.id, pedido.id, item.id

    with cliente.session_transaction() as sessao:
        sessao["tipo"] = "doador"
        sessao["usuario_id"] = doador_id
    resposta = cliente.post(f"/reconecta/publico/doacoes/{pedido_id}/contribuicoes", data={
        "item_id": str(item_id), "quantidade": "2", "validade": (date.today() + timedelta(days=4)).isoformat(),
        "dentro_validade": "sim", "embalagem_ok": "sim", "armazenado_ok": "sim", "nao_caseiro": "sim",
        "foto": (BytesIO(FOTO), "arroz.jpg"),
    }, content_type="multipart/form-data")
    assert resposta.status_code == 201, resposta.json
    foto_url = f"/reconecta/contribuicoes/{resposta.json['id']}/foto"
    with app.app_context():
        contribuicao = db.session.get(Contribuicao, resposta.json["id"])
        assert contribuicao.foto_dados == FOTO
        caminho = Path(app.instance_path) / "uploads" / "contribuicoes" / contribuicao.foto_arquivo
        assert caminho.is_file()
        caminho.unlink()
    resposta_foto = cliente.get(foto_url)
    assert resposta_foto.status_code == 200
    assert resposta_foto.data == FOTO
    assert resposta_foto.headers["Cache-Control"] == "private, no-store"
    with app.app_context():
        contribuicao = db.session.get(Contribuicao, resposta.json["id"])
        contribuicao.foto_dados = None
        db.session.commit()
        caminho.write_bytes(FOTO)
    assert cliente.get(foto_url).data == FOTO
    with cliente.session_transaction() as sessao:
        sessao.clear()
    assert cliente.get(foto_url).status_code == 404


def test_auditoria_json_sem_credenciais(cliente, caplog, monkeypatch):
    _auditoria.addHandler(caplog.handler)
    try:
        erro = cliente.post("/reconecta/auth/login", json={
            "identificador": "maria@example.org", "senha": "SenhaSecreta123"})
        assert erro.status_code == 401
        criado = cliente.post("/reconecta/cadastro/doador", json={
            "nome": "Maria Teste", "cpf": "52998224725", "email": "maria@example.org",
            "telefone": "11999998888", "senha": "SenhaSecreta123", "aceite_privacidade": True})
        assert criado.status_code == 201
        editado = cliente.put("/reconecta/auth/me", json={
            "telefone": "11999997777", "senha_atual": "SenhaSecreta123", "nova_senha": "OutraSenha456"})
        assert editado.status_code == 200
        assert cliente.post("/reconecta/auth/logout").status_code == 204
        login = cliente.post("/reconecta/auth/login", json={
            "identificador": "maria@example.org", "senha": "OutraSenha456"})
        assert login.status_code == 200
        monkeypatch.setenv("ADMIN_TOKEN", "token-teste-nao-logar")
        from crud_admin import exigir_admin
        with app.test_request_context("/", headers={"X-Admin-Token": "invalido"}):
            assert exigir_admin()[1] == 401
        with app.test_request_context("/", headers={"X-Admin-Token": "token-teste-nao-logar"}):
            assert exigir_admin() is None
        registros = [json.loads(r.message) for r in caplog.records if r.name == "reconecta.auditoria"]
        assert {(r["evento"], r["resultado"]) for r in registros} >= {
            ("login", "falha"), ("login", "ok"), ("cadastro_doador", "ok"),
            ("dados_editados", "ok"), ("senha_trocada", "ok"), ("logout", "ok"),
            ("token_admin", "negado"), ("token_admin", "aceito")}
        assert all(set(r) == {"data", "evento", "ator_tipo", "ator_id", "ip", "resultado"}
                   for r in registros)
        texto = "\n".join(r.message for r in caplog.records)
        for segredo in ("SenhaSecreta123", "OutraSenha456", "52998224725",
                        "maria@example.org", "token-teste-nao-logar"):
            assert segredo not in texto
    finally:
        _auditoria.removeHandler(caplog.handler)


def test_cota_de_doacoes_por_usuario(cliente, monkeypatch):
    import Contribuicoes
    monkeypatch.setattr(Contribuicoes, "LIMITE_DOACOES", 2)
    with app.app_context():
        empresa = Estabelecimento(nome="Mercado", cnpj="47508411000156", email="mercado@example.org",
                                  telefone="11999998888", endereco="Rua A")
        doador = Doador(nome="Maria", cpf="52998224725", email="maria@example.org",
                        telefone="11999997777")
        db.session.add_all([empresa, doador])
        db.session.flush()
        pedido = Doacao(estabelecimento_id=empresa.id,
                        data_limite_retirada=datetime.now() + timedelta(days=3), status="DISPONIVEL")
        db.session.add(pedido)
        db.session.commit()
        doador_id, pedido_id = doador.id, pedido.id
    with cliente.session_transaction() as sessao:
        sessao["tipo"] = "doador"
        sessao["usuario_id"] = doador_id
    url = f"/reconecta/publico/doacoes/{pedido_id}/contribuicoes"
    assert cliente.post(url, data={}).status_code == 400
    assert cliente.post(url, data={}).status_code == 400
    resposta = cliente.post(url, data={})
    assert resposta.status_code == 429
    assert resposta.json["codigo"] == "MUITAS_TENTATIVAS"
    assert Contribuicoes.LIMITE_DOACOES == 2


@pytest.mark.skipif(not os.getenv("RECON_CSP_URL"), reason="Requer Compose efêmero em RECON_CSP_URL")
def test_csp_navegador_headless(monkeypatch):
    """Roda manualmente no Compose: RECON_CSP_URL=http://localhost:5000 pytest -k csp_navegador."""
    from playwright.sync_api import sync_playwright

    # O driver Node do Playwright também deve nascer sem console externo no Windows.
    criar_processo = asyncio.create_subprocess_exec

    async def criar_oculto(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return await criar_processo(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", criar_oculto)
    base = os.environ["RECON_CSP_URL"].rstrip("/")
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(channel="chrome", headless=True)
        def verificar_paginas(contexto, caminhos):
            contexto.add_init_script("""window.__cspViolations = [];
                document.addEventListener('securitypolicyviolation', e =>
                    window.__cspViolations.push(e.effectiveDirective + ': ' + e.blockedURI));""")
            pagina = contexto.new_page()
            console_csp = []
            pagina.on("console", lambda msg: console_csp.append(msg.text)
                      if "Content Security Policy" in msg.text or "Refused to" in msg.text else None)
            for caminho in caminhos:
                resposta = pagina.goto(base + caminho, wait_until="load", timeout=30000)
                assert resposta.status == 200, caminho
                pagina.wait_for_timeout(600)
                assert pagina.url.split("?", 1)[0].endswith(caminho), caminho
                assert pagina.locator("body").is_visible(), caminho
                assert pagina.evaluate("window.__cspViolations") == [], caminho
            assert console_csp == []

        anonimo = navegador.new_context()
        verificar_paginas(anonimo, ("/", "/cadastro", "/entrar", "/dashboard"))
        contexto = navegador.new_context()
        cadastro = contexto.request.post(base + "/reconecta/cadastro/doador", data={
            "nome": "Teste Navegador", "cpf": "52998224725", "email": "csp@example.invalid",
            "telefone": "11999998888", "senha": "TesteCsp123"})
        if cadastro.status == 409:
            login = contexto.request.post(base + "/reconecta/auth/login", data={
                "identificador": "csp@example.invalid", "senha": "TesteCsp123"})
            assert login.status == 200
        else:
            assert cadastro.status == 201
        verificar_paginas(contexto, ("/painel", "/doacoes/1"))
        navegador.close()
