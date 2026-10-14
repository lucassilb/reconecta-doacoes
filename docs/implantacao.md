# Implantação gratuita: Docker Compose, Supabase e Render

Este guia prepara uma instalação de demonstração sem serviço pago. Não use o banco local `reconecta` nos comandos de prova. O Compose usa `reconecta_dev`, com volume próprio. O Render executa a aplicação em Docker; o Supabase guarda os dados e os bytes das fotos.

## 1. Rodar localmente com Docker Compose

1. Instale Docker Engine/Desktop com Compose e confirme `docker version` e `docker compose version`.
2. Opcionalmente copie `.env.example` para `.env` e defina `POSTGRES_PASSWORD` e `SECRET_KEY` para seu ambiente de desenvolvimento. Os padrões do Compose (`dev-only-*`) são somente para uma máquina de teste; não os reutilize em um serviço acessível pela internet. Para a senha usada na URL, codifique caracteres reservados como `%40` para `@`.
3. Na raiz do repositório, execute:

   ```bash
   docker compose build app
   docker compose up -d --wait
   curl --fail http://localhost:5000/reconecta/saude
   ```

   A resposta esperada é `{"status":"ok","banco":"ok"}`. A página inicial fica em `http://localhost:5000/` e a API em `/swagger`.

4. Para desligar preservando o banco de desenvolvimento: `docker compose down`. Para descartar **somente o volume de teste deste Compose**: `docker compose down -v`.

O perfil opcional `ia` inicia um Ollama local ao Compose:

```bash
docker compose --profile ia up -d --wait
docker compose exec ollama ollama pull qwen2.5:3b
```

O serviço Flask recebe `OLLAMA_URL=http://ollama:11434`. A integração entre contêineres requer o ajuste de lista de hosts permitidos em `llm_service.py` da Frente C; até sua integração, a rota de IA mantém o fallback local de regras/classificador. O modelo do Ollama é baixado somente no perfil `ia`.

## 2. Criar o banco Supabase

1. Crie um projeto no plano gratuito do Supabase e defina uma senha forte. Não importe o banco local de produção nem use o nome `reconecta` em provas.
2. No projeto, abra **Connect** e escolha **Session pooler** (porta 5432, IPv4). Copie a URL apresentada, com usuário no formato `postgres.<project-ref>`. Substitua `[YOUR-PASSWORD]` pela senha, codificando caracteres reservados na URL. Não use a URL de Transaction pooler (porta 6543).
3. Guarde essa URL como `DATABASE_URL` no Render. O aplicativo converte `postgres://` e `postgresql://` para `postgresql+psycopg://` e exige `sslmode=require` para host remoto. Não salve a URL em Git.

O esquema é criado no primeiro boot. A migração idempotente adiciona `contribuicoes.foto_dados` (`BYTEA` no PostgreSQL, `BLOB` no SQLite), preservando linhas antigas. Fotos novas são servidas a partir do banco; arquivos legados continuam acessíveis pelo mesmo endpoint privado enquanto existirem no disco da instalação antiga.

## 3. Criar o serviço Render

