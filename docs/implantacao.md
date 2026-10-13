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

1. Depois de integrar e publicar a branch principal do projeto, conecte o repositório no Render e crie um **Blueprint** com o `render.yaml` da raiz. Confira que o serviço `reconecta` é **Web Service**, `runtime: docker` e `plan: free` antes de confirmar. Se a tela exigir pagamento ou cartão, interrompa a criação.
2. No primeiro Blueprint, informe `DATABASE_URL` com a URL do Session pooler. `SECRET_KEY` é gerada pelo Render. `COOKIE_SEGURO=1` ativa cookie HTTPS e `ProxyFix`. `ADMIN_TOKEN` é opcional; configure somente se precisar da escrita dos CRUDs administrativos legados. Em Blueprint já existente, edite valores `sync: false` diretamente no serviço do Render.
3. Após o deploy, abra `https://<servico>.onrender.com/reconecta/saude`; deve responder `200` com banco `ok`. Confira login e upload de foto em uma instalação de teste, pois o disco do Render gratuito é efêmero. O aplicativo mantém fotos novas no banco para sobreviver a reinícios.

O plano gratuito pode suspender o serviço após inatividade e tem cotas de uso. A URL pública só existe após o Regente criar o serviço; este repositório não fornece credenciais nem faz publicação automática sem o hook configurado.

## 4. Ativar CI/CD no GitHub

O workflow `.github/workflows/ci.yml` roda em push/PR para `main` e por acionamento manual. Executa Python 3.12 e pytest com JUnit; Bandit; Trivy em arquivos e imagem com tabelas/SARIF; e build + healthcheck do Compose. Artefatos ficam em cada execução do Actions. Achados Bandit altos e Trivy críticos com correção disponível bloqueiam o deploy.

O Blueprint usa `autoDeployTrigger: off` para que um commit sozinho não contorne os checks. Para disparar o Render somente após todos os jobs passarem, copie o **Deploy Hook URL** do serviço Render e crie no GitHub o segredo de Actions `RENDER_DEPLOY_HOOK_URL`. O workflow envia POST ao hook apenas em `main`. Sem esse segredo, o job termina com aviso e não faz deploy. Trate o hook como segredo: não cole a URL em arquivos ou logs.

## Referências dos provedores

- [Render Blueprint YAML](https://render.com/docs/blueprint-spec) e [plano gratuito](https://render.com/docs/free)
- [Render Deploy Hooks](https://render.com/docs/deploy-hooks)
- [Supabase: conexão PostgreSQL e Session pooler](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Trivy Action](https://github.com/aquasecurity/trivy-action#readme)
