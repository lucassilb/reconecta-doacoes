# ReConecta

Plataforma de doação de alimentos que conecta empresas do setor alimentício a pessoas e outras empresas dispostas a doar.

Projeto acadêmico da disciplina **Computational Thinking with Python**. O CP1 entregou a primeira versão do backend (API REST com CRUDs e regras de doação). O **CP2** evolui o backend e acrescenta aplicação web, dashboard, otimizações, revisão do banco, testes automatizados e uma funcionalidade com LLM local e gratuita.

## Sobre o projeto

O desperdício de alimentos convive com a falta de alimento em outro lugar. O **ReConecta** organiza a ponte entre quem precisa e quem pode doar:

1. Uma **empresa com CNPJ ativo e atividade ligada a alimentação** publica um **pedido de doação** (ex.: "precisamos de 100 caixas de leite e 100 pães até sexta").
2. O pedido aparece em **Doações disponíveis**. Qualquer **pessoa com CPF válido** ou **outra empresa** escolhe um item e doa.
3. Antes de confirmar, quem doa responde um **questionário curto** (4 perguntas de segurança alimentar) e envia uma **foto** do alimento. Se tudo estiver de acordo, a doação é aceita, o progresso do pedido é atualizado e a pessoa recebe o endereço e o prazo de entrega.

## Público-alvo

- **Empresas do setor de alimentos** (restaurantes, padarias, mercados, indústrias, associações com atividade alimentar): publicam pedidos e também podem doar a pedidos de outras empresas.
- **Doadores pessoa física** (CPF): doam alimentos para os pedidos abertos.
- **Instituições receptoras**: entidade mantida do CP1 (CRUD na API).

## Funcionalidades

| Área | O que faz |
|---|---|
| Cadastro de empresa | Valida o CNPJ (dígitos), consulta a Receita Federal em fontes públicas gratuitas (BrasilAPI, com OpenCNPJ e CNPJ.ws como alternativas), exige situação **ATIVA** e atividade econômica (CNAE principal ou secundária) ligada a alimentos. |
| Cadastro de doador | Valida o CPF pelos dígitos verificadores; CPF sempre devolvido mascarado. |
| Login | E-mail, CNPJ ou CPF + senha (hash scrypt). Sessão em cookie HttpOnly/SameSite=Lax; 5 falhas em 15 min bloqueiam novas tentativas. |
| Pedidos de doação | Só empresa publica: itens (nome, categoria, quantidade, unidade) e prazo "receber até". Remover só pedido próprio, disponível e sem reservas. |
| Doar para um pedido | Pessoa (CPF) ou outra empresa; questionário de 4 perguntas + foto obrigatória (JPEG/PNG/WebP até 5 MB, conferida pelos bytes). A empresa não doa no próprio pedido. |
| Progresso | Cada item mostra recebido × meta e quanto falta. |
| Painéis | Empresa: publicar pedido (com "Preencher com IA"), meus pedidos com progresso e doações recebidas com foto, minhas doações. Doador: minhas doações. |
| Dashboard | Indicadores, gráfico pedido × recebido por categoria, doações por dia (30 dias), empresas com mais doações, alertas e últimas doações, com dados reais do banco. Botão "Gerar resumo com IA". |
| LLM local | `qwen2.5:3b` via Ollama (gratuito, roda no próprio PC): interpreta o texto do pedido e resume o dashboard. Detalhes em [docs/llm.md](docs/llm.md). |
| CRUDs do CP1 | Estabelecimentos, Instituições e Doações (`/reconecta/...`), agora com validação e erros em JSON. |

## Regras de negócio

| Código | Regra |
|---|---|
| RN01 | Empresa só se cadastra com CNPJ válido, situação ATIVA e CNAE ligado a alimentação. |
| RN02 | Só empresa publica pedido de doação; pessoa com CPF só doa. |
| RN03 | Todo item de pedido tem quantidade maior que zero; categoria e unidade vêm de listas fixas. |
| RN04 | Só recebe doações o pedido DISPONÍVEL e dentro do prazo "receber até". |
| RN05 | Doação só é aceita com as 4 respostas "sim" (dentro da validade, embalagem íntegra, armazenamento correto, não é comida caseira), validade não vencida e foto válida. Caso contrário nada é registrado e o motivo é exibido. |
| RN06 | A empresa dona não doa no próprio pedido. |
| RN07 | A foto da doação só é visível para quem doou e para a empresa dona do pedido. |
| RN08 | Dados pessoais (CPF, e-mail, telefone, endereço completo) não aparecem em telas ou respostas públicas. |
| RN09 | E-mail, CNPJ e CPF são únicos. |