1. Depois de integrar e publicar a branch `main` do repositório novo [`lucassilb/reconecta-doacoes`](https://github.com/lucassilb/reconecta-doacoes), faça login no Render com o GitHub e abra [o Blueprint deste repositório](https://render.com/deploy?repo=https://github.com/lucassilb/reconecta-doacoes). Autorize o acesso ao repositório privado pelo login do GitHub. Confira que o serviço `reconecta` é **Web Service**, `runtime: docker` e `plan: free` antes de confirmar. O Blueprint não precisa de chave de API do Render. Se a tela exigir pagamento ou cartão, interrompa a criação.
2. No primeiro Blueprint, informe `DATABASE_URL` com a URL do Session pooler. `SECRET_KEY` é gerada pelo Render. `COOKIE_SEGURO=1` ativa cookie HTTPS e `ProxyFix`. `ADMIN_TOKEN` é opcional; configure somente se precisar da escrita dos CRUDs administrativos legados. `GROQ_API_KEY` também é opcional: só uma chave do Groq Free, sem cartão, ativa a LLM externa; sem ela, o classificador e as regras continuam ativos. Em Blueprint já existente, edite valores `sync: false` diretamente no serviço do Render. Nunca cole a chave no repositório.
3. Após o deploy, abra `https://<servico>.onrender.com/reconecta/saude`; deve responder `200` com banco `ok`. Confira login e upload de foto em uma instalação de teste, pois o disco do Render gratuito é efêmero. O aplicativo mantém fotos novas no banco para sobreviver a reinícios.

O plano gratuito pode suspender o serviço após inatividade e tem cotas de uso. A URL pública só existe após o Regente criar o serviço. O `autoDeployTrigger: checksPass` publica novos commits da branch conectada depois que os checks do GitHub Actions passam.

## 4. Ativar CI/CD no GitHub

O workflow `.github/workflows/ci.yml` roda em push/PR para `main` e por acionamento manual. Executa Python 3.12 e pytest com JUnit; Bandit; Trivy em arquivos e imagem com tabelas/SARIF; e build + healthcheck do Compose. Artefatos ficam em cada execução do Actions. Achados Bandit altos e Trivy críticos com correção disponível bloqueiam o deploy.

O Blueprint usa `autoDeployTrigger: checksPass`; essa é a rota normal de CD e não pede chave de API nem segredo de GitHub ao usuário. Há também um job **opcional** de Deploy Hook para acionamento manual (`workflow_dispatch`) em `main`, após todos os jobs passarem. Para usá-lo, copie o **Deploy Hook URL** do serviço Render e crie no GitHub o segredo de Actions `RENDER_DEPLOY_HOOK_URL`. Sem esse segredo, o job termina com aviso. Trate o hook como segredo: não cole a URL em arquivos ou logs.

## 5. Segurança operacional

O servidor de desenvolvimento escuta só em `127.0.0.1` por padrão; `FLASK_RUN_HOST` pode alterar esse valor. No Docker, gunicorn escuta em `0.0.0.0`. Em HTTPS, `COOKIE_SEGURO=1` ativa o cookie seguro, `ProxyFix` e HSTS. Todas as respostas recebem proteção contra MIME sniffing e frames, política de referenciador, política de permissões e CSP compatível com as páginas e com Chart.js/Google Fonts. A CSP permite atributos de estilo inline para as barras e prévias de foto criadas pelo JavaScript existente; scripts inline e `unsafe-eval` permanecem bloqueados.

O logger `reconecta.auditoria` emite uma linha JSON por evento de autenticação, cadastro, alteração de conta, pedido, doação e uso do token administrativo. Inclui data UTC, tipo e ID do ator, IP e resultado; não inclui credenciais, documentos, e-mail nem foto. Os logs devem ser guardados conforme a política do ambiente. POSTs de contribuição têm cota de 20 por hora por usuário **em cada processo**; reinício ou outro worker tem cota independente. Prova de posse de e-mail/CNPJ e limite global por IP continuam riscos residuais documentados em `docs/stride.md`.

## Referências dos provedores

- [Render Blueprint YAML](https://render.com/docs/blueprint-spec) e [plano gratuito](https://render.com/docs/free)
- [Render Deploy Hooks](https://render.com/docs/deploy-hooks)
- [Supabase: conexão PostgreSQL e Session pooler](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Trivy Action](https://github.com/aquasecurity/trivy-action#readme)

## Estado publicado e dois cuidados com a `DATABASE_URL`

- Site no ar: `https://reconecta-iota.onrender.com` (Render, plano gratuito), ligado ao PostgreSQL do Supabase em São Paulo, desde 2026-10-13.
- **Senha com símbolos**: se a senha do banco tiver `@`, `/`, `:`, `#`, `?`, `%`, `,` ou parênteses, ela precisa ir na URL em formato codificado (`@` vira `%40`, `/` vira `%2F`), senão o endereço é cortado no lugar errado (foi a causa da primeira falha de publicação: `failed to resolve host`). O mais simples é usar senha só com letras e números.
- **Quebra de linha no fim**: colar a URL com linha em branco depois de `/postgres` fazia a aplicação procurar um banco chamado `postgres` seguido de quebras de linha (`database "postgres\n\n" does not exist`). A aplicação agora remove espaços e quebras de linha no início e no fim da `DATABASE_URL` (`app.py`, função `_database_url`; teste em `tests/test_nuvem.py`).
