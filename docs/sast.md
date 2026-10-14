# Relatórios SAST — ReConecta

- **1ª passada:** 2026-10-13, base `e652512` — Bandit 5 MEDIUM; Trivy fs 4 MEDIUM.
- **2ª passada:** 2026-10-13, base `main` `3a7939e` (Frentes A e C integradas) — resultado
  na seção "Estado anterior".
- **3ª passada:** 2026-10-13, base `main` local `520d5b1` (rodada 11 integrada) — resultado
  na seção "Estado atual". Trivy `image` **não foi refeito localmente** (daemon Docker
  indisponível na máquina); ele roda no job `sast-trivy` do GitHub Actions
  (`ci.yml:84-99`) e os artefatos `trivy-image.*` em `relatorios/sast/` seguem referindo-se
  à 2ª passada (`3a7939e`).

## Ferramentas e comandos

| Ferramenta | Versão | Comando |
|---|---|---|
| Bandit | 1.9.4 (venv do projeto, Python 3.14) | `bandit -r . -x ./tests,./scripts,./.venv,./venv,./instance,./relatorios,./__pycache__ -f json\|txt\|html -o relatorios/sast/bandit.*` |
| Trivy fs | 0.75.0 (binário fora do repositório) | `trivy fs --scanners vuln,secret,misconfig --skip-dirs .git,__pycache__,instance,relatorios,tests/fixtures,.venv,venv --format table\|json .` |
| Trivy config | 0.75.0 | `trivy config .` (Dockerfile e demais IaC detectados) |
| Trivy image | 0.75.0 | `docker build -t reconecta:sast .` → `trivy image --scanners vuln,secret,misconfig reconecta:sast` |

Para refazer tudo: `python scripts/sast.py` na raiz (`--so-bandit`, `--sem-imagem`;
`TRIVY=<caminho-do-exe>` se o Trivy não estiver no PATH; `trivy image` precisa do Docker
ligado e constrói `reconecta:sast` se a imagem não existir).

Artefatos versionados em `relatorios/sast/`: `bandit.{json,txt,html}`, `trivy-fs.{txt,json}`,
`trivy-config.{txt,json}`, `trivy-image.{txt,json}`.

As exclusões cobrem testes, relatórios, `instance/` e ambientes virtuais (`.venv`/`venv`),
para o scan local dar o mesmo resultado do job `sast-*` do CI em qualquer máquina.

**Limitação do Trivy 0.75:** os scanners de `config`/`misconfig` só cobrem Dockerfile,
Kubernetes, Helm, Terraform, CloudFormation e Ansible — `docker-compose.yml`,
`render.yaml` e `.github/workflows/ci.yml` não são analisados por essa versão (a revisão
deles está na matriz `docs/stride.md`, linhas T6/T7/D7/I9). O `trivy config` detecta só o
`Dockerfile` neste repositório: 0 misconfigurações.

## Estado atual (`520d5b1`, rodada 11)

Rodado localmente com `python scripts/sast.py --sem-imagem` (Bandit 1.9.4 no venv,
Python 3.14; Trivy 0.75.0 com DB de 2026-10-13, binário fora do repositório).

| Origem | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---|---|---|---|---|
| Bandit (código, excl. tests/scripts/venv/instance) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — vulns (`requirements.txt`, Dockerfile) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — segredos | — | — | **0** | — | — |
| Trivy `config` — IaC (Dockerfile) | — | — | **0** | — | — |
| Trivy `image` — não refeito nesta passada | — | — | — | — | — |

Bandit: **0 achados** em 4372 linhas varridas (4 testes pulados por `# nosec`, os mesmos
B608 justificados de `migracoes.py`). Os módulos novos da rodada (`Excedentes.py`,
`eventos.py`, `TempoReal.py`, `conexao.py`, mudanças em `Cadastro.py`, `Painel.py`,
`IA.py`, `models.py`, `migracoes.py`) saíram limpos: as transições de estado usam
`update().where(...)` parametrizado pelo ORM e não há SQL novo fora de `migracoes.py`.

Trivy `fs`/`config`: **0 vulnerabilidades, 0 segredos, 0 misconfigurações** — incluída a
linha nova do `CMD` do gunicorn (`--worker-class gthread --threads 8`, `Dockerfile:21`).