## Arquitetura

```text
ReConecta/
├── app.py                 # Flask + flask-restx: configuração, rotas das páginas, erros JSON, registro dos namespaces
├── models.py              # Modelos SQLAlchemy (entidades, CHECKs, índices)
├── migracoes.py           # Migrações idempotentes aplicadas no boot (SQLite e PostgreSQL)
├── schema.sql             # Esquema para instalação manual no PostgreSQL
├── Cadastro.py            # /reconecta/cadastro  (CNPJ, empresa, doador)
├── cnpj_service.py        # Consulta e cache de CNPJ nas fontes públicas
├── cnae_alimentos.py      # Critério "atividade ligada a alimentos" por CNAE
├── Auth.py                # /reconecta/auth      (login, logout, me)
├── Publico.py             # /reconecta/publico   (resumo, opções, pedidos, detalhe)
├── Contribuicoes.py       # doação para um pedido (questionário + foto)
├── Painel.py              # /reconecta/painel    (pedidos da empresa, minhas doações)
├── Dashboard.py           # /reconecta/dashboard (agregados)
├── IA.py, llm_service.py  # /reconecta/ia        (LLM local via Ollama + regras automáticas se ele estiver fora)
├── Estabelecimentos.py, Instituicoes.py, Doacoes.py, crud_validacao.py  # CRUDs do CP1
├── static/                # Front-end: HTML, CSS e JS (sem build)
├── tests/                 # pytest
└── docs/                  # modelagem, otimizações, LLM, critério CNAE
```

Front-end: páginas HTML/CSS/JS puras que consomem a API com `fetch` (sessão por cookie). Gráficos com Chart.js (MIT, CDN gratuita). Páginas: `/` (Home), `/sobre`, `/cadastro`, `/entrar`, `/painel`, `/doacoes/<id>` (pedido e doação), `/dashboard`.

## Tecnologias

Python 3.10+ (testado em 3.14), Flask, Flask-RESTX (Swagger), Flask-SQLAlchemy/SQLAlchemy 2, PostgreSQL (ou SQLite para desenvolvimento), psycopg 3, python-dotenv, requests, pytest, Ollama + `qwen2.5:3b` (opcional, gratuito e local), Chart.js.

## Instalação

### Pré-requisitos

- Python 3.10 ou superior e Git;
- PostgreSQL (opcional: sem `DATABASE_URL` a aplicação usa SQLite em `instance/reconecta.db`);
- Ollama (opcional, gratuito) para a LLM local — sem ele as funções de IA usam regras automáticas.

### Passos

```bash
git clone <URL_DO_REPOSITORIO>
cd ReConecta
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux ou macOS
source .venv/bin/activate
pip install -r requirements.txt
```

