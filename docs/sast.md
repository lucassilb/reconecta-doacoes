# Relatórios SAST — ReConecta

- **1ª passada:** 2026-10-13, base `e652512` — Bandit 5 MEDIUM; Trivy fs 4 MEDIUM.
- **2ª passada:** 2026-10-13, base `main` `3a7939e` (Frentes A e C integradas) — resultado
  na seção "Estado anterior".
- **3ª passada:** 2026-10-13, base `main` local `520d5b1` (rodada 11 integrada) — resultado
  na seção histórica abaixo. Trivy `image` **não foi refeito localmente** (daemon Docker
  indisponível na máquina); ele roda no job `sast-trivy` do GitHub Actions
  (`ci.yml:84-99`) e os artefatos `trivy-image.*` em `relatorios/sast/` seguem referindo-se
  à 2ª passada (`3a7939e`) naquele momento.
- **4ª passada:** 2026-10-15, branch `frente/r25-docker-github` sobre `b28fc2a` — imagem
  Alpine reconstruída e varrida localmente, com resultado na seção "Imagem atual".

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

## Imagem atual (rodada 25, 15/10/2026)

O `Dockerfile` usa `python:3.12-alpine` por digest e aplica `apk upgrade --no-cache`
antes de instalar as dependências. A varredura da imagem construída neste branch,
com Trivy 0.75.0 e scanners `vuln,secret,misconfig`, substituiu os artefatos
[`trivy-image.json`](../relatorios/sast/trivy-image.json) e
[`trivy-image.txt`](../relatorios/sast/trivy-image.txt). O resultado foi **0 CRITICAL,
0 HIGH, 0 MEDIUM, 0 LOW, 0 UNKNOWN, 0 segredos e 0 misconfigurações**; o gate
HIGH/CRITICAL sem `ignore-unfixed` passou. A imagem tem 43,1 MB segundo
`docker image inspect`, executa Python 3.12.15 e roda como UID 10001. O Compose
com PostgreSQL ficou saudável, e os testes de HTTP, SSE e upload de JPEG passaram.

O snapshot anterior de `python:3.12-slim` (Debian 13.7) tinha **44 ocorrências HIGH
ligadas a 8 CVEs distintos**, além de 58 MEDIUM, 61 LOW e 3 UNKNOWN. A troca de
base removeu os pacotes vulneráveis da imagem de produção; nenhum achado foi
ocultado por `.trivyignore` ou por um filtro de severidade. As contagens do Trivy
são por pacote e dependem da data do banco de vulnerabilidades. Refaça o build
e a varredura após atualizar a base ou o índice de pacotes Alpine.

Os resultados de Bandit, Trivy `fs` e `config` nas seções seguintes são snapshots
históricos separados, com suas próprias datas; esta rodada refez a imagem.

## Estado anterior (`520d5b1`, rodada 11)

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

## Estado histórico (`3a7939e`)

| Origem | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---|---|---|---|---|
| Bandit (código, excl. tests/scripts/venv/instance) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — vulns (`requirements.txt`, Dockerfile) | 0 | 0 | **0** | 0 | 0 |
| Trivy `fs` — segredos | — | — | **0** | — | — |
| Trivy `config` — IaC (Dockerfile) | — | — | **0** | — | — |
| Trivy `image` — `reconecta:sast` (Debian 13.7 + Python) | 0 | **44** | 58 | 61 | 3 |

**Imagem à época: os 44 HIGH eram CVEs de pacotes Debian da base `python:3.12-slim`
sem correção disponível na distribuição** (`util-linux`, `ncurses`, `systemd`, `acl`, `perl` — status
"affected"/vazio em `FixedVersion`). Das 166 vulnerabilidades, só **2 têm correção** e
ambas são `UNKNOWN`. Nenhum pacote Python da imagem tem CVE. O gate do CI
(`severity: CRITICAL` + `ignore-unfixed`) passa. Ação recomendada: rebuild periódico da
imagem era reconstruí-la periodicamente ou trocar a base. A rodada 25 aplicou a
segunda opção com Alpine, conforme o snapshot atual acima.