## Estado anterior (`3a7939e`)

| Origem | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---|---|---|---|---|
| Bandit (código, excl. tests/scripts/venv/instance) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — vulns (`requirements.txt`, Dockerfile) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — segredos | — | — | **0** | — | — |
| Trivy `config` — IaC (Dockerfile) | — | — | **0** | — | — |
| Trivy `image` — `reconecta:sast` (Debian 13.7 + Python) | 0 | **44** | 58 | 61 | 3 |

**Imagem: os 44 HIGH são todos CVEs de pacotes Debian da imagem base `python:3.12-slim`
sem correção disponível** (`util-linux`, `ncurses`, `pam`, `glibc`, `apt` etc. — status
"affected"/vazio em `FixedVersion`). Das 166 vulnerabilidades, só **2 têm correção** e
ambas são `UNKNOWN`. Nenhum pacote Python da imagem tem CVE. O gate do CI
(`severity: CRITICAL` + `ignore-unfixed`) passa. Ação recomendada: rebuild periódico da
imagem (a base slim é atualizada) e, se quiser reduzir a superfície, avaliar
`python:3.12-slim` reconstruída ou imagem distroless — fora do escopo da rodada.

## Antes → depois

### Bandit (5 MEDIUM → 0)

| Achado na 1ª passada | Destino em `3a7939e` |
|---|---|
| B104 `app.py:133` — bind `0.0.0.0` | **Corrigido**: `FLASK_RUN_HOST` com padrão `127.0.0.1` e `PORT` por ambiente (`app.py:194-196`); gunicorn faz o bind em produção (`Dockerfile:21`) |
| B608 ×4 `migracoes.py` — SQL com f-string | **Justificados**: falso positivo confirmado (identificadores são literais internos); a Frente A marcou `# nosec B608` com comentário (`migracoes.py:88,127,174,221`). Bandit reporta "4 skipped due to nosec" |

### Trivy fs (4 MEDIUM → 0)

| Pacote (1ª passada) | CVE | Destino |
|---|---|---|
| Werkzeug 3.1.8 | CVE-2026-102598 (DoS `safe_join`, device paths Windows) | `Werkzeug==3.1.9` (corrigido) |
| requests 2.32.5 | CVE-2026-25645 (temp file previsível) | `requests==2.33.0` |
| python-dotenv 1.1.1 | CVE-2026-28684 (sobrescrita via symlink) | `python-dotenv==1.2.2` |
| pytest 8.4.2 | CVE-2025-71176 (tmp dir inseguro) | movido para `requirements-dev.txt` como `pytest==9.0.3` — fora da imagem de produção |

**Supply chain:** `psycopg[binary]`, `SQLAlchemy` e `tzdata` agora pinados
(`==3.3.6`, `==2.1.2`, `==2026.4`). Não há mais faixas abertas. Pendente (documentado na
matriz, T6): actions por tag e não por SHA; sem lockfile com hash.

## Triagem — o que resta

1. **Trivy image — 44 HIGH / 58 MEDIUM sem correção.** Verdadeiros, mas não acionáveis
   hoje: são CVEs de pacotes Debian da base, sem `FixedVersion`. O aplicativo roda como
   usuário não-root (`Dockerfile:11,15`), não instala pacotes de sistema extras e remove
   `pip` da imagem (`:10`), o que reduz a superfície real. Risco aceito para o MVP;
   reavaliar quando a base publicar updates.
2. **Sem segredos, sem misconfig detectada, sem CVE em dependência Python.**
3. Itens que o SAST não cobre (fora do escopo da ferramenta) estão no STRIDE: prova de
   posse no cadastro, limite global por IP, token admin estático, auditoria só em stdout —
   e, novos na rodada 11 (`docs/stride.md`, seção 8): cada conexão SSE segura um gthread
   por até 5 min (D8), a regra "evento sem dado pessoal" é convenção e não enforcement
   (I11), contas legadas ficam `atividade_alimentar=True` até `atualizar_perfis.py` rodar
   (E8) e a `observacao` do excedente é texto livre público (I12).

**Nenhum achado CRITICAL nem HIGH acionável. Nenhuma correção pendente nesta frente.**