LLM local (opcional, gratuito): instale o Ollama (https://ollama.com/download) e baixe o modelo:

```bash
ollama pull qwen2.5:3b
ollama serve
```

## Variáveis de ambiente

Crie um `.env` a partir do `.env.example` (não publique o `.env`):

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `DATABASE_URL` | não | SQLite `instance/reconecta.db` | Ex.: `postgresql://USUARIO:SENHA@localhost:5432/reconecta` |
| `SECRET_KEY` | não | gerada e guardada em `instance/secret_key` | Assina o cookie de sessão; defina em produção. |
| `FLASK_DEBUG` | não | `0` | `1` liga o modo debug. |
| `OLLAMA_URL` | não | `http://localhost:11434` | Endereço do Ollama local. |
| `OLLAMA_MODELO` | não | `qwen2.5:3b` | Modelo gratuito usado pela IA. |

## Execução

```bash
python app.py
```

A aplicação sobe em `http://localhost:5000`. Ao iniciar, cria as tabelas que faltarem e aplica as migrações (colunas, índices) de forma idempotente. Swagger em `http://localhost:5000/swagger`.

## Testes

```bash
python -m pytest -q
```

154 testes (unitários, de endpoints, de regras de negócio, de migração e da LLM com respostas simuladas). Os testes usam SQLite em memória e não acessam a internet nem o Ollama.

## Endpoints

Todos os erros sob `/reconecta/` respondem JSON `{"codigo", "mensagem"}` (+ `campos` em erros de validação).

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/reconecta/cadastro/cnpj/{cnpj}` | Consulta CNPJ: situação, atividades alimentares, `apto` e `motivos`. |
| POST | `/reconecta/cadastro/empresa` | Cadastra empresa (refaz a verificação do CNPJ) e inicia a sessão. |
| POST | `/reconecta/cadastro/doador` | Cadastra pessoa física e inicia a sessão. |
| POST | `/reconecta/auth/login` | Login por e-mail, CNPJ ou CPF + senha. |
| POST | `/reconecta/auth/logout` | Encerra a sessão. |
| GET | `/reconecta/auth/me` | Perfil da sessão. |
| GET | `/reconecta/publico/resumo` | Contadores públicos. |
| GET | `/reconecta/publico/opcoes` | Categorias e unidades aceitas. |
| GET | `/reconecta/publico/doacoes` | Pedidos abertos. Paginação `pagina`/`por_pagina` (máx. 50), filtros `categoria`, `uf`, `busca`; cabeçalhos `X-Total-Count`, `X-Pagina`, `X-Por-Pagina`. |
| GET | `/reconecta/publico/doacoes/{id}` | Detalhe do pedido com progresso por item. |
| POST | `/reconecta/publico/doacoes/{id}/contribuicoes` | Doar (multipart: item, quantidade, validade, 4 respostas, foto). |
| GET | `/reconecta/contribuicoes/{id}/foto` | Foto da doação (só quem doou ou a empresa dona). |
| GET/POST | `/reconecta/painel/doacoes` | Pedidos da empresa logada / publicar pedido. |
| DELETE | `/reconecta/painel/doacoes/{id}` | Remover pedido próprio. |
| GET | `/reconecta/painel/minhas-doacoes` | Doações feitas pela pessoa ou empresa logada. |
| GET | `/reconecta/dashboard` | Indicadores, séries, ranking, alertas e últimas doações (agregados). |
| POST | `/reconecta/ia/interpretar-pedido` | Empresa logada: texto livre → itens sugeridos para revisão. |
| POST | `/reconecta/ia/resumo-dashboard` | Resumo e recomendações a partir dos agregados (10/min por IP). |
| GET/POST | `/reconecta/estabelecimentos/` | CRUD do CP1. |
| GET/PUT/DELETE | `/reconecta/estabelecimentos/{id}` | CRUD do CP1. |
| GET/POST | `/reconecta/instituicoes/` | CRUD do CP1. |
| GET/PUT/DELETE | `/reconecta/instituicoes/{id}` | CRUD do CP1. |
| GET/POST | `/reconecta/doacoes/` | CRUD do CP1. |
| GET/PUT/DELETE | `/reconecta/doacoes/{id}` | CRUD do CP1. |

O arquivo [swagger.json](swagger.json) é a exportação da especificação OpenAPI atual; a versão interativa fica em `/swagger`.

## Banco de dados

Entidades: `estabelecimentos`, `doadores`, `instituicoes`, `doacoes` (pedido), `itens_doacao` (itens pedidos), `contribuicoes` (doações recebidas, com respostas do questionário e foto) e `reservas` (modelo do CP1, sem endpoints nesta versão). Diagrama ER, chaves, CHECKs, índices e as decisões de normalização estão em [docs/modelagem.md](docs/modelagem.md).

## Documentação complementar

- [docs/modelagem.md](docs/modelagem.md) — modelagem, normalização e índices;
- [docs/otimizacoes.md](docs/otimizacoes.md) — otimizações da API com medições;
- [docs/llm.md](docs/llm.md) — LLM: modelo, finalidade, dados enviados, uso, limitações e segurança;
- [docs/cnae-alimentos.md](docs/cnae-alimentos.md) — critério de atividade alimentar.

## Limitações conhecidas

- Reserva e retirada por instituições (modelo `reservas` do CP1) ainda não têm fluxo na aplicação.
- Recuperação de senha não implementada.
- A consulta de CNPJ depende de serviços públicos externos (com cache de 10 minutos e fontes alternativas).
- A LLM é pequena e roda localmente: as sugestões passam por validação e revisão humana; sem Ollama, as funções usam regras automáticas e indicam `fonte: "regras"`.

## Documentação Swagger

Interativa em `/swagger` (local) e no deploy do CP1: **[Swagger/OpenAPI do ReConecta](https://reconecta.onrender.com/swagger)**.

## Organização no Trello

[Quadro ReConecta no Trello](https://trello.com/invite/b/6a96cdf34f25b339652662c3/ATTI4b7785042036ae55024963ac1546279b355F294D/reconecta)

## Integrantes

| Integrante | RM |
|---|---|
| Aline Delphino Chiaramonte | RM569860 |
| Brian Barreto Brasil | RM570384 |
| Enzo Gabriel Lima Miranda | RM573094 |
| Victor Deggerone Gomes | RM569518 |

## Status

Entrega do CP2 — 2026.
