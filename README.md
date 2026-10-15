# ReConecta

Plataforma de doação de alimentos que conecta empresas de alimentos, ONGs e pessoas dispostas a doar.

Projeto acadêmico da disciplina **Computational Thinking with Python**. O CP1 entregou a primeira versão do backend (API REST com CRUDs e regras de doação). O **CP2** evolui o backend e acrescenta aplicação web, dashboard, otimizações, revisão do banco, testes automatizados e uma funcionalidade com LLM gratuita. Esta entrega acrescenta dataset estruturado, modelo treinado local, matriz de riscos STRIDE, relatórios SAST, Docker e Docker Compose, pipeline de CI/CD e publicação em nuvem com banco gerenciado, tudo com ferramentas e planos gratuitos.

Na rodada 11, o código local acrescenta perfis de ONG, excedentes, confirmação de entrega, eventos em tempo real e sugestões de destino. A URL pública citada neste README pode continuar na versão anterior até a publicação dessa rodada.

## Sobre o projeto

O desperdício de alimentos convive com a falta de alimento em outro lugar. O **ReConecta** organiza a ponte entre quem precisa e quem pode doar:

1. Uma **ONG com CNPJ ativo e natureza jurídica sem fins lucrativos** ou uma **empresa de alimentos** publica um **pedido de doação** (ex.: "precisamos de 100 caixas de leite e 100 pães até sexta").
2. O pedido aparece em **Pedidos das ONGs**, na Home. Qualquer **pessoa com CPF válido** ou **outra empresa** escolhe um item e doa.
3. Antes de confirmar, quem doa responde um **questionário curto** (4 perguntas de segurança alimentar) e envia uma **foto** do alimento. Se tudo estiver de acordo, a doação é aceita, o progresso do pedido é atualizado e a pessoa recebe o endereço e o prazo de entrega.
4. Uma empresa de alimentos também pode publicar o **excedente do dia**; uma ONG reserva, retira e a publicadora confirma a retirada. A organização que abriu um pedido confirma se recebeu cada doação.

## Objetivo da solução: IA + DevSecOps para reduzir desperdício e conectar doadores a ONGs em tempo real

| Parte do objetivo | Implementação verificável |
|---|---|
| ONGs | O cadastro consulta a natureza jurídica do CNPJ e aceita organização sem fins lucrativos mesmo sem CNAE alimentar; um CNPJ pode ter os dois perfis. `GET /reconecta/cadastro/cnpj/{cnpj}`, `Cadastro.py`, `cnpj_service.py`, `tests/test_dominio_r11.py`. |
| Reduzir desperdício | Empresas de alimentos publicam excedentes com validade e prazo; ONGs reservam e a publicadora confirma a retirada. `POST /reconecta/excedentes`, `POST /reconecta/excedentes/{id}/reservar`, `POST /reconecta/excedentes/{id}/confirmar-retirada`, `Excedentes.py`, tela `/painel` (`static/js/painel-excedentes.js`), `tests/test_dominio_r11.py`. O sistema registra retiradas; não mede redução total de desperdício. |
| Conectar com IA | `POST /reconecta/ia/sugerir-destino` interpreta o alimento oferecido e ordena pedidos compatíveis com pontuação e motivos. Usa `conexao.py`, o classificador de `classificador.py` e a LLM via `llm_service.py` quando disponível (Groq Free, depois Ollama local); sem LLM, aplica classificador e regras. `tests/test_tempo_real.py`, `tests/test_ia.py` e `tests/test_groq.py`. |
| Perto de quem precisa | Distância em linha reta (haversine) entre quem oferece e a ONG entra na pontuação da sugestão ("a 3,8 km"); o aviso de excedente vai primeiro para as ONGs compatíveis mais próximas (mesma UF ou até 50 km, no máximo 10), com a distância; `GET /reconecta/excedentes/rota` ordena as retiradas da ONG (vizinho mais próximo + 2-opt) com links do OpenStreetMap. Coordenadas por Nominatim/BrasilAPI em segundo plano, com cache e sede do município do IBGE como reserva, sem chave nem custo. `geo.py`, `Rotas.py`, `conexao.py`, [docs/geo.md](docs/geo.md), `tests/test_geo.py`. |
| Em tempo real | `GET /reconecta/tempo-real` transmite eventos por SSE; `GET /reconecta/novidades` sustenta a consulta periódica se a conexão cair. O sino, os avisos e a atualização do painel e do dashboard estão em `static/js/layout.js`, `static/js/painel.js`, `static/js/painel-excedentes.js` e `static/js/dashboard.js`; testes em `tests/test_tempo_real.py`. |
| Ciclo fechado | No painel, o dono do pedido marca **Recebi** ou **Não recebi** (`POST /reconecta/painel/contribuicoes/{id}/receber` e `/nao-recebida`); o estado distingue oferta aceita de entrega confirmada. `Painel.py`, `static/js/painel.js`, `tests/test_dominio_r11.py`. |
| Indicadores | `GET /reconecta/dashboard` apresenta doações entregues, excedentes disponíveis e retirados, ONGs, empresas de alimentos e tempo médio até a reserva em `/dashboard`; `Dashboard.py`, `static/js/dashboard.js`, `tests/test_dashboard.py`. |
| DevSecOps | Suíte `python -m pytest`, análise Bandit/Trivy em `.github/workflows/ci.yml`, riscos em `docs/stride.md`, imagem em `Dockerfile`, publicação configurada em `render.yaml` e healthcheck `GET /reconecta/saude`. |

## Critérios desta entrega

Tudo usa ferramentas de código aberto e planos gratuitos, sem chave de API paga e sem cartão.

