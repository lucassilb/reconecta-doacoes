# Guia de avaliação de Cyber Risk

Para comunicar uma vulnerabilidade, consulte [SECURITY.md](../SECURITY.md).

Este guia permite examinar o código e testar uma **cópia local** do ReConecta. Use dados inventados e credenciais de teste. O relatório de uma execução deve registrar versão do commit, comandos, ambiente, achados e limitações; resultados antigos em `relatorios/` são evidência histórica, não substituem uma nova varredura.

## Escopo, arquitetura e superfícies

O Flask serve páginas, API REST e Swagger em `/swagger`. SQLAlchemy usa SQLite no caminho Python e PostgreSQL no Docker Compose. O navegador usa cookie de sessão para ONG, empresa de alimentos ou doador. Os CRUDs legados do CP1 exigem `X-Admin-Token` para escrita. O dashboard tem dados reais e uma demonstração fictícia em SQLite na memória.

Inclua na análise: rotas públicas de cadastro, login, pedidos, doações e consulta de CNPJ; sessão, autorização por perfil e por objeto; upload e leitura de foto de alimento; eventos SSE (`/reconecta/tempo-real`, `/reconecta/novidades`); entradas e saídas da IA; e CRUDs com `ADMIN_TOKEN`. Consulte [STRIDE](stride.md), [segurança](seguranca.md) e [LGPD](lgpd.md) para fluxos, controles e tratamento de dados.

## Regras de engajamento

- Faça testes ativos **somente** em `127.0.0.1` ou contêineres do projeto local. Use um clone separado, banco novo e contas fictícias. Não reutilize `.env`, volume, banco, chave ou conta do autor.
- **Não ataque** `https://reconecta-iota.onrender.com`, o Supabase ou o Groq do projeto. São serviços de produção em planos com recursos limitados. Qualquer teste no site público exige combinação prévia de escopo, janela, contas, limites e responsáveis.
- A consulta de CNPJ do cadastro usa APIs públicas gratuitas (BrasilAPI e alternativas). `GEO_EXTERNO=0` desliga apenas geolocalização externa, **não** a consulta de CNPJ. Para teste inteiramente sem rede, não invoque essa consulta; use a semente DAST ou os testes de cadastro com resposta simulada.
- Não envie CPF, telefone, foto ou texto de pessoa real. Não rode scanners de rede contra hosts de terceiros. Remova os contêineres e os volumes locais ao terminar.

## Ambiente isolado

Faça `git clone <URL_DO_REPOSITORIO> reconecta-avaliacao` e entre na pasta. Verifique que não há `.env`. Não defina `DATABASE_URL`, `GROQ_API_KEY` nem `GROQ_KEY_FILE`. Um terminal **PowerShell** para o caminho Python:

```powershell
Remove-Item Env:DATABASE_URL,Env:GROQ_API_KEY,Env:GROQ_KEY_FILE -ErrorAction SilentlyContinue
$env:SECRET_KEY = 'somente-teste-local-cyber-risk-2026'
$env:ADMIN_TOKEN = 'somente-teste-admin-cyber-risk-2026'
$env:OLLAMA_URL = ''  # sem LLM local: o resumo usa regras
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe app.py
```

Em Linux/macOS, use `python3 -m venv .venv`, `source .venv/bin/activate`, `unset DATABASE_URL GROQ_API_KEY GROQ_KEY_FILE` e `export SECRET_KEY=somente-teste-local-cyber-risk-2026 ADMIN_TOKEN=somente-teste-admin-cyber-risk-2026 OLLAMA_URL=''`; então execute os comandos `python` acima sem o prefixo Windows. Sem `DATABASE_URL`, o banco é `instance/reconecta.db`, dentro do clone. A chave e o token acima são **fictícios e exclusivos para teste**, nunca para produção. Para não consultar serviços externos de geolocalização, defina também `GEO_EXTERNO=0`.

Confira `/`, `/dashboard`, `/swagger` e `/reconecta/saude` em `http://127.0.0.1:5000`. Em `/dashboard?modo=demonstracao`, clique em **Gerar resumo com IA**; sem Groq e sem Ollama, `POST /reconecta/ia/resumo-dashboard?modo=demonstracao` deve responder `fonte: regras`, `modo: demonstracao` e texto marcado como simulado. A demonstração usa `data/demonstracao.json` e não grava no banco configurado. Se já houver um Ollama local em execução, desligue-o para essa prova ou deixe `OLLAMA_URL=''` como no exemplo; apenas a ausência da chave Groq não força o uso das regras.

