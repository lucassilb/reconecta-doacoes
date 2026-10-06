# Otimizações da API — Checkpoint 2

## Lista pública

`GET /reconecta/publico/doacoes` continua devolvendo uma **lista JSON**. A lista agora aceita `pagina` (a partir de 1), `por_pagina` (1–50), `categoria`, `uf` e `busca` (nome do item ou da empresa). O parâmetro antigo `limite` continua aceito (1–100), com precedência de `por_pagina` quando ambos vierem. O padrão é página 1 com 8 pedidos. A resposta informa `X-Total-Count`, `X-Pagina` e `X-Por-Pagina`. Parâmetros inválidos recebem 400 com `codigo: DADOS_INVALIDOS` e o mapa `campos`.

A consulta usa `EXISTS` para filtrar itens por categoria/nome, sem duplicar pedidos que têm vários itens. `selectinload` busca empresa, itens e contribuições em lotes antes da serialização. A mesma técnica foi aplicada ao detalhe público, ao resumo e às listas do painel. A ordem permanece por data de cadastro e ID decrescentes. O filtro de UF usa a forma `cidade/UF` presente no endereço cadastrado; como endereço é texto livre legado, cadastros sem esse padrão não são encontrados por UF.

## Dashboard

`GET /reconecta/dashboard` e `montar_dashboard()` usam somas e contagens por `GROUP BY` para contribuições por item, por pedido, por empresa e por dia. Consultas limitadas obtêm as 10 últimas doações e as 10 empresas com mais doações recebidas. A quantidade de consultas não cresce por pedido ou contribuição. A série temporal sempre contém 30 dias, com zero nos dias sem doações. O percentual soma `min(recebido, meta)` por item de pedido aberto antes da divisão pela soma das metas; excedentes não elevam o percentual acima de 100%.

## Medição local

`tests/test_cp2_api.py` usa o evento `before_cursor_execute` do SQLAlchemy e conta apenas instruções `SELECT`. Com 25 pedidos, um item em cada um, uma empresa e SQLite em memória no Windows:

| Operação | Antes | Depois |
|---|---:|---:|
| Lista de 25 pedidos | 52 SELECT, ~21 ms | 5 SELECT, ~15 ms |
| Dashboard de 25 pedidos | inexistente | 10 SELECT, ~23 ms |

O cenário "antes" executa a consulta e a serialização da lista original, com sessão limpa e carregamento preguiçoso. O cenário "depois" chama o endpoint paginado, incluindo a consulta adicional para `X-Total-Count`. São tempos de uma execução local, úteis apenas como ordem de grandeza; não representam latência de rede nem carga concorrente. Para repetir: `python -m pytest tests/test_cp2_api.py::test_consultas_lista_nao_crescem_com_numero_de_pedidos tests/test_cp2_api.py::test_dashboard_usa_consultas_agregadas_independentes_do_volume -q -s` com `DATABASE_URL=sqlite://`.

## Índices e erros

`models.py` e `migracoes.py` criam, de modo idempotente em SQLite e PostgreSQL, índices para as chaves estrangeiras de `doacoes`, `itens_doacao` e `contribuicoes`, além de `(status, data_limite_retirada)` para pedidos disponíveis e `(doacao_id, status)` para contribuições aceitas. `schema.sql` declara os mesmos índices para instalação manual. Índices aceleram os filtros e junções, com custo de espaço e de escrita.

Sob `/reconecta/`, erros 404, 405 e 500 retornam JSON com `codigo` e `mensagem`, sem detalhes internos. Com token válido, os CRUDs originais rejeitam corpo ausente, campos obrigatórios faltando e tipos inválidos com 400 e mapa `campos`. As respostas de sucesso da escrita e as rotas antigas mantêm seus formatos anteriores.

Os CRUDs legados exigem `ADMIN_TOKEN` via `X-Admin-Token` para POST/PUT/DELETE; GET de estabelecimentos e instituições oculta e-mail e telefone sem token válido. CNPJ e dependências são verificados antes da escrita, com erros JSON 400/409/422.

O dashboard filtra o intervalo de 30 dias pelas meias-noites de `America/Sao_Paulo` convertidas para UTC. O banco agrega contribuições por hora UTC com `extract` do SQLAlchemy (SQLite e PostgreSQL); Python atribui cada grupo ao dia de Brasília. Assim, a consulta retorna cerca de 720 grupos em vez de carregar todas as contribuições; uma mudança histórica de horário de verão pode alterar essa quantidade em uma hora.

## Redução de requisições desnecessárias

- **Dashboard em uma requisição**: a página `/dashboard` faz um único `GET /reconecta/dashboard`, que já traz indicadores, séries, ranking, alertas e últimas doações, em vez de um endpoint por cartão ou gráfico. O resumo da IA é calculado no servidor a partir dos mesmos agregados (o cliente não reenvia os dados).
- **Sessão consultada uma vez por página**: antes, `/painel` e `/entrar` chamavam `GET /reconecta/auth/me` duas vezes ao abrir (uma no cabeçalho, em `layout.js`, e outra na própria página). Agora `layout.js` dispara a consulta logo no carregamento e expõe a resposta em `window.ReConecta.sessaoResposta`; `painel.js` e `entrar.js` reaproveitam essa mesma resposta. Medido no servidor com o navegador abrindo `/entrar` e `/painel`: 1 `GET /reconecta/auth/me` por página (eram 2).
- **Cache de CNPJ**: `cnpj_service.py` guarda o resultado da consulta à Receita por 10 minutos (`CACHE_TTL = 600`). A verificação ao digitar o CNPJ e a nova verificação no envio do cadastro usam o mesmo resultado, sem uma segunda chamada externa. Cada fonte externa tem timeout de 8 s e há fontes alternativas.
- **Edição de dados envia só o que mudou**: o formulário "Seus dados" compara com o valor atual e não faz requisição quando nada mudou.
- **Lista pública paginada**: a Home pede só a primeira página (8 pedidos) em vez de todos os pedidos abertos.

## Organização das respostas

- Erros sempre no formato `{"codigo", "mensagem"}`, com `campos` (erro por campo) em validação e `motivos` em recusas de regra de negócio (CNPJ inapto, doação recusada). Os códigos HTTP seguem o significado: 400 dado inválido, 401 sem sessão, 403 sem permissão, 404 inexistente, 409 conflito/duplicado, 413 arquivo grande, 422 regra de negócio, 429 limite de tentativas, 503 serviço externo indisponível.
- Paginação informada em cabeçalhos (`X-Total-Count`, `X-Pagina`, `X-Por-Pagina`) para manter o corpo como lista, compatível com quem já consumia a API.
- Datas com fuso explícito (ISO 8601 com `-03:00`), CPF mascarado e nenhum dado de contato em respostas públicas.
- Modelos de entrada e saída documentados no Swagger (`/swagger` e `swagger.json`).