| Critério | Situação | Onde está |
|---|---|---|
| Dataset estruturado | Pronto | [`data/alimentos.csv`](data/alimentos.csv) (925 linhas), [`data/pedidos_avaliacao.jsonl`](data/pedidos_avaliacao.jsonl) (66 pedidos com gabarito) e [`data/README.md`](data/README.md). Seção [Dataset estruturado](#dataset-estruturado). |
| Modelo funcional local | Pronto | Classificador treinado em [`classificador.py`](classificador.py) + [`modelo/classificador_categorias.json`](modelo/classificador_categorias.json), usado em `POST /reconecta/ia/interpretar-pedido`; Groq Free opcional e Ollama local como segundo provedor. Seção [Modelo funcional local](#modelo-funcional-local). |
| Matriz de riscos (STRIDE) | Pronto | [`docs/stride.md`](docs/stride.md), com 40 ameaças nas seis categorias (35 do sistema e 5 próprias da nuvem). Seção [Segurança (STRIDE e SAST)](#segurança-stride-e-sast). |
| Dockerfile + Docker Compose | Pronto | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml) e [`.dockerignore`](.dockerignore). Seção [Docker e Docker Compose](#docker-e-docker-compose). |
| Pipeline CI/CD (GitHub Actions) | Pronto | [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Seção [Pipeline CI/CD](#pipeline-cicd-github-actions). |
| Relatórios SAST (Bandit e Trivy) | Pronto | [`relatorios/sast/`](relatorios/sast/), triagem em [`docs/sast.md`](docs/sast.md), comando `python scripts/sast.py`; os mesmos relatórios saem como artefatos do GitHub Actions. Seção [Segurança (STRIDE e SAST)](#segurança-stride-e-sast). |
| URL pública | Pronto | **https://reconecta-iota.onrender.com** — Render, plano gratuito, pelo [`render.yaml`](render.yaml). Seção [Nuvem: Render e Supabase](#nuvem-render-e-supabase). |
| Banco em nuvem | Pronto | Supabase (PostgreSQL, região São Paulo), plano gratuito, pela variável `DATABASE_URL`. Passo a passo em [docs/implantacao.md](docs/implantacao.md). |
| README completo | Pronto | Este arquivo. |

## Público-alvo

- **Empresas do setor de alimentos** (restaurantes, padarias, mercados, indústrias, associações com atividade alimentar): publicam pedidos ou excedentes e também podem doar a pedidos de outras organizações.
- **ONGs com CNPJ** e natureza jurídica sem fins lucrativos: publicam pedidos, reservam excedentes e confirmam doações recebidas. Podem acumular o perfil de empresa de alimentos.
- **Doadores pessoa física** (CPF): doam alimentos para os pedidos abertos e, quando não há pedido que combine, publicam o que sobrou como excedente, com endereço de retirada que só a ONG que reservar vê, e confirmam a retirada (comida caseira não é aceita).
- **Instituições receptoras**: entidade mantida do CP1 (CRUD na API).

## Funcionalidades

| Área | O que faz |
|---|---|
| Cadastro de organização | Valida o CNPJ (dígitos), consulta fontes públicas gratuitas (BrasilAPI, com OpenCNPJ e CNPJ.ws como alternativas) e exige situação **ATIVA** e natureza jurídica sem fins lucrativos ou CNAE alimentar. Devolve os perfis ONG e/ou empresa de alimentos. |
| Cadastro de doador | Valida o CPF pelos dígitos verificadores; CPF sempre devolvido mascarado. |
| Login | E-mail, CNPJ ou CPF + senha (hash scrypt). Sessão em cookie HttpOnly/SameSite=Lax; 5 falhas em 15 min bloqueiam novas tentativas; o tempo de resposta não difere entre identificador válido e inválido. Sair, trocar a senha ou excluir a conta incrementa a geração da sessão e invalida os cookies emitidos para a conta. |
| Pedidos de doação | Organização com CNPJ publica: itens (nome, categoria, quantidade, unidade) e prazo "receber até". Remover só pedido próprio, disponível e sem reservas. |
| Doar para um pedido | Pessoa (CPF) ou outra organização; questionário de 4 perguntas + foto obrigatória (JPEG/PNG/WebP até 5 MB, conferida pelos bytes). A foto é guardada no banco de dados, para não se perder quando o servidor da nuvem reinicia. A organização não doa no próprio pedido. Limite de 20 envios por hora por usuário. |
| Progresso e entrega | Cada item mostra recebido × meta, quanto falta e quantidade entregue; o dono do pedido confirma **Recebi** ou **Não recebi** em cada doação aceita. |
| Alimentos doados (excedentes) | Empresa de alimentos **ou pessoa física** oferece o que sobrou em 3 etapas curtas (o que é, onde retirar, confirmações), com **foto obrigatória do alimento mostrando a validade** (reduzida no navegador e sem os metadados de GPS); ONG reserva, pode cancelar e quem doou confirma a retirada. O endereço de retirada só aparece para a ONG que reservou. |
| Página inicial | Bloco "Agora na rede" com abas **Pedidos das ONGs**, **Alimentos doados** e **ONGs na rede**, filtro por categoria com fotos reais (créditos em `static/img/categorias/CREDITOS.md`) e botão **Doar** no topo para quem entrou. |
| Painéis | Organização: publicar pedido (com "Preencher com IA"), acompanhar contribuições e confirmar recebimento; empresa de alimentos também publica e acompanha excedentes; ONG acompanha reservas. Doador: minhas doações e estado da entrega. |
| Meus dados | No painel, "Editar" altera os próprios dados (empresa: e-mail e telefone; doador: nome, e-mail e telefone) e troca a senha informando a atual. CNPJ e CPF não mudam. |
| Dashboard | Indicadores de pedidos, doações entregues, excedentes disponíveis e retirados, ONGs, empresas de alimentos e tempo médio até a reserva; gráficos, alertas e últimas doações com dados do banco. Botão "Gerar resumo com IA". **Mapa de calor do Brasil** (contornos oficiais do IBGE, escala logarítmica de refeições potenciais por estado e cidade) e modo **Demonstração** rotulado. |
| LLM | Groq Free (`openai/gpt-oss-20b`) quando configurado; Ollama local (`qwen2.5:3b`) como reserva. Interpretam o texto do pedido e resumem o dashboard. Detalhes em [docs/llm.md](docs/llm.md). |
| Classificador treinado | Modelo próprio, treinado no dataset do projeto, que escolhe a categoria de cada item em "Preencher com IA". Roda dentro da aplicação, inclusive na nuvem, onde o Ollama não está disponível. Detalhes em [docs/dataset-modelo.md](docs/dataset-modelo.md). |
| Segurança | Cabeçalhos de segurança e Content-Security-Policy em todas as respostas; trilha de auditoria em JSON (login, cadastro, edição de dados, pedidos, doações e uso do token de administrador) sem senha, documento, e-mail ou foto; limites de uso nas rotas de IA e de doação. |
| Saúde | `GET /reconecta/saude` confere a conexão com o banco; é usado pelos healthchecks do Docker, do Compose e do Render. |
| CRUDs do CP1 | Estabelecimentos, Instituições e Doações (`/reconecta/...`): leitura pública sem contatos; escrita só com token de administrador, CNPJ verificado e erros em JSON. |

## Regras de negócio

| Código | Regra |
|---|---|
| RN01 | Organização se cadastra com CNPJ válido, situação ATIVA e natureza jurídica sem fins lucrativos ou CNAE ligado a alimentação. |
| RN02 | Só organização com CNPJ publica pedido de doação; pessoa com CPF só doa. |
| RN03 | Todo item de pedido tem quantidade maior que zero; categoria e unidade vêm de listas fixas. |
| RN04 | Só recebe doações o pedido DISPONÍVEL e dentro do prazo "receber até". |
| RN05 | Doação só é aceita com as 4 respostas "sim" (dentro da validade, embalagem íntegra, armazenamento correto, não é comida caseira), validade não vencida e foto válida. Caso contrário nada é registrado e o motivo é exibido. |
| RN06 | A empresa dona não doa no próprio pedido. |
| RN07 | A foto da doação só é visível para quem doou e para a empresa dona do pedido. |
| RN08 | CPF, e-mail, telefone e endereços privados não aparecem em telas ou respostas públicas; o endereço cadastrado de estabelecimentos e instituições permanece público nos CRUDs do CP1. |
| RN09 | E-mail, CNPJ e CPF são únicos. |
| RN10 | POST/PUT/DELETE dos CRUDs do CP1 exigem `X-Admin-Token` válido; sem `ADMIN_TOKEN` configurado, a escrita fica desativada. |
| RN11 | Limites de uso: 5 falhas de login em 15 min bloqueiam novas tentativas; cada empresa interpreta até 10 pedidos por minuto com a IA; cada IP gera até 10 resumos do dashboard por minuto e até 20 consultas de CNPJ por minuto; cada usuário envia até 20 doações por hora. Acima disso a API responde 429. |

## Arquitetura

```text
ReConecta/
├── app.py                 # Flask + flask-restx: configuração, rotas das páginas, /reconecta/saude, cabeçalhos de segurança, erros JSON
├── models.py              # Modelos SQLAlchemy (entidades, CHECKs, índices)
├── migracoes.py           # Migrações idempotentes aplicadas no boot (SQLite e PostgreSQL)
├── schema.sql             # Esquema para instalação manual no PostgreSQL
├── fuso.py                # Datas e horas no fuso de Brasília
├── Cadastro.py            # /reconecta/cadastro  (CNPJ, empresa, doador)
├── cnpj_service.py        # Consulta e cache de CNPJ nas fontes públicas
├── cnae_alimentos.py      # Critério "atividade ligada a alimentos" por CNAE
├── Auth.py                # /reconecta/auth      (login, logout, me) e trilha de auditoria
├── Publico.py             # /reconecta/publico   (resumo, opções, pedidos, detalhe)
├── Contribuicoes.py       # doação para um pedido (questionário + foto guardada no banco)
├── Excedentes.py          # /reconecta/excedentes (publicação, reserva e retirada)
├── Painel.py              # /reconecta/painel    (pedidos, confirmações, minhas doações)
├── Dashboard.py           # /reconecta/dashboard (agregados)
├── IA.py, llm_service.py, conexao.py  # IA local e sugestão de destino
├── TempoReal.py, eventos.py # SSE, notificações e registro de eventos
├── geo.py, Rotas.py       # coordenadas (cache, IBGE, Nominatim/BrasilAPI), distância e rota de coleta
├── classificador.py       # Classificador de categorias (Naive Bayes em Python puro)
├── modelo/                # Modelo treinado em JSON, métricas do treino e da avaliação
├── data/                  # Dataset de alimentos, pedidos de avaliação e gerador
├── scripts/               # treinar_modelo.py, classificar.py, avaliar_modelos.py, sast.py
├── Estabelecimentos.py, Instituicoes.py, Doacoes.py  # CRUDs do CP1
├── crud_validacao.py, crud_admin.py  # validação dos CRUDs do CP1 e token de administrador (X-Admin-Token)
├── static/                # Front-end: HTML, CSS e JS (sem build)
├── tests/                 # pytest
├── docs/                  # modelagem, otimizações, LLM, dataset e modelo, implantação, STRIDE, SAST, critério CNAE
├── relatorios/sast/       # Relatórios do Bandit e do Trivy
├── Dockerfile, .dockerignore, docker-compose.yml  # Imagem da aplicação e ambiente local com PostgreSQL
├── render.yaml            # Blueprint do Render (plano gratuito)
├── .github/workflows/ci.yml  # Pipeline de CI/CD
├── requirements.txt       # Dependências de produção
└── requirements-dev.txt   # Dependências de desenvolvimento (pytest, bandit, playwright)
```

Front-end: páginas HTML/CSS/JS puras que consomem a API com `fetch` (sessão por cookie). Gráficos com Chart.js (MIT, CDN gratuita com verificação de integridade SRI). Páginas integradas: `/` (Home), `/sobre`, `/privacidade`, `/cadastro`, `/entrar`, `/painel`, `/doacoes/<id>` (pedido e doação), `/dashboard`, `/excedentes/<id>` (excedente: reserva, cancelamento e confirmação de retirada, com a situação ao vivo). Todas as páginas carregam `static/js/layout.js`, que abre uma única conexão com `/reconecta/tempo-real`, cai para `/reconecta/novidades` a cada 10 s se o fluxo falhar e repassa cada evento às páginas pelo evento `reconecta:evento`; o sino de notificações e os avisos ao vivo saem daí. Na Home, o botão "Tenho alimento para doar" abre o assistente que chama `POST /reconecta/ia/sugerir-destino` e leva ao pedido sugerido com o questionário preenchido; a faixa "Excedentes de hoje" e o progresso dos pedidos se atualizam sem recarregar.

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
| Feedback das operações realizadas | "Pedido publicado" e "Preenchemos N itens a partir do texto" (`painel.js`). "Doação confirmada", com o endereço de entrega (`doacao.js`). Tela de sucesso do cadastro (`cadastro.js`). "Dados atualizados", com o "Olá, …" do painel e do cabeçalho atualizado sem recarregar (`painel.js`). Lista recarregada depois de remover um pedido. Botões em estado de carregamento durante o envio. Selo da origem do resumo: Groq Free, modelo local ou regras automáticas (`dashboard.js`) | os mesmos endpoints de escrita |

## Dashboard (critério 3 do CP2)

Página `/dashboard` (`static/dashboard.html` + `static/js/dashboard.js`), ligada no cabeçalho e no rodapé de todas as páginas. Os indicadores anteriores vêm de `GET /reconecta/dashboard`, montado por `montar_dashboard()` em `Dashboard.py` com consultas agregadas (`COUNT`/`SUM` com `GROUP BY`) direto do banco da aplicação. O impacto e a segurança vêm de `/reconecta/dashboard/impacto` e `/reconecta/dashboard/seguranca`. O botão "Atualizar dados" refaz as consultas de negócio; "Dados de …" mostra o horário de Brasília.

| Item do critério | Onde aparece na página | Campo do `GET /reconecta/dashboard` |
|---|---|---|
| Indicadores | Cartões: pedidos abertos e encerrados, doações recebidas e entregues, excedentes disponíveis e retirados, tempo médio até a reserva, empresas de alimentos, ONGs e doadores | `indicadores.pedidos_abertos`, `pedidos_encerrados`, `doacoes_recebidas`, `doacoes_entregues`, `excedentes_disponiveis`, `excedentes_resgatados`, `tempo_medio_reserva_min`, `empresas_alimentos`, `ongs`, `doadores` |
| Métricas | "Cobertura média por item aberto" em % com barra de progresso e "X de Y itens pedidos com a meta completa" | `indicadores.percentual_atendimento` (média de `min(recebido ÷ meta, 1)` por item com meta positiva × 100), `itens_pedidos`, `itens_atendidos` |
| Gráficos | Barras "Pedido × recebido por categoria" e linha de doações e excedentes retirados por dia (Chart.js) | `por_categoria[]`, `por_dia[]` |
| Tabelas | "Empresas com mais doações recebidas", "Últimas doações" e "Ver dados em tabela" embaixo de cada gráfico | `top_empresas[]`, `ultimas_doacoes[]`, `por_categoria[]`, `por_dia[]` |
| Históricos | Série dos últimos 30 dias (dias sem doação aparecem com 0) e as 10 últimas doações com data e hora | `por_dia[]` (30 dias, fuso de Brasília), `ultimas_doacoes[]` |
| Alertas | Lista "Alertas" com link "Ver pedido": prazo terminando em até 3 dias, pedido aberto há 3 dias ou mais sem doação, item com 80% ou mais da meta, meta atingida | `alertas[]` com `tipo` = `PRAZO_PROXIMO`, `SEM_DOACOES`, `QUASE_COMPLETO`, `META_ATINGIDA` |
| Dados consolidados | Totais por categoria, por dia e por empresa; resumo e recomendações gerados pela LLM disponível a partir desses agregados ("Gerar resumo com IA") | `por_categoria`, `por_dia`, `top_empresas`, `indicadores`; `POST /reconecta/ia/resumo-dashboard` |

Privacidade: o dashboard é público e só traz dados agregados. "Últimas doações" mostra o item, a quantidade, a empresa que recebeu e se quem doou foi pessoa ou empresa, sem nome, CPF ou contato de pessoas. Testes em `tests/test_dashboard.py`, `tests/test_fuso.py` e `tests/test_cp2_api.py` (agregação, limite da meta, ausência de dados pessoais, fuso e número de consultas).

### Impacto e DevSecOps

O painel mostra **kg em unidades físicas** (kg, g e litros convertidos com a premissa 1 L = 1 kg) separados de **kg estimados** por médias de categoria para unidade, pacote e caixa. Conta somente doações `ENTREGUE` e excedentes `RETIRADO`. As **refeições potenciais por UF e região** usam 0,5 kg por refeição como premissa, não refeições servidas. Exibe ainda o tempo médio pedido → doação aceita e oferta → reserva; a avaliação offline da IA com data, acurácias e limiares; gráficos Chart.js; mapa de calor do Brasil com os contornos do IBGE e manchas por município de quem recebeu (`static/js/mapa-calor.js`, sem tiles externos nem biblioteca); e calor dia × hora das doações aceitas. O impacto atualiza com eventos em tempo real.

O bloco de segurança lê `relatorios/sast/resumo.json` com achados e data de Bandit, Trivy de arquivos/configuração/imagem e estado STRIDE. A imagem versionada ainda tem 44 achados HIGH do Debian base; o painel não os chama de mitigados. Cabeçalhos/CSP e cotas são controles existentes; falhas e bloqueios de login aparecem como **não medidos**, pois só constam no log. Regras, premissas, atualização do relatório e prova estão em [docs/dashboard.md](docs/dashboard.md); testes em `tests/test_dashboard_impacto.py`.

Para a apresentação no site público, a alternância **Dados reais | Demonstração** mantém os dados reais como padrão e identifica a simulação por uma faixa fixa. `?modo=demonstracao` calcula os mesmos indicadores em SQLite **em memória**, sem escrever no banco configurado: a semente versionada em `data/demonstracao.json` cria 25 ONGs, 5 mercados e 8 doadores fictícios, com 320 pedidos/doações e 160 excedentes. A semeadura usa a meia-noite de Brasília e é renovada quando o dia muda. Acurácia da IA e SAST permanecem reais nos dois modos. O resumo em linguagem natural funciona nos dois modos; na Demonstração é rotulado como resumo de dados simulados. Sem Groq ou Ollama, usa regras locais. O snapshot SAST em `data/resumo_sast.json` acompanha a imagem Docker, que exclui `relatorios/`. Testes em `tests/test_dashboard_demo.py`.

**Mapa de calor.** `static/js/mapa-calor.js` desenha o Brasil em SVG com os contornos oficiais do IBGE (`static/geo/brasil.topo.json`, 37 KB, fonte e licença em `static/geo/FONTES.txt`) e pinta o calor em Canvas recortado pelo país: 40% de fundo suave por estado e 60% de pontos quentes nas cidades de quem recebeu. A cor segue o dado real em refeições potenciais, em **escala logarítmica** (azul = baixo, amarelo = médio, vermelho = alto, com os números na legenda). Passar o mouse ou tocar num estado mostra refeições, kg e ONGs; a tabela por estado e por cidade fica logo abaixo. Os dados vêm de `refeicoes.por_municipio` em `GET /reconecta/dashboard/impacto` (só cidade, UF e números). No modo Demonstração, 100 ONGs fictícias ficam nas 100 cidades mais populosas (IBGE, Censo 2022).

## Otimização da API (critério 4 do CP2)

Detalhes, medições e como repetir em [docs/otimizacoes.md](docs/otimizacoes.md).

| Item do critério | O que foi feito | Onde |
|---|---|---|
| Redução de requisições desnecessárias | Indicadores originais do dashboard em **1** requisição; impacto e segurança em 2 endpoints adicionais; sessão consultada **1** vez por página (antes `/painel` e `/entrar` faziam 2 `GET /auth/me`); cache de 10 min das consultas de CNPJ (a verificação ao digitar e a do envio usam o mesmo resultado); "Seus dados" não envia nada se nada mudou; Home busca só a 1ª página de pedidos | `Dashboard.py`, `static/js/layout.js`, `painel.js`, `entrar.js`, `cnpj_service.py` |
| Paginação | `GET /reconecta/publico/doacoes?pagina=&por_pagina=` (máx. 50) com `X-Total-Count`, `X-Pagina`, `X-Por-Pagina`; `limite` antigo continua aceito | `Publico.py` |
| Filtros | `categoria`, `uf` e `busca` (nome do item ou da empresa) na mesma lista, com `EXISTS` para não duplicar pedidos | `Publico.py` |
| Consultas otimizadas | `selectinload` (carregamento em lote) nas listas e no painel; agregações `COUNT`/`SUM` + `GROUP BY` no dashboard; índices nas chaves estrangeiras, em `doacoes(status, data_limite_retirada)` e `contribuicoes(doacao_id, status)` | `Publico.py`, `Painel.py`, `Dashboard.py`, `models.py`, `migracoes.py`, `schema.sql` |
| Melhor tratamento de erros | Erros JSON padronizados para 404/405/413/500 sob `/reconecta/` (sem stack trace); CRUDs do CP1 deixaram de dar 500 com campo faltando; falhas da Receita e do Ollama viram 503 ou fallback explícito | `app.py`, `crud_validacao.py`, `cnpj_service.py`, `llm_service.py` |
| Validações | Parâmetros de paginação/filtro validados (400 com `campos`); CRUDs do CP1 validados e protegidos por `X-Admin-Token`; cadastro, pedido, doação (questionário + foto pelos bytes) e edição de dados validados no servidor | `Publico.py`, `crud_validacao.py`, `crud_admin.py`, `Cadastro.py`, `Painel.py`, `Contribuicoes.py`, `Auth.py` |
| Organização das respostas | Formato único `{codigo, mensagem, campos/motivos}`; códigos HTTP com significado fixo; paginação em cabeçalhos mantendo a lista; datas com fuso `-03:00`; CPF mascarado; modelos no Swagger | todos os namespaces, `swagger.json` |
| Melhorias de desempenho | Lista de 25 pedidos: **52 → 5** consultas SELECT (~21 ms → ~15 ms); dashboard com **10** consultas fixas, independentemente do volume; limite de 6 MB por requisição | `tests/test_cp2_api.py` (mede as consultas), `app.py` |

## Tecnologias

Todas gratuitas.

- **Aplicação**: Python 3.10+ (testado em 3.14 local e 3.12 na imagem Docker), Flask, Flask-RESTX (Swagger), Flask-SQLAlchemy/SQLAlchemy 2, psycopg 3, python-dotenv, requests, gunicorn (servidor de produção), Chart.js.
- **Banco**: PostgreSQL (local, no Compose ou no Supabase) ou SQLite para desenvolvimento.
- **IA**: Groq Free (`openai/gpt-oss-20b`, opcional), Ollama + `qwen2.5:3b` (opcional, local) e o classificador próprio em Python puro, sem dependência extra.
- **Testes e segurança**: pytest, Bandit, Trivy e Playwright (só para a prova opcional de CSP no navegador).
- **Entrega**: Docker, Docker Compose, GitHub Actions, Render (plano gratuito) e Supabase (plano gratuito).

## Instalação

Há dois caminhos: Python direto na máquina ou Docker Compose. Para avaliação de segurança em ambiente isolado, siga também o [guia Cyber Risk](docs/avaliacao-cyber-risk.md).

### Caminho 1: Python local

Pré-requisitos:

- Python 3.10 ou superior e Git;
- PostgreSQL (opcional: sem `DATABASE_URL` a aplicação usa SQLite em `instance/reconecta.db`);
- Chave Groq Free ou Ollama (ambos opcionais) para a LLM. Sem os dois, as funções usam o classificador treinado e regras automáticas.

```text
git clone <URL_DO_REPOSITORIO> reconecta-avaliacao
cd reconecta-avaliacao
python -m venv .venv
# Windows PowerShell (sem ativação)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
# Linux ou macOS (sem ativação)
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install -r requirements-dev.txt
```

LLM local (opcional, gratuito): instale o Ollama (https://ollama.com/download) e baixe o modelo:

```bash
ollama pull qwen2.5:3b
ollama serve
```

### Caminho 2: Docker Compose

Pré-requisito: Docker com Compose (`docker version` e `docker compose version`). Não precisa de Python nem de PostgreSQL instalados. Os comandos estão em [Docker e Docker Compose](#docker-e-docker-compose).

## Variáveis de ambiente

Se precisar configurar variáveis, crie um `.env` a partir do `.env.example` (não publique o `.env`). Sem ele, o caminho Python usa SQLite local; o Compose tem valores padrão apenas para desenvolvimento. Use somente credenciais fictícias na avaliação.

| Variável | Padrão | Uso |
|---|---|---|
| `DATABASE_URL` | SQLite `instance/reconecta.db` | Ex.: `postgresql://USUARIO:SENHA@localhost:5432/reconecta_dev`. Aceita `postgres://` e `postgresql://` (Supabase, Render) e usa o driver psycopg 3. Em host que não é local, a conexão exige SSL (`sslmode=require`). |
| `SECRET_KEY` | gerada e guardada em `instance/secret_key` | Assina o cookie de sessão; defina em produção. No Render é gerada pelo Blueprint. |
| `COOKIE_SEGURO` | desligado | `1` atrás de HTTPS (Render): cookie de sessão só por HTTPS, leitura dos cabeçalhos do proxy e `Strict-Transport-Security`. Deixe ausente em HTTP local. |
| `PORT` | `5000` | Porta do servidor (o Render define a dele). |
| `FLASK_RUN_HOST` | `127.0.0.1` | Endereço do servidor de desenvolvimento (`python app.py`). No Docker quem escuta em `0.0.0.0` é o gunicorn. |
| `FLASK_DEBUG` | `0` | `1` liga o modo debug. |
| `FLASK_APP` | `app.py` | Usada só pelo comando `flask`. |
| `ADMIN_TOKEN` | desativado | Token longo e aleatório enviado em `X-Admin-Token` para a escrita dos CRUDs do CP1. Sem configuração: escrita 403; token ausente ou incorreto: 401. Não use no navegador nem publique no repositório. |
| `GROQ_API_KEY` | ausente | Chave opcional da conta Groq Free, só no ambiente. No Render, preencher no painel (`sync: false`); nunca incluir em Git ou no navegador. |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Modelo strict gratuito; aceita também `openai/gpt-oss-120b` e `qwen/qwen3.8-27b`. Outro valor desliga o Groq. |
| `OLLAMA_URL` | `http://localhost:11434` | Endereço do Ollama. Só HTTP, com porta, em `localhost`, `127.0.0.1` ou `::1`. |
| `OLLAMA_MODELO` | `qwen2.5:3b` | Modelo gratuito usado pela IA; outro valor desliga a chamada à LLM. |
| `GEO_EXTERNO` | `1` | `0` desliga as consultas de geolocalização ao Nominatim e à BrasilAPI; as distâncias usam o cache e a sede do município (`data/municipios.csv`). A consulta pública de CNPJ no cadastro continua independente dessa variável. |
| `OLLAMA_PERMITIR_DOCKER` | desligado | `1` aceita também, e somente, o host `ollama` do Docker Compose em `OLLAMA_URL` (`http://ollama:11434`). O Compose já define. |

Só no Docker Compose (lidas pelo `docker-compose.yml`):

| Variável | Padrão | Uso |
|---|---|---|
| `POSTGRES_PASSWORD` | `dev-only-change-me` | Senha do PostgreSQL de desenvolvimento do Compose. O padrão serve só para máquina de teste. |
| `COMPOSE_OLLAMA_URL` | `http://ollama:11434` | Endereço do Ollama visto pelo contêiner da aplicação. |

Só nos testes opcionais: `CP2_PG_SUPERUSER_PASSWORD_FILE` (provas em PostgreSQL) e `RECON_CSP_URL` (prova de CSP no navegador). Para refazer os relatórios SAST, `TRIVY` pode apontar para o binário do Trivy.

## Execução

Local:

```text
# Windows PowerShell
.\.venv\Scripts\python.exe app.py
# Linux ou macOS
./.venv/bin/python app.py
```

Com Docker Compose:

```bash
docker compose build app
docker compose up -d --wait
```

Nos dois casos a aplicação sobe em `http://localhost:5000`, com o Swagger em `http://localhost:5000/swagger` e a verificação de saúde em `http://localhost:5000/reconecta/saude`. Ao iniciar, cria as tabelas que faltarem e aplica as migrações (colunas, índices) de forma idempotente.

## Testes

```text
# Windows PowerShell
.\.venv\Scripts\python.exe -m pytest -q
# Linux ou macOS
./.venv/bin/python -m pytest -q
```

Os totais variam conforme o ambiente e os testes opcionais. Tipos de teste e condições de execução estão em [Testes (critério 7 do CP2)](#testes-critério-7-do-cp2).

## Endpoints

Todos os erros sob `/reconecta/` respondem JSON `{"codigo", "mensagem"}` (+ `campos` em erros de validação).

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/reconecta/saude` | Saúde da aplicação: 200 `{"status":"ok","banco":"ok"}`; 503 se o banco não responder. |
| GET | `/reconecta/cadastro/cnpj/{cnpj}` | Consulta CNPJ: situação, natureza jurídica, perfis ONG/empresa de alimentos, `apto` e `motivos`. |
| POST | `/reconecta/cadastro/empresa` | Cadastra organização com perfil ONG e/ou empresa de alimentos (refaz a verificação do CNPJ) e inicia a sessão. |
| POST | `/reconecta/cadastro/doador` | Cadastra pessoa física e inicia a sessão. |
| POST | `/reconecta/auth/login` | Login por e-mail, CNPJ ou CPF + senha. |
| POST | `/reconecta/auth/logout` | Encerra a sessão. |
| GET | `/reconecta/auth/me` | Perfil da sessão. |
| PUT | `/reconecta/auth/me` | Edita os próprios dados (empresa: e-mail e telefone; doador: nome, e-mail e telefone) e troca a senha com a senha atual. |
| GET | `/reconecta/auth/me/dados` | Exporta em JSON os dados da conta e os registros do titular (LGPD, art. 18, II). |
| DELETE | `/reconecta/auth/me` | Exclui a conta por anonimização: remove identificação e mantém pedidos/doações como estatística (LGPD, art. 16). |
| GET | `/reconecta/publico/resumo` | Contadores públicos. |
| GET | `/reconecta/publico/opcoes` | Categorias e unidades aceitas. |
| GET | `/reconecta/publico/doacoes` | Pedidos abertos. Paginação `pagina`/`por_pagina` (máx. 50), filtros `categoria`, `uf`, `busca`; cabeçalhos `X-Total-Count`, `X-Pagina`, `X-Por-Pagina`. |
| GET | `/reconecta/publico/doacoes/{id}` | Detalhe do pedido com progresso por item. |
| GET | `/reconecta/publico/ongs` | ONGs da rede: nome, município/UF e pedidos abertos, sem contato nem CNPJ. |
| POST | `/reconecta/publico/doacoes/{id}/contribuicoes` | Doar (multipart: item, quantidade, validade, 4 respostas, foto). Limite de 20 por hora por usuário (429 `MUITAS_TENTATIVAS`). |
| GET | `/reconecta/contribuicoes/{id}/foto` | Foto da doação (só quem doou ou a empresa dona). |
| GET/POST | `/reconecta/painel/doacoes` | Pedidos da organização logada / publicar pedido. |
| DELETE | `/reconecta/painel/doacoes/{id}` | Remover pedido próprio. |
| GET | `/reconecta/painel/minhas-doacoes` | Doações feitas pela pessoa ou empresa logada. |
| POST | `/reconecta/painel/contribuicoes/{id}/receber` | Dono do pedido confirma a entrega da contribuição. |
| POST | `/reconecta/painel/contribuicoes/{id}/nao-recebida` | Dono do pedido registra que a contribuição não chegou. |
| GET/POST | `/reconecta/excedentes` | Lista excedentes disponíveis / publica a oferta da empresa de alimentos ou da pessoa física. POST em multipart: `dados` (o JSON da oferta) e `foto` do alimento mostrando a validade (JPEG, PNG ou WebP reais, até 5 MB, sem metadados ao gravar). JSON sem foto: 400 com `campos.foto`. |
| GET | `/reconecta/excedentes/{id}/foto` | Foto da validade: quem publicou e ONGs logadas (oferta aberta ou reservada por ela); os demais recebem 404. |
| GET | `/reconecta/excedentes/meus` | Excedentes publicados pela organização logada. |
| GET | `/reconecta/excedentes/reservas` | Reservas da ONG logada. |
| GET/DELETE | `/reconecta/excedentes/{id}` | Detalhe / cancelamento pelo publicador quando disponível. |
| POST | `/reconecta/excedentes/{id}/reservar` | ONG reserva um excedente disponível. |
| POST | `/reconecta/excedentes/{id}/cancelar-reserva` | Reservante ou publicador libera a reserva. |
| POST | `/reconecta/excedentes/{id}/confirmar-retirada` | Publicador confirma a retirada. |
| GET | `/reconecta/excedentes/rota` | ONG: ordem das retiradas reservadas (vizinho mais próximo + 2-opt), distâncias e links do OpenStreetMap. |
| GET | `/reconecta/dashboard` | Indicadores, séries, ranking, alertas e últimas doações (agregados). |
| GET | `/reconecta/dashboard/impacto` | Kg físicos e estimados, refeições potenciais por UF/região e por município de quem recebeu (só cidade/UF, sede IBGE e números), match, avaliação da IA e calor por dia/hora. |
| GET | `/reconecta/dashboard/seguranca` | Resumo versionado SAST/STRIDE e controles de segurança declarados. |
| POST | `/reconecta/ia/interpretar-pedido` | Organização logada: texto livre → itens sugeridos para revisão. Categoria pelo classificador treinado. Limite de 10 por minuto por organização (429 `MUITAS_TENTATIVAS`). |
| POST | `/reconecta/ia/resumo-dashboard` | Resumo e recomendações a partir dos agregados. Limite de 10 por minuto por IP (429 `LIMITE_IA`). |
| POST | `/reconecta/ia/risco-descarte` | Estima risco de descarte de um lote com modelo treinado em dados simulados; devolve probabilidade, prioridade e aviso de limitação. Limite de 10 por minuto por IP. |
| POST | `/reconecta/ia/sugerir-destino` | Interpreta alimentos oferecidos e sugere pedidos compatíveis com pontuação e motivos. |
| GET | `/reconecta/tempo-real` | Fluxo SSE de eventos públicos e privados autorizados. |
| GET | `/reconecta/novidades` | Consulta JSON de eventos para retomada e fallback. |
| GET | `/reconecta/notificacoes` | Notificações privadas da sessão. |
| POST | `/reconecta/notificacoes/lidas` | Marca notificações como lidas até um id. |
| GET público / POST admin | `/reconecta/estabelecimentos/` | Lista pública sem e-mail/telefone; POST verifica CNPJ ativo e CNAE alimentar. |
| GET público / PUT/DELETE admin | `/reconecta/estabelecimentos/{id}` | GET sem contato; admin recebe registro completo. DELETE com dependentes: 409. |
| GET público / POST admin | `/reconecta/instituicoes/` | Lista pública sem e-mail/telefone; POST verifica CNPJ ativo. |
| GET público / PUT/DELETE admin | `/reconecta/instituicoes/{id}` | GET sem contato; admin recebe registro completo. DELETE com reservas: 409. |
| GET público / POST admin | `/reconecta/doacoes/` | CRUD legado do CP1; escrita administrativa. |
| GET público / PUT/DELETE admin | `/reconecta/doacoes/{id}` | DELETE com itens, contribuições ou reservas: 409. |

A tabela cobre as **60 operações em 46 caminhos** da API, conferidas contra o [swagger.json](swagger.json), que é a exportação da especificação OpenAPI atual; a versão interativa fica em `/swagger`.

## Banco de dados (critério 5 do CP2)

Entidades: `estabelecimentos`, `doadores`, `instituicoes`, `doacoes` (pedido), `itens_doacao`, `contribuicoes` (doações para pedidos), `excedentes`, `itens_excedente`, `eventos`, `notificacao_leitura`, `geolocalizacoes` (cache de coordenadas por hash do endereço) e `reservas` (modelo legado do CP1). A revisão do domínio, com diagrama ER, está em [docs/modelagem.md](docs/modelagem.md), organizada por item do critério:

| Item do critério | Seção em `docs/modelagem.md` | Resumo |
|---|---|---|
| Duplicidade de informações | Duplicidade de informações | Itens em linhas próprias; progresso calculado, não gravado; repetições que ficaram (fotografia do item na contribuição, `doacao_id`) são deliberadas e controladas |
| Relacionamentos | Relacionamentos | Cardinalidades 1:N com chaves estrangeiras `ON DELETE RESTRICT` (nada some em cascata sem querer) |
| Integridade dos dados | Integridade dos dados | PK, FK, UNIQUE (CNPJ, CPF, e-mail), NOT NULL e CHECKs nomeados de status, quantidade e origem — iguais no código (ORM) e no `schema.sql`; FK composta impede vincular um item a outro pedido |
| Organização das entidades | Organização das entidades | O que cada tabela representa e quem escreve nela |
| Índices quando necessários | Índices | Índices dos pedidos e dos excedentes ligados às consultas que aceleram |
| Normalização | Normalização | 1FN, 2FN e 3FN com exemplos e as exceções deliberadas |
| Justificar decisões | Decisões de modelagem | Tabela decisão × alternativa × motivo |

As mudanças são aplicadas por `migracoes.py` no início da aplicação, de forma idempotente, em PostgreSQL (restrições com `NOT VALID` + `VALIDATE`, abortando sem apagar dados se houver registro inválido) e em SQLite. Testes em `tests/test_integridade_banco.py`; a prova em PostgreSQL roda com `CP2_PG_SUPERUSER_PASSWORD_FILE` apontando para um arquivo com a senha do superusuário (cria e apaga um banco temporário).

## Documentação (critério 6 do CP2)

Onde cada item exigido está atualizado:

| Item do critério | Onde está |
|---|---|
| README | Este arquivo, reescrito para o CP2 (fluxo de pedidos e doações, dashboard, LLM, segurança) e ampliado com dataset, modelo, STRIDE, SAST, Docker, CI/CD e nuvem |
| Swagger | `/swagger` (gerado do código pelo Flask-RESTX) e [swagger.json](swagger.json) exportado da API atual, com todos os endpoints, modelos de entrada/saída, códigos de resposta e o cabeçalho `X-Admin-Token` |
| Instruções de instalação | Seções **Instalação** (Python local com venv, `requirements.txt` e `requirements-dev.txt`, PostgreSQL ou SQLite, Ollama gratuito; ou Docker Compose), **Execução** e **Testes**; nuvem em [docs/implantacao.md](docs/implantacao.md) |
| Endpoints | Seção **Endpoints**: todas as 52 operações da API (39 caminhos) com método, caminho e descrição, mais as rotas de página em **Arquitetura** |
| Arquitetura | Seção **Arquitetura**: um arquivo por responsabilidade, front-end em `static/`, testes em `tests/`, docs em `docs/` |
| Funcionalidades | Seções **Funcionalidades** e **Regras de negócio** (RN01–RN11), mais as tabelas dos critérios 2, 3 e 4 |
| Variáveis de ambiente | Seção **Variáveis de ambiente** (as 11 da aplicação, as 2 do Docker Compose e as dos testes opcionais) e o arquivo `.env.example` |

Os documentos de apoio estão listados em [Documentação complementar](#documentação-complementar).

## Testes (critério 7 do CP2)

Comando para demonstrar na apresentação (na pasta do projeto, com o ambiente virtual ativo):

```bash
python -m pytest -v
```

Resultado atual: **455 passed, 10 skipped**. Os testes usam SQLite isolado (em memória ou em arquivo temporário) e simulam a Receita, o Groq e o Ollama, então rodam sem internet e sem tocar no banco real. Os testes pulados são provas opcionais que precisam de um ambiente a mais:

- 4 provas em PostgreSQL (`tests/test_integridade_banco.py` e `tests/test_excedente_pessoa_fisica.py`): rodam com `CP2_PG_SUPERUSER_PASSWORD_FILE` apontando para um arquivo com a senha do superusuário; criam e apagam um banco temporário.
- 1 prova de CSP num navegador de verdade (`tests/test_nuvem.py`): roda com `RECON_CSP_URL=http://localhost:5000` e a aplicação no ar pelo Docker Compose; abre as páginas com o Playwright e falha se o console acusar violação de CSP.

| Tipo de teste | Arquivos | O que cobrem |
|---|---|---|
| Unitários | `test_cnae_alimentos.py`, `test_classificador.py`, `test_ciclo_ia.py`, partes de `test_ia.py` e `test_cadastro.py` | Critério de atividade alimentar por CNAE, dígitos de CPF/CNPJ, validação da saída da LLM, fallback, treino reprodutível, recomendação e limiares da IA |
| De endpoints | `test_cadastro.py`, `test_auth.py`, `test_publico_painel.py`, `test_pedidos.py`, `test_dashboard.py`, `test_ia.py`, `test_dominio_r11.py`, `test_tempo_real.py`, `test_geo.py`, `test_lgpd.py`, `test_crud_seguro.py`, `test_cp2_api.py`, `test_nuvem.py` | Códigos HTTP, formato das respostas e erros JSON de cadastro, login, pedidos, doações, excedentes, confirmação de entrega, eventos, notificações, dashboard, IA, rota de coleta, CRUDs e saúde |
| De regras de negócio | `test_cadastro.py`, `test_pedidos.py`, `test_dominio_r11.py`, `test_tempo_real.py`, `test_crud_seguro.py`, `test_auth.py`, `test_ia.py`, `test_nuvem.py`, `test_lgpd.py` | Elegibilidade por natureza jurídica ou CNAE, reserva exclusiva por ONG, confirmação pelo dono do pedido, privacidade de eventos e fotos, limites de login, IA, privacidade/LGPD e doações |
| De integração | `test_integridade_banco.py`, `test_migracao_doador.py`, `test_migracao_pedidos.py`, `test_dominio_r11.py`, `test_tempo_real.py`, `test_fuso.py`, `test_cp2_api.py`, `test_nuvem.py`, `test_classificador.py` | Aplicação + SQLite isolado: migrações, restrições, transições de estado, fluxo de eventos, fuso, consultas SQL, foto no banco, auditoria e classificador dentro da interpretação de pedidos |

## LLM (critério 8 do CP2)

O ReConecta usa LLM **gratuita** via Groq Free (`openai/gpt-oss-20b`) quando há chave, depois Ollama local (`qwen2.5:3b`). Sem ambos, usa classificador e regras. Essas funções apoiam as regras de negócio:

1. **"Preencher com IA"** (painel da empresa → "Publicar pedido de doação"): a empresa escreve, por exemplo, "Precisamos de 100 caixas de leite e 100 pães até sexta-feira"; a LLM classifica e estrutura os itens nas **categorias e unidades fixas da plataforma** e sugere o prazo. O formulário é preenchido para a empresa revisar; a publicação continua passando pelas validações do pedido.
2. **"Gerar resumo com IA"** (dashboard): a LLM interpreta os indicadores agregados dos pedidos e doações e devolve um resumo e recomendações para apoiar decisões.

3. **"Sugerir destino"** (`POST /reconecta/ia/sugerir-destino`): interpreta o alimento oferecido, compara com os pedidos disponíveis e devolve até cinco sugestões com pontuação e motivos para a pessoa escolher.

Quando a LLM não está disponível, ou devolve uma categoria fora da lista, a categoria de cada item vem do classificador treinado do projeto (seção [Modelo funcional local](#modelo-funcional-local)).

Modelo, finalidade, dados enviados, validação da saída, limites, fallback e proteção dos dados estão em [docs/llm.md](docs/llm.md). Endpoints: `POST /reconecta/ia/interpretar-pedido`, `POST /reconecta/ia/resumo-dashboard` e `POST /reconecta/ia/sugerir-destino`; código em `llm_service.py`, `IA.py` e `conexao.py`; testes em `tests/test_ia.py`, `tests/test_groq.py` e `tests/test_tempo_real.py`.

## Dataset estruturado

O projeto tem dois conjuntos de dados próprios em `data/`, **sintéticos e curados à mão** (nenhum dado coletado de usuários, nenhum dado pessoal):

| Arquivo | Conteúdo |
|---|---|
| [`data/alimentos.csv`](data/alimentos.csv) | 925 nomes de alimentos como uma empresa escreve num pedido ("leite integral 1L", "pao frances", "arroz tipo 1 5kg"), com `id`, `texto`, `categoria` (as 8 da aplicação), `unidade_sugerida` e `origem`. Sem duplicata, nem ignorando acento e caixa. |
| [`data/pedidos_avaliacao.jsonl`](data/pedidos_avaliacao.jsonl) | 66 pedidos em texto livre (20 fáceis, 22 médios, 24 difíceis) com o gabarito de itens e prazo: 130 itens. |
| [`data/README.md`](data/README.md) | Dicionário de dados, como foi construído, critérios de categoria, distribuição, divisão treino/teste e licença. |

Divisão treino/teste estratificada por categoria (740/185), com semente fixa. Para refazer o CSV: `python data/gerar_dataset.py`.

## Modelo funcional local

Além da LLM opcional, o ReConecta tem um **modelo treinado no próprio dataset**: um classificador Naive Bayes multinomial que escolhe a categoria de cada item do pedido. É Python puro (só biblioteca padrão), roda dentro da aplicação em menos de 1 ms, não precisa de GPU nem de serviço externo e é salvo em JSON, sem `pickle`.

| Medida (execução de 2026-10-13) | Classificador treinado | Regra de palavras-chave anterior |
|---|---|---|
| Acurácia no teste (185 linhas) | **77,8%** | 40,0% |
| F1 macro no teste | **0,78** | 0,45 |
| Validação cruzada de 5 dobras (925 linhas) | **81,2% ± 1,7** | — |
| Categoria certa nos 130 itens dos pedidos de avaliação | **84,6%** | 56,2% |
| Pedidos inteiros certos, sem a LLM (66 pedidos) | **48** | 25 |

Na avaliação de 2026-10-14 dos mesmos 66 pedidos, as regras acertaram **25/66**, o classificador + regras **48/66** e o fluxo Groq Free → Ollama → regras **51/66** pedidos inteiros. Das 66 respostas desse fluxo, **44** foram aceitas do Groq, **11** vieram do Ollama local e **11** das regras. Os 51 acertos pertencem ao fluxo completo, não apenas ao Groq. O Ollama da avaliação local anterior acertou **50/66**, com 3,6 s de latência média por pedido; veja [docs/avaliacao-modelos.md](docs/avaliacao-modelos.md). O script [`scripts/avaliar_groq.py`](scripts/avaliar_groq.py) e o resultado [`modelo/avaliacao_groq.json`](modelo/avaliacao_groq.json) permitem repetir a comparação. Os casos sintéticos formam um gabarito de regressão, não uma estimativa de desempenho no público.

Uso na aplicação: em `POST /reconecta/ia/interpretar-pedido`, a categoria de um item vem do classificador quando a confiança passa do limiar (0,15, escolhido pelos dados); senão das palavras-chave; senão "Outros". Na nuvem, o Groq responde somente se `GROQ_API_KEY` estiver configurada; sem ela, o classificador e as regras continuam disponíveis. O contrato da API e as telas não mudaram, e a organização continua revisando antes de publicar.

```bash
python scripts/treinar_modelo.py                 # treina, avalia e grava modelo/classificador_categorias.json
python scripts/classificar.py "pao de queijo"    # demonstração no terminal
python scripts/avaliar_modelos.py                # regras x classificador x LLM (use --sem-llm sem o Ollama)
python scripts/avaliar_groq.py                  # 66 pedidos; chama Groq Free só com chave local
python scripts/ciclo_ia.py                        # treina, avalia a conexão e aplica os limiares
```

Detalhes (atributos, treino, métricas por categoria, matriz de confusão, limiar e limitações) em [docs/dataset-modelo.md](docs/dataset-modelo.md).

### Validação e ciclo da IA

O gabarito manual [`data/ofertas_avaliacao.jsonl`](data/ofertas_avaliacao.jsonl) tem 86 ofertas com pedidos abertos: 64 com destino correto e 22 sem destino. `python scripts/avaliar_conexao.py` mede `conexao.casar` e grava [`modelo/avaliacao_conexao.json`](modelo/avaliacao_conexao.json). Na execução de 2026-10-14, o classificador acertou **144/185 (77,84%)** no teste separado; a conexão acertou **57/64 (89,06%)** no top-1 e no top-3 e retornou vazio corretamente em **22/22 (100%)** casos sem destino. Os sete erros restantes, sobretudo nomes regionais equivalentes, estão no JSON.

`python scripts/ciclo_ia.py` refaz o treino determinístico e as duas avaliações, grava data, versão e tamanhos em [`modelo/metricas.json`](modelo/metricas.json) e falha abaixo dos mínimos de [`modelo/limiares.json`](modelo/limiares.json): **75%** no classificador, **85%** no top-1 e top-3, **95%** na rejeição correta. O job `ia` em [CI](.github/workflows/ci.yml) roda esse comando, publica as métricas e é exigido antes do deploy. Tudo roda sem LLM ou serviço pago; detalhes e critério do gabarito em [docs/dataset-modelo.md](docs/dataset-modelo.md).

### Predição simulada de descarte

O mesmo ciclo treina e testa dois modelos scikit-learn com pandas sobre 3.200
lotes **simulados** de [`data/lotes_descarte.csv`](data/lotes_descarte.csv).
A regressão logística obteve no teste separado acurácia **67,50%**, F1 **50,48%**
e ROC-AUC **70,15%**; os limites do CI são 64%, 47% e 67%. O artefato
[`modelo/risco_descarte.json`](modelo/risco_descarte.json) roda em Python puro na
API, sem essas bibliotecas na imagem. A lista pública de excedentes usa a
probabilidade para priorizar ofertas e identifica as de prioridade alta. A
temperatura e a distância não cadastradas aparecem como ausentes; a previsão
não é uma taxa observada no sistema nem substitui a decisão da ONG. No mesmo
teste de 185 alimentos, o TF-IDF linear obteve 74,59% de acurácia, abaixo dos
77,84% do Naive Bayes já usado; o classificador atual foi mantido. Regras da
simulação, matriz de confusão, teste e limitações estão em
[docs/dataset-modelo.md](docs/dataset-modelo.md).

## Segurança (STRIDE e SAST)

- **Matriz de riscos STRIDE**: [docs/stride.md](docs/stride.md). Traz o diagrama de fluxo de dados com as fronteiras de confiança, os ativos e atores, a matriz com probabilidade × impacto, os controles existentes com referência `arquivo:linha`, as lacunas e os riscos residuais.
- **Relatórios SAST**: pasta [`relatorios/sast/`](relatorios/sast/), versionada. Bandit no código Python (`bandit.json`, `bandit.txt`, `bandit.html`) e Trivy em três varreduras: arquivos e dependências (`trivy-fs.*`, scanners `vuln,secret,misconfig`), configuração do Dockerfile (`trivy-config.*`) e imagem Docker (`trivy-image.*`). A triagem achado a achado está em `docs/sast.md`.
- **Resumo dos achados**: a varredura SAST de 13/10 registrou 0 achados Bandit e 0 vulnerabilidades/segredos/misconfigurações em arquivos. A imagem Debian anterior tinha 44 ocorrências HIGH de 8 CVEs. Em 15/10, a imagem Alpine construída neste branch foi varrida com Trivy 0.75.0 (`vuln,secret,misconfig`) e teve **0 vulnerabilidades, 0 segredos e 0 misconfigurações**. Os resultados têm datas próprias; veja o antes, o depois e as limitações em [docs/sast.md](docs/sast.md).
- **Refazer os relatórios**: `python scripts/sast.py` na raiz do projeto. Precisa do Bandit (`pip install -r requirements-dev.txt`) e do binário gratuito do Trivy no PATH ou em `TRIVY=<caminho>`.
- **Security Gates no pipeline**: o GitHub Actions repete Bandit e Trivy a cada push ou pull request na `main` e guarda os relatórios como artefatos. Os portões reprovam: Bandit em severidade alta (`-lll`); Trivy `fs` em vulnerabilidade HIGH/CRITICAL com correção, segredo ou misconfig alta; `trivy config` em HIGH/CRITICAL; Trivy `image` em CRITICAL corrigível; **Semgrep** (pacotes `p/python`, `p/flask`, `p/secrets` e `p/owasp-top-ten`, mais o ruleset próprio `semgrep-local.yml`) em achado ERROR; **pip-audit** em qualquer CVE de `requirements.txt`/`requirements-dev.txt` (com SBOM CycloneDX como artefato); **gitleaks** em qualquer segredo nos arquivos (diretório e histórico); o job `guardas` roda `pre-commit run --all-files` — os mesmos hooks do commit local — e o job `ia` se as métricas caírem abaixo de `modelo/limiares.json`. `scripts/resumo_sast.py` declara a regra e o último resultado de cada portão em `relatorios/sast/resumo.json`, e o dashboard mostra esse bloco junto à rosca "Mitigadas / Em análise / Críticas".
- **Segurança "enquanto coda" (pre-commit)**: `.pre-commit-config.yaml` roda checks básicos, Bandit, Semgrep (ruleset local, offline), pip-audit e gitleaks **antes de cada commit**. Instalar com `pip install pre-commit semgrep pip-audit`, o binário do gitleaks no PATH e `pre-commit install` uma vez por clone. Varreduras completas e triagem da rodada 18: [docs/seguranca.md](docs/seguranca.md), relatórios em [`relatorios/seguranca/`](relatorios/seguranca/).
- **LGPD**: a política de privacidade fica em `/privacidade` (mapa de dados em [`docs/lgpd.md`](docs/lgpd.md)); o cadastro exige aceite, gravado com versão e data (`consentimento_versao`, `consentimento_em`); o titular exporta tudo em `GET /reconecta/auth/me/dados` e exclui a conta por anonimização em `DELETE /reconecta/auth/me` — pedidos e doações ficam só como estatística.
- **Guardas da IA e log mínimo (rodada 18)**: o NVIDIA NeMo Guardrails (`guardrails/`, Colang) barra injeção de prompt e pedidos fora do tema antes da LLM e descarta respostas com dado pessoal, link ou vazamento do prompt; no CI roda o NeMo de verdade (job `guardrails`), em produção as mesmas ações rodam sem a biblioteca para caber no Render free. Os logs não levam CPF, CNPJ, e-mail, telefone, endereço, texto livre, cookie, token nem IP completo (`registro.py`, `pii.py`, `gunicorn.conf.py`). O NeMo protege a IA; os hooks de pre-commit protegem o código. Números, achados e riscos residuais em [docs/seguranca.md](docs/seguranca.md); o inventário de logs em [docs/lgpd.md](docs/lgpd.md#logs-log-mínimo).
- **Varredura completa da rodada 18** (detalhes, comandos, números e falsos positivos em [docs/seguranca.md](docs/seguranca.md)):
  - **SAST**: Bandit (0 alto/médio), Semgrep com 288 regras oficiais + regras próprias (37 achados iniciais → 0) e Trivy de configuração (0).
  - **SCA**: pip-audit e Trivy de dependências (0 vulnerabilidades nas 15 bibliotecas) e SBOM CycloneDX em `relatorios/seguranca/sbom-cyclonedx.json`.
  - **Segredos**: gitleaks no código e nos 123 commits do histórico (nenhum segredo real; 3 falsos positivos registrados por impressão digital).
  - **DAST**: OWASP ZAP 2.17 (baseline + API pelo `swagger.json`) contra o Compose efêmero, com sessões fictícias de doador, empresa e ONG: 0 crítico, 0 alto, 0 médio.
  - **IAST**: sensor próprio (`iast_sensor.py`, ligado só com `RECONECTA_IAST=1`) que vigia SQL com dado da requisição, código dinâmico, arquivos e conexões durante a suíte e o ZAP: 0 achados.
  - **Autorização por objeto (BOLA/IDOR)**: `scripts/avaliar_autorizacao.py` gera a matriz pelo Swagger e tenta cada escrita e leitura privada como dono, outro usuário, outro perfil e anônimo (213 requisições, 0 falhas).
- **13 portões no GitHub Actions** antes de publicar: testes, ciclo da IA, Bandit, Trivy, Semgrep, pip-audit, gitleaks, pre-commit, Docker, DAST, IAST + BOLA, guardas da IA (NeMo) e resumo de segurança. Se um falhar, o Render não publica.

Controles que estão no código:

| Controle | Onde |
|---|---|
| Senhas com hash scrypt; sessão em cookie HttpOnly e SameSite=Lax; cookie só por HTTPS com `COOKIE_SEGURO=1` | `Auth.py`, `app.py` |
| Cabeçalhos em todas as respostas: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` e `Content-Security-Policy` (sem script inline e sem `unsafe-eval`); `Strict-Transport-Security` com `COOKIE_SEGURO=1` | `app.py` |
| Trilha de auditoria: logger `reconecta.auditoria`, uma linha JSON por evento (login, logout, cadastro, edição de dados, troca de senha, pedido publicado ou removido, doação aceita ou recusada, uso do token de administrador), com data, ator, IP truncado (/24) e resultado, sem senha, documento, e-mail ou foto | `Auth.py`, `Cadastro.py`, `Painel.py`, `Contribuicoes.py`, `crud_admin.py` |
| Limites de uso (RN11) | `Auth.py`, `IA.py`, `Contribuicoes.py` |
| Foto conferida pelos bytes, até 5 MB, visível só para quem doou e para a empresa dona do pedido | `Contribuicoes.py` |
| LLM só em endereço local (ou no serviço `ollama` do Compose), sem redirecionamento e sem proxy; saída validada e nunca gravada direto no banco | `llm_service.py` |
| Imagem Docker com usuário sem privilégio e sem segredos; `.dockerignore` deixa `.env`, `instance/` e testes de fora | `Dockerfile`, `.dockerignore` |

## Docker e Docker Compose

O [`Dockerfile`](Dockerfile) parte de `python:3.12-alpine` fixado por digest e aplica as atualizações de pacotes do Alpine no build. Instala só o `requirements.txt` de produção, remove o `pip`, roda com o usuário sem privilégio `reconecta` e serve a aplicação com gunicorn gthread (2 workers, 8 threads, timeout de 90 s). Tem `HEALTHCHECK` em `/reconecta/saude`, respeita a variável `PORT` do Render e não leva segredo nenhum: tudo chega por variável de ambiente. A troca da base Debian para Alpine eliminou os 44 achados HIGH da imagem anterior no [snapshot Trivy de 15/10/2026](docs/sast.md); refaça o scan em cada reconstrução.

O [`docker-compose.yml`](docker-compose.yml) sobe dois serviços, mais um opcional:

| Serviço | Imagem | Papel |
|---|---|---|
| `app` | construída do `Dockerfile` | Aplicação na porta 5000; só inicia depois que o banco está saudável. |
| `db` | `postgres:17-alpine` | PostgreSQL de desenvolvimento (`reconecta_dev`), com volume nomeado e healthcheck `pg_isready`. |
| `ollama` | `ollama/ollama` | Opcional, perfil `ia`: a LLM local dentro do Compose. |

```bash
docker compose build app
docker compose up -d --wait
curl --fail http://localhost:5000/reconecta/saude     # {"status":"ok","banco":"ok"}

# opcional: LLM local dentro do Compose
docker compose --profile ia up -d --wait
docker compose exec ollama ollama pull qwen2.5:3b

docker compose down        # desliga e mantém o banco de desenvolvimento
docker compose down -v     # desliga e apaga o volume deste Compose
```

As senhas padrão do Compose (`dev-only-...`) servem só para máquina de teste; defina `POSTGRES_PASSWORD` e `SECRET_KEY` no `.env` antes de compartilhar o ambiente.

## Pipeline CI/CD (GitHub Actions)

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda a cada push e pull request na `main`, e também por acionamento manual. As permissões são mínimas (`contents: read`).

| Job | O que faz | Quando falha |
|---|---|---|
| `testes` | Python 3.12, instala `requirements.txt` e `requirements-dev.txt`, roda `python -m pytest` e guarda o relatório JUnit como artefato | Algum teste falha |
| `ia` | Treina o classificador, avalia a conexão, confere `modelo/limiares.json` e publica `metricas-ia` | Qualquer métrica cai abaixo do mínimo |
| `sast-bandit` | Bandit no código da aplicação; relatórios JSON e texto como artefato `bandit-report` | Achado de severidade alta (`bandit -lll`) |
| `sast-trivy` | Constrói a imagem e roda o Trivy nos arquivos (dependências, segredos, configuração) e na imagem; tabelas e SARIF como artefato `trivy-report` | Arquivos: achado HIGH/CRITICAL corrigível; configuração (IaC): achado HIGH/CRITICAL; imagem: qualquer achado HIGH/CRITICAL |
| `docker` | `docker compose build app`, `docker compose up -d --wait` e chamada a `/reconecta/saude` | A imagem não constrói ou a aplicação não fica saudável |
| `deploy` | Opcional e manual: dispara o Deploy Hook do Render guardado no segredo `RENDER_DEPLOY_HOOK_URL` | Sem o segredo, termina com aviso e sem erro |

A entrega contínua normal não depende do job `deploy`: o `render.yaml` usa `autoDeployTrigger: checksPass`, então o Render publica a `main` sozinho depois que os checks do GitHub passam.

## Nuvem: Render e Supabase

- **Aplicação**: Web Service no plano gratuito do Render, criado pelo Blueprint [`render.yaml`](render.yaml) (`runtime: docker`, `healthCheckPath: /reconecta/saude`). URL pública: **https://reconecta-iota.onrender.com** (saúde em [`/reconecta/saude`](https://reconecta-iota.onrender.com/reconecta/saude), Swagger em [`/swagger`](https://reconecta-iota.onrender.com/swagger)). No plano gratuito o serviço hiberna sem uso; o primeiro acesso depois disso pode levar cerca de um minuto.
- **Banco**: PostgreSQL no plano gratuito do Supabase, ligado pela `DATABASE_URL` com a URL do Session pooler. Situação: no ar desde 2026-10-13, com as 7 tabelas criadas pela própria aplicação ao iniciar; conferido com um cadastro feito pelo site público e lido direto no banco (registro de teste apagado em seguida). A publicação é automática: o Render só publica um commit da `main` depois que o GitHub Actions passa (`autoDeployTrigger: checksPass`).
- **Variáveis no Render**: `DATABASE_URL` (informada na criação), `SECRET_KEY` (gerada pelo Render), `COOKIE_SEGURO=1`, `ADMIN_TOKEN` (opcional) e `GROQ_API_KEY` (opcional, `sync: false`, somente conta Free).
- **O que muda na nuvem**:
  - As tabelas são criadas e migradas no primeiro início.
  - As fotos das doações ficam no banco, porque o disco do plano gratuito é apagado a cada reinício.
  - O Ollama não roda no plano gratuito. Com chave Groq Free configurada, a interpretação e o resumo usam o Groq; sem chave, classificador e regras respondem com `fonte: "regras"`.

O passo a passo completo (criar o projeto no Supabase, criar o serviço no Render, ativar o CI/CD e conferir) está em [docs/implantacao.md](docs/implantacao.md).

## Documentação complementar

- [docs/modelagem.md](docs/modelagem.md) — modelagem, normalização e índices;
- [docs/otimizacoes.md](docs/otimizacoes.md) — otimizações da API com medições;
- [docs/llm.md](docs/llm.md) — LLM: modelo, finalidade, dados enviados, uso, limitações e segurança;
- [docs/dataset-modelo.md](docs/dataset-modelo.md) — dataset, classificador treinado, métricas e uso na aplicação;
- [docs/avaliacao-modelos.md](docs/avaliacao-modelos.md) — comparação entre regras, classificador e LLM local;
- [data/README.md](data/README.md) — dicionário de dados dos dois conjuntos;
- [docs/implantacao.md](docs/implantacao.md) — Docker Compose, Supabase, Render e CI/CD, passo a passo;
- [docs/stride.md](docs/stride.md) — matriz de riscos STRIDE;
- [docs/sast.md](docs/sast.md) — triagem dos relatórios do Bandit e do Trivy;
- [SECURITY.md](SECURITY.md) — relato responsável de vulnerabilidades e escopo de testes locais;
- [docs/cnae-alimentos.md](docs/cnae-alimentos.md) — critério de atividade alimentar;
- [docs/geo.md](docs/geo.md) — localização, distância na recomendação, avisos por proximidade e rota de coleta.

## Limitações conhecidas

- O modelo legado `reservas` do CP1 continua sem endpoints próprios; a reserva e retirada atuais usam as tabelas `excedentes` e `itens_excedente`.
- Recuperação de senha não implementada.
- A consulta de CNPJ depende de serviços públicos externos (com cache de 10 minutos e fontes alternativas).
- A LLM Groq Free é externa e opcional; Ollama pode rodar localmente. As sugestões passam por validação e revisão humana; sem ambos, usam classificador e regras automáticas e indicam `fonte: "regras"`. O Groq recebe texto livre após remoção de padrões comuns de identificadores, que não cobre todos os formatos.
- O classificador conhece o vocabulário de 254 alimentos do dataset, que é sintético; alimento muito diferente pode cair na categoria errada, e a empresa sempre revisa antes de publicar.
- O plano gratuito do Render suspende o serviço depois de um tempo sem acesso, então o primeiro acesso seguinte demora; ele também não roda o Ollama.
- Os limites de uso (login, IA, doações) ficam na memória de cada processo: com 2 workers do gunicorn, cada um conta separado, e a contagem zera quando o serviço reinicia.
- Riscos residuais registrados em [docs/stride.md](docs/stride.md), seção 5: não há prova de posse do e-mail nem do CNPJ no cadastro (exigiria serviço de e-mail); não há limite global de requisições por IP e os limites de uso ficam na memória de cada processo; o token de administrador é único e estático; a trilha de auditoria vai só para o log, sem persistência. As actions do CI e a imagem base usam digest/SHA; o `apk upgrade` consulta o repositório Alpine durante cada build, então um novo scan continua necessário.

## Documentação Swagger

Interativa em `http://localhost:5000/swagger`, gerada pelo Flask-RESTX a partir do código (sempre igual à API em execução). A especificação exportada está em [swagger.json](swagger.json) e é regenerada a cada mudança de endpoint. Na nuvem, fica em `/swagger` da URL pública desta entrega (seção [Nuvem: Render e Supabase](#nuvem-render-e-supabase)). O endereço publicado no CP1 (https://reconecta.onrender.com/swagger) é de outra conta e mostra a versão do CP1.

## Avaliação de segurança

O [guia de avaliação](docs/avaliacao-cyber-risk.md) descreve a arquitetura, o ambiente isolado sem credenciais de produção, contas fictícias, comandos de testes e riscos residuais. Execute testes ativos somente contra a instância local.

## Organização no Trello

[Quadro ReConecta no Trello](https://trello.com/invite/b/6a96cdf34f25b339652662c3/ATTI4b7785042036ae55024963ac1546279b355F294D/reconecta)



## Roteiro da apresentação

1. Abrir https://reconecta-iota.onrender.com alguns minutos antes: o plano gratuito do Render dorme quando fica parado e leva até um minuto para acordar.
2. **Página inicial**: abas Pedidos das ONGs, Alimentos doados e ONGs na rede; botão **Doar** no topo e o assistente "Tenho alimento para doar", que lê o texto com o Groq (`openai/gpt-oss-20b`) e sugere a ONG certa e mais próxima.
3. **Fluxo ao vivo** (duas abas, uma como ONG e outra como doador ou empresa): publicar um pedido; doar com foto da validade; reservar; confirmar a retirada; marcar Recebi. Os avisos chegam no sino em segundos.
4. **Dashboard** (`/dashboard`): em **Demonstração**, kg salvos, refeições por região no mapa de calor, acurácia da IA, tempo médio de match e segurança; em **Dados reais**, os números de verdade.
5. **API e segurança**: Swagger interativo em `/swagger`; portões verdes no GitHub Actions; relatórios em `relatorios/` e `docs/seguranca.md`.

Inteligências do projeto: leitura de texto por LLM (Groq Free, com Ollama local e regras como reserva, protegida pelas guardas NeMo), classificador de categoria Naive Bayes (77,8%), modelo de risco de descarte com scikit-learn (67,5%, AUC 0,70, dados simulados) e recomendação Doador × ONG por pontuação com distância (89,1% de acerto na primeira sugestão). Todas são medidas a cada envio pelo job `ia`.

## Integrantes

| Integrante | RM |
|---|---|
| Aline Delphino Chiaramonte | RM569860 |
| Brian Barreto Brasil | RM570384 |
| Enzo Gabriel Lima Miranda | RM573094 |
| Victor Deggerone Gomes | RM569518 |
| Lucas Silvério Bomtempo | RM568585 |

## Status

Entrega do CP2 — 2026.
