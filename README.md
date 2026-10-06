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
| Meus dados | No painel, "Editar" altera os próprios dados (empresa: e-mail e telefone; doador: nome, e-mail e telefone) e troca a senha informando a atual. CNPJ e CPF não mudam. |
| Dashboard | Indicadores, gráfico pedido × recebido por categoria, doações por dia (30 dias), empresas com mais doações, alertas e últimas doações, com dados reais do banco. Botão "Gerar resumo com IA". |
| LLM local | `qwen2.5:3b` via Ollama (gratuito, roda no próprio PC): interpreta o texto do pedido e resume o dashboard. Detalhes em [docs/llm.md](docs/llm.md). |
| CRUDs do CP1 | Estabelecimentos, Instituições e Doações (`/reconecta/...`): leitura pública sem contatos; escrita só com token de administrador, CNPJ verificado e erros em JSON. |

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
| RN08 | CPF, e-mail, telefone e endereços privados não aparecem em telas ou respostas públicas; o endereço cadastrado de estabelecimentos e instituições permanece público nos CRUDs do CP1. |
| RN09 | E-mail, CNPJ e CPF são únicos. |
| RN10 | POST/PUT/DELETE dos CRUDs do CP1 exigem `X-Admin-Token` válido; sem `ADMIN_TOKEN` configurado, a escrita fica desativada. |

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
├── Estabelecimentos.py, Instituicoes.py, Doacoes.py  # CRUDs do CP1
├── crud_validacao.py, crud_admin.py  # validação dos CRUDs do CP1 e token de administrador (X-Admin-Token)
├── static/                # Front-end: HTML, CSS e JS (sem build)
├── tests/                 # pytest
└── docs/                  # modelagem, otimizações, LLM, critério CNAE
```

Front-end: páginas HTML/CSS/JS puras que consomem a API com `fetch` (sessão por cookie). Gráficos com Chart.js (MIT, CDN gratuita). Páginas: `/` (Home), `/sobre`, `/cadastro`, `/entrar`, `/painel`, `/doacoes/<id>` (pedido e doação), `/dashboard`.

## Frontend (critério 2 do CP2)

Cada item do critério e onde ele está no código. As páginas ficam em `static/` (HTML, CSS e JS sem build). Cabeçalho e rodapé vêm de `static/js/layout.js`. Os endpoints abaixo omitem o prefixo `/reconecta`.

| Item do critério | Onde está (página → arquivo JS) | Endpoints consumidos |
|---|---|---|
| Consumir a API | Todas as páginas usam `fetch` com a sessão por cookie: `/` → `home.js`, `/cadastro` → `cadastro.js`, `/entrar` → `entrar.js`, `/painel` → `painel.js`, `/doacoes/<id>` → `doacao.js`, `/dashboard` → `dashboard.js`, todas → `layout.js` | `/publico/*`, `/cadastro/*`, `/auth/*`, `/painel/*`, `/dashboard`, `/ia/*` |
| Interação com as funcionalidades principais | Cadastro de empresa (consulta do CNPJ) e de doador (`cadastro.js`). Login e logout (`entrar.js`, `layout.js`). Publicar pedido, "Preencher com IA" e remover pedido (`painel.js`). Doar com questionário e foto (`doacao.js`). "Gerar resumo com IA" (`dashboard.js`). Editar "Seus dados" e trocar a senha (`painel.js`) | `GET /cadastro/cnpj/{cnpj}`, `POST /cadastro/empresa`, `POST /cadastro/doador`, `POST /auth/login`, `POST /auth/logout`, `POST /painel/doacoes`, `DELETE /painel/doacoes/{id}`, `POST /ia/interpretar-pedido`, `POST /publico/doacoes/{id}/contribuicoes`, `POST /ia/resumo-dashboard`, `PUT /auth/me` |
| Navegação coerente | Cabeçalho e rodapé iguais em todas as páginas, com Início, Sobre, Doações, Como funciona e Dashboard. Com sessão, o cabeçalho mostra "Olá, …", Painel e Sair; sem sessão, mostra Entrar e Cadastrar (`layout.js`). Páginas que exigem login mandam para `/entrar?proximo=…` e voltam ao destino depois do login (`painel.js`, `doacao.js`, `entrar.js`) | `GET /auth/me` |
| Apresentar dados obtidos do backend | Home: contadores e pedidos abertos com progresso (`home.js`). Detalhe do pedido com progresso por item (`doacao.js`). Painel: seus dados, meus pedidos com doações recebidas e fotos, minhas doações, resumo da rede (`painel.js`). Dashboard: indicadores, gráficos com tabela equivalente, alertas, ranking e últimas doações (`dashboard.js`) | `GET /publico/resumo`, `GET /publico/opcoes`, `GET /publico/doacoes`, `GET /publico/doacoes/{id}`, `GET /painel/doacoes`, `GET /painel/minhas-doacoes`, `GET /contribuicoes/{id}/foto`, `GET /dashboard`, `GET /auth/me` |
| Cadastro ou alteração de informações | Cadastro de conta em `/cadastro` (`cadastro.js`), publicação de pedido em `/painel` (`painel.js`) e doação em `/doacoes/<id>` (`doacao.js`). **Alteração**: em `/painel`, o botão "Editar" de "Seus dados" abre um formulário. A empresa altera e-mail e telefone (nome, CNPJ e endereço vêm da Receita). O doador altera nome, e-mail e telefone (o CPF fica fixo). Os dois podem trocar a senha informando a senha atual (`painel.js`, função `iniciarMeusDados`) | `POST /cadastro/empresa`, `POST /cadastro/doador`, `POST /painel/doacoes`, `POST /publico/doacoes/{id}/contribuicoes`, `PUT /auth/me` |
| Tratamento visual de erros | Erros por campo (borda vermelha, `aria-invalid` e mensagem abaixo do campo) no cadastro, login, publicar pedido, questionário e "Seus dados". Os erros do servidor em `campos` vão para o campo certo, como e-mail já cadastrado (409) e senha atual errada. Avisos com `role="alert"`/`aria-live`, com "Tentar novamente" quando falta conexão. Mensagens para CNPJ inapto (motivos da Receita), login bloqueado (429), pedido não encontrado, foto inválida e falha ao carregar o dashboard | respostas `{codigo, mensagem, campos}` dos endpoints acima |
| Feedback das operações realizadas | "Pedido publicado" e "Preenchemos N itens a partir do texto" (`painel.js`). "Doação confirmada", com o endereço de entrega (`doacao.js`). Tela de sucesso do cadastro (`cadastro.js`). "Dados atualizados", com o "Olá, …" do painel e do cabeçalho atualizado sem recarregar (`painel.js`). Lista recarregada depois de remover um pedido. Botões em estado de carregamento durante o envio. Selo da origem do resumo: modelo local ou regras automáticas (`dashboard.js`) | os mesmos endpoints de escrita |

## Dashboard (critério 3 do CP2)

Página `/dashboard` (`static/dashboard.html` + `static/js/dashboard.js`), ligada no cabeçalho e no rodapé de todas as páginas. Os dados vêm de **uma única requisição** `GET /reconecta/dashboard`, montada por `montar_dashboard()` em `Dashboard.py` com consultas agregadas (`COUNT`/`SUM` com `GROUP BY`) direto do banco da aplicação — nada é fixo no HTML. O botão "Atualizar dados" refaz a consulta; "Dados de …" mostra quando os números foram gerados, em horário de Brasília.

| Item do critério | Onde aparece na página | Campo do `GET /reconecta/dashboard` |
|---|---|---|
| Indicadores | Cartões: pedidos abertos, pedidos encerrados, doações recebidas, empresas, doadores (CPF) e instituições | `indicadores.pedidos_abertos`, `pedidos_encerrados`, `doacoes_recebidas`, `empresas`, `doadores`, `instituicoes` |
| Métricas | "Atendimento dos pedidos abertos" em % com barra de progresso e "X de Y itens pedidos com a meta completa" | `indicadores.percentual_atendimento` (Σ min(recebido, meta) ÷ Σ meta × 100), `itens_pedidos`, `itens_atendidos` |
| Gráficos | Barras "Pedido × recebido por categoria" e linha "Doações por dia" (Chart.js) | `por_categoria[]`, `por_dia[]` |
| Tabelas | "Empresas com mais doações recebidas", "Últimas doações" e "Ver dados em tabela" embaixo de cada gráfico | `top_empresas[]`, `ultimas_doacoes[]`, `por_categoria[]`, `por_dia[]` |
| Históricos | Série dos últimos 30 dias (dias sem doação aparecem com 0) e as 10 últimas doações com data e hora | `por_dia[]` (30 dias, fuso de Brasília), `ultimas_doacoes[]` |
| Alertas | Lista "Alertas" com link "Ver pedido": prazo terminando em até 3 dias, pedido aberto há 3 dias ou mais sem doação, item com 80% ou mais da meta, meta atingida | `alertas[]` com `tipo` = `PRAZO_PROXIMO`, `SEM_DOACOES`, `QUASE_COMPLETO`, `META_ATINGIDA` |
| Dados consolidados | Totais por categoria, por dia e por empresa; resumo e recomendações gerados pela LLM local a partir desses agregados ("Gerar resumo com IA") | `por_categoria`, `por_dia`, `top_empresas`, `indicadores`; `POST /reconecta/ia/resumo-dashboard` |

Privacidade: o dashboard é público e só traz dados agregados. "Últimas doações" mostra o item, a quantidade, a empresa que recebeu e se quem doou foi pessoa ou empresa, sem nome, CPF ou contato de pessoas. Testes em `tests/test_dashboard.py`, `tests/test_fuso.py` e `tests/test_cp2_api.py` (agregação, limite da meta, ausência de dados pessoais, fuso e número de consultas).

## Otimização da API (critério 4 do CP2)

Detalhes, medições e como repetir em [docs/otimizacoes.md](docs/otimizacoes.md).

| Item do critério | O que foi feito | Onde |
|---|---|---|
| Redução de requisições desnecessárias | Dashboard inteiro em **1** requisição; sessão consultada **1** vez por página (antes `/painel` e `/entrar` faziam 2 `GET /auth/me`); cache de 10 min das consultas de CNPJ (a verificação ao digitar e a do envio usam o mesmo resultado); "Seus dados" não envia nada se nada mudou; Home busca só a 1ª página de pedidos | `Dashboard.py`, `static/js/layout.js`, `painel.js`, `entrar.js`, `cnpj_service.py` |
| Paginação | `GET /reconecta/publico/doacoes?pagina=&por_pagina=` (máx. 50) com `X-Total-Count`, `X-Pagina`, `X-Por-Pagina`; `limite` antigo continua aceito | `Publico.py` |
| Filtros | `categoria`, `uf` e `busca` (nome do item ou da empresa) na mesma lista, com `EXISTS` para não duplicar pedidos | `Publico.py` |
| Consultas otimizadas | `selectinload` (carregamento em lote) nas listas e no painel; agregações `COUNT`/`SUM` + `GROUP BY` no dashboard; índices nas chaves estrangeiras, em `doacoes(status, data_limite_retirada)` e `contribuicoes(doacao_id, status)` | `Publico.py`, `Painel.py`, `Dashboard.py`, `models.py`, `migracoes.py`, `schema.sql` |
| Melhor tratamento de erros | Erros JSON padronizados para 404/405/413/500 sob `/reconecta/` (sem stack trace); CRUDs do CP1 deixaram de dar 500 com campo faltando; falhas da Receita e do Ollama viram 503 ou fallback explícito | `app.py`, `crud_validacao.py`, `cnpj_service.py`, `llm_service.py` |
| Validações | Parâmetros de paginação/filtro validados (400 com `campos`); CRUDs do CP1 validados e protegidos por `X-Admin-Token`; cadastro, pedido, doação (questionário + foto pelos bytes) e edição de dados validados no servidor | `Publico.py`, `crud_validacao.py`, `crud_admin.py`, `Cadastro.py`, `Painel.py`, `Contribuicoes.py`, `Auth.py` |
| Organização das respostas | Formato único `{codigo, mensagem, campos/motivos}`; códigos HTTP com significado fixo; paginação em cabeçalhos mantendo a lista; datas com fuso `-03:00`; CPF mascarado; modelos no Swagger | todos os namespaces, `swagger.json` |
| Melhorias de desempenho | Lista de 25 pedidos: **52 → 5** consultas SELECT (~21 ms → ~15 ms); dashboard com **10** consultas fixas, independentemente do volume; limite de 6 MB por requisição | `tests/test_cp2_api.py` (mede as consultas), `app.py` |

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
| `ADMIN_TOKEN` | para escrita dos CRUDs do CP1 | desativado | Token longo e aleatório enviado em `X-Admin-Token`. Sem configuração: escrita 403; token ausente/incorreto: 401. Não use no navegador nem publique no repositório. |
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

188 testes (unitários, de endpoints, de regras de negócio, de migração, de integridade do banco e da LLM com respostas simuladas). Usam SQLite em memória e não acessam a internet nem o Ollama; 3 provas opcionais em PostgreSQL só rodam com `CP2_PG_SUPERUSER_PASSWORD_FILE` definido (sem ela aparecem como "skipped").

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
| PUT | `/reconecta/auth/me` | Edita os próprios dados (empresa: e-mail e telefone; doador: nome, e-mail e telefone) e troca a senha com a senha atual. |
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
| GET público / POST admin | `/reconecta/estabelecimentos/` | Lista pública sem e-mail/telefone; POST verifica CNPJ ativo e CNAE alimentar. |
| GET público / PUT/DELETE admin | `/reconecta/estabelecimentos/{id}` | GET sem contato; admin recebe registro completo. DELETE com dependentes: 409. |
| GET público / POST admin | `/reconecta/instituicoes/` | Lista pública sem e-mail/telefone; POST verifica CNPJ ativo. |
| GET público / PUT/DELETE admin | `/reconecta/instituicoes/{id}` | GET sem contato; admin recebe registro completo. DELETE com reservas: 409. |
| GET público / POST admin | `/reconecta/doacoes/` | CRUD legado do CP1; escrita administrativa. |
| GET público / PUT/DELETE admin | `/reconecta/doacoes/{id}` | DELETE com itens, contribuições ou reservas: 409. |

O arquivo [swagger.json](swagger.json) é a exportação da especificação OpenAPI atual; a versão interativa fica em `/swagger`.

## Banco de dados (critério 5 do CP2)

Entidades: `estabelecimentos`, `doadores`, `instituicoes`, `doacoes` (pedido), `itens_doacao` (itens pedidos), `contribuicoes` (doações recebidas, com respostas do questionário e foto) e `reservas` (modelo do CP1, sem endpoints nesta versão). A revisão completa, com diagrama ER, está em [docs/modelagem.md](docs/modelagem.md), organizada por item do critério:

| Item do critério | Seção em `docs/modelagem.md` | Resumo |
|---|---|---|
| Duplicidade de informações | Duplicidade de informações | Itens em linhas próprias; progresso calculado, não gravado; repetições que ficaram (fotografia do item na contribuição, `doacao_id`) são deliberadas e controladas |
| Relacionamentos | Relacionamentos | Cardinalidades 1:N com chaves estrangeiras `ON DELETE RESTRICT` (nada some em cascata sem querer) |
| Integridade dos dados | Integridade dos dados | PK, FK, UNIQUE (CNPJ, CPF, e-mail), NOT NULL e CHECKs nomeados de status, quantidade e origem — iguais no código (ORM) e no `schema.sql`; FK composta impede vincular um item a outro pedido |
| Organização das entidades | Organização das entidades | O que cada tabela representa e quem escreve nela |
| Índices quando necessários | Índices | 8 índices, cada um ligado à consulta que ele acelera |
| Normalização | Normalização | 1FN, 2FN e 3FN com exemplos e as exceções deliberadas |
| Justificar decisões | Decisões de modelagem | Tabela decisão × alternativa × motivo |

As mudanças são aplicadas por `migracoes.py` no início da aplicação, de forma idempotente, em PostgreSQL (restrições com `NOT VALID` + `VALIDATE`, abortando sem apagar dados se houver registro inválido) e em SQLite. Testes em `tests/test_integridade_banco.py`; a prova em PostgreSQL roda com `CP2_PG_SUPERUSER_PASSWORD_FILE` apontando para um arquivo com a senha do superusuário (cria e apaga um banco temporário).

## Documentação (critério 6 do CP2)

Onde cada item exigido está atualizado:

| Item do critério | Onde está |
|---|---|
| README | Este arquivo, reescrito para o CP2 (fluxo de pedidos e doações, dashboard, LLM, segurança) |
| Swagger | `/swagger` (gerado do código pelo Flask-RESTX) e [swagger.json](swagger.json) exportado da API atual, com todos os endpoints, modelos de entrada/saída, códigos de resposta e o cabeçalho `X-Admin-Token` |
| Instruções de instalação | Seções **Instalação** (Python, venv, `pip install -r requirements.txt`, PostgreSQL ou SQLite, Ollama gratuito), **Execução** e **Testes** |
| Endpoints | Seção **Endpoints**: todas as 35 operações da API (24 caminhos) com método, caminho e descrição, mais as rotas de página em **Arquitetura** |
| Arquitetura | Seção **Arquitetura**: um arquivo por responsabilidade, front-end em `static/`, testes em `tests/`, docs em `docs/` |
| Funcionalidades | Seções **Funcionalidades** e **Regras de negócio** (RN01–RN10), mais as tabelas dos critérios 2, 3 e 4 |
| Variáveis de ambiente | Seção **Variáveis de ambiente** (`DATABASE_URL`, `SECRET_KEY`, `FLASK_DEBUG`, `OLLAMA_URL`, `OLLAMA_MODELO`, `ADMIN_TOKEN`) e o arquivo `.env.example` |

Documentos complementares: [docs/modelagem.md](docs/modelagem.md) (banco), [docs/otimizacoes.md](docs/otimizacoes.md) (otimizações com medições), [docs/llm.md](docs/llm.md) (LLM) e [docs/cnae-alimentos.md](docs/cnae-alimentos.md) (critério de atividade alimentar).

## Testes (critério 7 do CP2)

Comando para demonstrar na apresentação (na pasta do projeto, com o ambiente virtual ativo):

```bash
python -m pytest -v
```

Resultado atual: **185 passed, 3 skipped** (os 3 "skipped" são as provas opcionais em PostgreSQL; com `CP2_PG_SUPERUSER_PASSWORD_FILE` definido, os 188 passam). Os testes usam SQLite em memória e simulam a Receita e o Ollama, então rodam sem internet e sem tocar no banco real.

| Tipo de teste | Arquivos | O que cobrem |
|---|---|---|
| Unitários | `test_cnae_alimentos.py`, partes de `test_ia.py` e `test_cadastro.py` | Critério de atividade alimentar por CNAE, dígitos de CPF/CNPJ, normalização e validação da saída da LLM, fallback por regras |
| De endpoints | `test_cadastro.py`, `test_auth.py`, `test_publico_painel.py`, `test_pedidos.py`, `test_dashboard.py`, `test_ia.py`, `test_crud_seguro.py`, `test_cp2_api.py` | Códigos HTTP, formato das respostas e erros JSON de cada rota (cadastro, login, edição de dados, pedidos, doação com foto, painel, dashboard, IA, CRUDs do CP1, paginação e filtros) |
| De regras de negócio | `test_cadastro.py`, `test_pedidos.py`, `test_crud_seguro.py`, `test_auth.py` | RN01–RN10: CNPJ ativo e alimentar, só empresa publica, questionário e validade, empresa não doa no próprio pedido, foto privada, dados pessoais fora do público, limite de tentativas de login, escrita do CP1 só com token |
| De integração | `test_integridade_banco.py`, `test_migracao_doador.py`, `test_migracao_pedidos.py`, `test_fuso.py`, `test_cp2_api.py` | Aplicação + banco: migrações idempotentes preservando dados, CHECKs e FK composta, fuso de Brasília no dashboard, número de consultas SQL das listas |

## LLM (critério 8 do CP2)

O ReConecta usa uma LLM **gratuita e local** (Ollama + `qwen2.5:3b`, sem API paga) em duas funções ligadas às regras de negócio — não é um chatbot genérico:

1. **"Preencher com IA"** (painel da empresa → "Publicar pedido de doação"): a empresa escreve, por exemplo, "Precisamos de 100 caixas de leite e 100 pães até sexta-feira"; a LLM classifica e estrutura os itens nas **categorias e unidades fixas da plataforma** e sugere o prazo. O formulário é preenchido para a empresa revisar; a publicação continua passando pelas validações do pedido.
2. **"Gerar resumo com IA"** (dashboard): a LLM interpreta os indicadores agregados dos pedidos e doações e devolve um resumo e recomendações para apoiar decisões.

Tudo o que o critério pede para explicar — modelo/serviço, finalidade, dados enviados, resposta obtida, uso da resposta, limitações e segurança/dados sensíveis — está na tabela do início de [docs/llm.md](docs/llm.md), com exemplos reais de entrada e saída. Endpoints: `POST /reconecta/ia/interpretar-pedido` e `POST /reconecta/ia/resumo-dashboard`; código em `llm_service.py` e `IA.py`; testes em `tests/test_ia.py`.

## Documentação complementar

- [docs/modelagem.md](docs/modelagem.md) — modelagem, normalização e índices;
- [docs/otimizacoes.md](docs/otimizacoes.md) — otimizações da API com medições;
- [docs/llm.md](docs/llm.md) — LLM: modelo, finalidade, dados enviados, uso, limitações e segurança;
- [docs/cnae-alimentos.md](docs/cnae-alimentos.md) — critério de atividade alimentar.

## Limitações conhecidas

- O CP1 tinha apenas o modelo `reservas`, sem endpoints de reserva. O fluxo atual é pedido → contribuição; reserva e retirada por instituições ainda não têm fluxo na aplicação.
- Recuperação de senha não implementada.
- A consulta de CNPJ depende de serviços públicos externos (com cache de 10 minutos e fontes alternativas).
- A LLM é pequena e roda localmente: as sugestões passam por validação e revisão humana; sem Ollama, as funções usam regras automáticas e indicam `fonte: "regras"`.

## Documentação Swagger

Interativa em `http://localhost:5000/swagger`, gerada pelo Flask-RESTX a partir do código (sempre igual à API em execução). A especificação exportada está em [swagger.json](swagger.json) e é regenerada a cada mudança de endpoint. O endereço publicado no CP1 (https://reconecta.onrender.com/swagger) mostra a versão do CP1 até ser atualizado.

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