## Antes → depois

### Bandit (5 MEDIUM → 0)

| Achado na 1ª passada | Destino em `3a7939e` |
|---|---|
| B104 `app.py:133` — bind `0.0.0.0` | **Corrigido**: `FLASK_RUN_HOST` com padrão `127.0.0.1` e `PORT` por ambiente (`app.py:194-196`); gunicorn faz o bind em produção (`Dockerfile:21`) |
| B608 ×4 `migracoes.py` — SQL com f-string | **Justificados**: falso positivo confirmado (identificadores são literais internos); a Frente A marcou `# nosec B608` com comentário (`migracoes.py:88,127,174,221`). Bandit reporta "4 skipped due to nosec" |
| B608 ×2 `migracoes.py:_migrar_consentimento` (rodada 14) | **Justificados**: mesma situação — a f-string carrega só nomes de tabela da tupla fixa (`estabelecimentos`, `doadores`) e nomes de coluna literais; nada entra por entrada do usuário. `# nosec B608` com comentário (`migracoes.py:96,99`) |

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

## Triagem anterior — rodada 11

1. **Na imagem Debian anterior: Trivy image — 44 HIGH / 58 MEDIUM sem correção.**
   Eram achados de pacotes da base, sem `FixedVersion`. O aplicativo rodava como
   usuário não-root (`Dockerfile:11,15`), não instala pacotes de sistema extras e remove
   `pip` da imagem (`:10`), o que reduzia a superfície real. A imagem Alpine atual
   foi varrida de novo e não contém essas ocorrências.
2. **Sem segredos, sem misconfig detectada, sem CVE em dependência Python.**
3. Itens que o SAST não cobre (fora do escopo da ferramenta) estão no STRIDE: prova de
   posse no cadastro, limite global por IP, token admin estático, auditoria só em stdout —
   e, novos na rodada 11 (`docs/stride.md`, seção 8): cada conexão SSE segura um gthread
   por até 5 min (D8), a regra "evento sem dado pessoal" é convenção e não enforcement
   (I11), contas legadas ficam `atividade_alimentar=True` até `atualizar_perfis.py` rodar
   (E8) e a `observacao` do excedente é texto livre público (I12).

**Esta triagem é histórica.** O resultado vigente da imagem está no início deste documento.

## Security Gates (rodadas 14 e 25)

O CI deixou de só gerar relatórios: cada varredura agora tem um portão que
reprova o job (`.github/workflows/ci.yml`), e `scripts/resumo_sast.py`
reproduz a regra sobre o último relatório gerado, publicando
`resumo.json → gates` (gate, regra, resultado `passou`/`falhou`/`sem_dados`,
detalhe) para o dashboard.

| Gate | Job | Regra |
|---|---|---|
| `bandit-high` | `sast-bandit` | `bandit -lll` — falha em qualquer achado de severidade HIGH |
| `trivy-fs` | `sast-trivy` | `fs` scanners `vuln,secret,misconfig`, severity `HIGH,CRITICAL`, `ignore-unfixed` — falha em vuln corrigível, segredo ou misconfig alta |
| `trivy-config` | `sast-trivy` | `config` severity `HIGH,CRITICAL` — falha em misconfiguração alta de IaC (Dockerfile) |
| `trivy-imagem` | `sast-trivy` | `image` severity `HIGH,CRITICAL` — falha em qualquer HIGH/CRITICAL na imagem, mesmo sem correção disponível |
| `ia-limiares` | `ia` | `python scripts/ciclo_ia.py` compara com `modelo/limiares.json` — falha abaixo dos mínimos |

O critério "corrigível" (`ignore-unfixed`) continua apenas no gate de arquivos.
O gate da imagem agora reprova qualquer HIGH/CRITICAL: a base Alpine eliminou as
44 ocorrências HIGH do snapshot Debian. `scripts/resumo_sast.py` reproduz a mesma
regra no resumo usado pelo dashboard, sem suprimir vulnerabilidades sem correção.