Para o caminho Docker, com Docker e Compose instalados, use outro clone sem `.env`. Defina `POSTGRES_PASSWORD`, `SECRET_KEY` e `ADMIN_TOKEN` com valores de teste próprios (os dois últimos exemplos acima servem apenas localmente), depois:

```text
docker compose -p reconecta-avaliacao build app
docker compose -p reconecta-avaliacao up -d --wait
docker compose -p reconecta-avaliacao ps
docker compose -p reconecta-avaliacao down -v
```

O Compose sobe somente `app` e `db`; o perfil `ia` com Ollama é opcional. A porta HTTP é `5000` e o PostgreSQL fica na rede interna. O `down -v` remove **apenas** os recursos do projeto Compose com esse nome. A imagem não contém o `.env`; confira o contexto em `.dockerignore`.

## Contas e dados de teste

O cadastro de doador em `/cadastro` aceita CPF com dígitos verificadores, e o cadastro de ONG/empresa exige CNPJ ativo obtido de fonte pública. A consulta pode falhar por indisponibilidade ou limite da API pública; isso não comprova falha da aplicação. Em teste automatizado, `tests/test_cadastro.py` usa resposta simulada para CNPJ e não depende dessas APIs.

Para testar autorização com os três papéis **sem depender de CNPJ externo**, use `python scripts/avaliar_autorizacao.py`: ele cria contas e objetos em SQLite na memória, confere o Swagger e não toca o banco configurado. Para varredura HTTP autenticada, `python scripts/dast.py` constrói um Compose próprio na porta `127.0.0.1:5005`, executa `scripts/seed_dast.py` e cria `doador@dast.invalid`, `empresa@dast.invalid` e `ong@dast.invalid`, todas com senha de teste `DastSenha123`. A semente recusa execução fora do SQLite efêmero com `RECONECTA_DAST=1`. Os números em testes e nessa semente são **fixtures inventadas**, com dígitos válidos para exercitar validação; não foram vinculados a titulares reais nem verificados em cadastro oficial. Evite reutilizá-los fora da avaliação.

## Comandos de segurança

Execute da raiz do clone, com ambiente virtual ativo e sem credenciais de produção. Ferramentas além de `requirements-dev.txt`: instalar `semgrep`, `pip-audit` e `pre-commit`; obter binários de Trivy e gitleaks e colocá-los no `PATH`. ZAP é baixado pelo Docker somente para o Compose DAST. Guarde as saídas em diretório local privado; não publique payloads, cookies ou tokens.

| Prova | Comando | Saída |
|---|---|---|
| Suíte funcional | `python -m pytest -q` | terminal; testes opcionais podem ser pulados |
| Bandit + Trivy | `python scripts/sast.py` | `relatorios/sast/bandit.*`, `trivy-fs.*`, `trivy-config.*`, `trivy-image.*`; sem Docker use `--sem-imagem`, sem Trivy use `--so-bandit` |
| Semgrep local | `semgrep --config semgrep-local.yml --error .` | terminal; achados `ERROR` reprovam |
| Dependências | `pip-audit -r requirements.txt -r requirements-dev.txt --strict` | terminal |
| Segredos | `gitleaks dir .` e `gitleaks git .` | terminal; inclui arquivos e histórico |
| Hooks | `pre-commit run --all-files` | terminal; instalar hooks e ferramentas antes; `SKIP=gitleaks` só se a instalação local não oferecer o comando antigo do hook |
| BOLA/IDOR | `python scripts/avaliar_autorizacao.py` | `relatorios/seguranca/autorizacao.json`; requer zero falhas |
| IAST | `RECONECTA_IAST=1 RECONECTA_IAST_REPORT_DIR=<pasta-local> python -m pytest -q`; depois `python scripts/resumo_iast.py <pasta-local> --saida relatorios/seguranca/iast.json` | JSON por PID na pasta local e resumo |
| DAST | `python scripts/dast.py` | `relatorios/seguranca/zap.json` e `iast-dast.json`; requer Docker e porta 5005 livre |

