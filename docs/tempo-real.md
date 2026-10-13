# Tempo real, eventos e notificações

O ReConecta avisa na hora quando algo muda: pedido publicado, doação aceita ou entregue,
excedente publicado/reservado/retirado. Nenhum serviço externo, nenhuma chave — é
Server-Sent Events (SSE) no próprio Flask, com queda automática para consulta periódica.

## A fonte única: tabela `eventos`

Todo fato relevante vira uma linha em `eventos` (`eventos.py`):

| Coluna | Papel |
|---|---|
| `id` | Crescente; é também o cursor (`Last-Event-ID` / `desde`) |
| `tipo` | `pedido.publicado`, `doacao.aceita`, `doacao.entregue`, `doacao.nao_recebida`, `excedente.publicado`, `excedente.reservado`, `excedente.reserva_cancelada`, `excedente.retirado`, `excedente.cancelado` |
| `publico` | `1` = visível a todos; `0` = visível só ao destinatário |
| `dest_tipo`/`dest_id` | `("empresa", id)` ou `("doador", id)`; NULL na linha pública |
| `dados` | JSON em texto, **sem dado pessoal** (só ids e rótulos públicos) |
| `criado_em` | Data UTC (sem fuso), serializada com fuso de Brasília |

`emitir(tipo, dados, publico=True, destinatarios=())` grava **na mesma transação** de quem
chama — se o pedido falhar depois, o anúncio some junto. Um evento público gera uma linha
com `dest_*` NULL; cada destinatário gera uma linha privada.

A mesma tabela serve aos três consumidores: o fluxo ao vivo, as notificações e o histórico
(rastreabilidade — toda mudança de estado fica registrada).

## Rotas

| Rota | O que faz |
|---|---|
| `GET /reconecta/tempo-real` | Fluxo SSE (`text/event-stream`): eventos públicos + os do usuário logado. Aceita `Last-Event-ID` ou `?desde=` para retomar. Batimento `: batimento` a cada 15 s. Encerra aos 5 min (o navegador reconecta). Se houver 20 conexões abertas no processo, responde 503 `TEMPO_REAL_LOTADO` |
| `GET /reconecta/novidades?desde=<id>` | Os mesmos eventos em JSON `{"ultimo_id", "eventos":[...]}` (máx. 50). Sem `desde`, só devolve `ultimo_id` — usado na primeira carga e na queda do SSE |
| `GET /reconecta/notificacoes` | (logado) as 30 mais recentes destinadas ao usuário, cada uma com `lida` |
| `POST /reconecta/notificacoes/lidas` | (logado) `{"ate_id": n}` marca lidas até o id — guardado em `notificacao_leitura` (um id por usuário) |

Formato do evento (SSE `data:` e JSON): `{"id", "tipo", "criado_em", "dados"}`.

## Como funciona por dentro

- O handler SSE abre um gerador com `stream_with_context`: a cada ~2 s consulta
  `eventos` (`id > ultimo`, público ou destinado a mim) e chama `db.session.remove()` ao
  fim de cada consulta — a conexão do pool fica livre entre as leituras; 20 conexões SSE
  não prendem 20 conexões de banco.
- Sem nada novo por 15 s, envia `: batimento` (comentário SSE) — mantém proxies e o
  timeout de 90 s do gunicorn tranquilos.
- Servidor de produção: `gunicorn --worker-class gthread --threads 8` (Dockerfile), para
  conexões SSE longas sem bloquear o worker inteiro.
- O front (`layout.js`) abre `EventSource("/reconecta/tempo-real")`; se falhar ou receber
  503, consulta `/reconecta/novidades` a cada 10 s e retoma pelo último `id`.

## Limites conhecidos

- Contadores e conexões são por processo: com 2 workers do gunicorn, o teto efetivo é 40
  conexões SSE e os limites de chamada dividem-se entre eles; restart zera tudo (o
  `Last-Event-ID` garante que nenhum evento se perca, porque a fonte é a tabela).
- Eventos guardam `dados` pequenos e públicos; o detalhe continua vindo das rotas REST —
  o evento é o aviso, não o payload.
- O limite de conexões por processo (20) é uma defesa simples; o valor certo para
  produção depende do plano.