No PowerShell, defina `$env:RECONECTA_IAST='1'` e `$env:RECONECTA_IAST_REPORT_DIR='<pasta-local>'` antes dos comandos IAST. O `scripts/dast.py` cria um projeto Compose com nome próprio e o derruba no bloco de limpeza, inclusive em falha. Verifique o relatório e a ausência de contêineres ao final.

## Riscos conhecidos e limites da prova

- Rodada 25: o login passou a verificar um hash fictício quando o identificador não existe (o tempo de resposta deixa de revelar conta cadastrada); sair, trocar a senha ou excluir a conta incrementa a geração da sessão gravada no usuário e invalida os cookies emitidos — sessões criadas antes da mudança, sem geração, seguem até expirar no navegador; a foto da contribuição recebe a mesma remoção de metadados da foto da oferta, inclusive ao servir fotos antigas; a consulta pública de CNPJ ganhou cota de 20 por minuto por IP; o Chart.js do CDN carrega com integridade SRI; e escritas que usam o cookie exigem `Origin`/`Referer` da mesma origem quando o cabeçalho vem presente (clientes sem cabeçalho, como scripts, seguem aceitos; `SameSite=Lax` continua como base).
- [STRIDE](stride.md) registra falta de prova de posse de CPF/CNPJ/e-mail no cadastro, token admin único e estático, auditoria só em stdout, ausência de limite global por IP e cotas em memória por processo. Dois workers dividem esses contadores e reinícios os zeram. SSE depende de convenção de não incluir PII em eventos futuros; a política ainda não é verificada automaticamente para todo emissor.
- O [snapshot SAST atual de 15/10](sast.md) da imagem `python:3.12-alpine` atualizada registrou **0 CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW, 0 UNKNOWN**, além de 0 segredos e 0 misconfigurações detectados. A imagem Debian anterior tinha **44 ocorrências HIGH em 8 CVEs**; os pacotes vulneráveis saíram com a troca de base, sem regra de exclusão. Esse número é pontual: o índice do `apk upgrade`, o banco do Trivy e as dependências podem mudar. Refaça build e scan antes de usar outra versão ou digest; um resultado zero não prova ausência de falhas.
- Alpine usa musl em vez de glibc. O app, `psycopg`, o Compose com PostgreSQL, SSE e upload de foto passaram no teste local; bibliotecas de treino como `scikit-learn` não integram a imagem de produção. Ao atualizar dependências nativas, valide o build e os fluxos reais novamente.
- Na reprodução do clone em Windows (15/10), Bandit encontrou dois avisos **LOW/B311** em `Dashboard.py` pela semente pseudoaleatória da demonstração; ela gera dados fictícios reproduzíveis e não protege segredo. Registre os avisos no relatório, sem tratá-los como prova de aleatoriedade criptográfica.
- [Segurança](seguranca.md) documenta o alerta ZAP 40018 (SQL injection) em rota que interpreta texto: só é rebaixado como falso positivo **condicional** se ocorrer nas rotas específicas e o IAST da mesma varredura estiver limpo. Um novo alerta ou uma prova de SQL com dado da requisição exige investigação.
- As guardas da IA são heurísticas e podem não reconhecer paráfrases ou outros idiomas. NeMo completo roda no CI com `RECONECTA_NEMO=1`; a produção executa as mesmas ações sem carregar a biblioteca, por limite de memória. Nomes, endereços e texto livre dependem de disciplina para não serem adicionados a novos logs.
- A geolocalização e as sugestões usam distância em **linha reta** e podem recorrer à sede do município; não representam percurso viário nem precisam de serviço pago. A API pública de CNPJ e o modelo Ollama são opcionais e podem estar indisponíveis.
- Gitleaks, Semgrep, Bandit, Trivy, ZAP, IAST e os testes cobrem cenários e versões concretos; resultados limpos não provam ausência de vulnerabilidades. Histórico, dependências e imagem devem ser reavaliados.

## Convite do Trello

O [link de convite mantido no README](../README.md#organização-no-trello) contém um token utilizável para ingressar no quadro. Ele permanece porque o professor exige acesso. O quadro deve ficar sem senhas, dados pessoais, URLs de banco, chaves ou detalhes exploráveis. Revise os membros durante a avaliação e revogue o convite ou gere outro link quando ela terminar.
