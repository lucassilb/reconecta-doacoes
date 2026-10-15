# Segurança — rodada 18 (SAST, DAST, IAST, SCA, guardas da IA e log mínimo)

Cada frente mantém só a sua seção.

## Frente B — DAST, IAST e autorização por objeto
### DAST: OWASP ZAP

Ferramenta: OWASP ZAP **2.17.0**, imagem oficial `ghcr.io/zaproxy/zaproxy:stable`. Comando: `python scripts/dast.py`. O script cria um projeto Compose exclusivo na porta **127.0.0.1:5005**, com SQLite em `/tmp` do contêiner, chave de sessão fictícia e Groq desativado. Ele confirma `/reconecta/saude`, semeia contas fictícias de doador, empresa de alimentos e ONG, testa cada cookie em `/reconecta/auth/me`, executa baseline passivo e quatro API scans ativos a partir de recortes do `swagger.json`, e encerra somente esse projeto Compose. Os recortes incluem GETs públicos e de cada papel, mais POSTs de login/IA, publicação de excedente pelo doador, publicação de pedido pela empresa e marcação de notificações pela ONG. Nenhuma varredura toca o site público, o banco configurado, Supabase ou Groq. O relatório versionado é [`relatorios/seguranca/zap.json`](../relatorios/seguranca/zap.json): só IDs, nomes, severidades, contagens e rotas normalizadas, sem cookies ou evidências brutas.

Na primeira execução local, houve **0 críticos, 0 altos, 0 médios, 12 baixos e 12 informativos** (contagem de tipos de alerta por varredura, não de URLs). ZAP apontou falta de COOP/CORP nas respostas e conteúdo de API potencialmente armazenável. `app.py` passou a enviar `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin` e `Cache-Control: no-store` nas rotas `/reconecta/`; o SSE também mantém `no-cache`. Os testes [`tests/test_dast_headers.py`](../tests/test_dast_headers.py) e [`tests/test_tempo_real.py`](../tests/test_tempo_real.py) verificam esses cabeçalhos e a CSP original. A varredura final, após essas correções, registrou **0 críticos, 0 altos, 0 médios, 6 baixos e 12 informativos**.

Os avisos baixos remanescentes foram: COEP ausente no HTML (1), um possível timestamp Unix (1) e tipo de conteúdo inesperado nos quatro API scans (4). COEP não foi ativado porque a página usa fontes Google e scripts do CDN; exigir incorporação entre origens sem adaptar esses recursos quebraria a interface. Os quatro alertas de tipo de conteúdo são **falsos positivos para a API**: as instâncias registradas são `/` ou caminhos fora do `swagger.json`, em que HTML é esperado; nenhuma aponta um endpoint da API definido no contrato. O timestamp fica como **risco baixo a investigar**: o relatório resumido preserva só a indicação de caminho fora do Swagger, insuficiente para concluir se é um dado sensível. O escopo automatizado cobre GETs e alguns POSTs; reserva, confirmação, exclusão, autorização por objeto e PostgreSQL exigem provas adicionais. Um DAST sem alerta alto não certifica ausência de vulnerabilidade.

### IAST: sensor de teste do projeto

Não há produto IAST comercial envolvido. O sensor leve [`iast_sensor.py`](../iast_sensor.py) liga somente com `RECONECTA_IAST=1` e combina `sys.addaudithook`, um listener `before_cursor_execute` do SQLAlchemy e valores textuais da requisição. Conta `exec`/`compile`, abertura de arquivos, processos, conexão de socket e SQL; gera achado **ALTA** quando observa processo iniciado, código ou SQL contendo valor integral da requisição, arquivo fora de `/app`/projeto, temporário e Python, ou conexão fora da allowlist local. Não bloqueia a requisição. O JSON por PID não contém texto livre, SQL, caminho, host externo, cookie ou identificador; [`scripts/resumo_iast.py`](../scripts/resumo_iast.py) agrega e falha se houver achado alto ou nenhum processo instrumentado.

Comando local: definir `DATABASE_URL=sqlite://`, `RECONECTA_IAST=1` e `RECONECTA_IAST_REPORT_DIR` para uma pasta temporária; executar `.venv/Scripts/python.exe -m pytest -q`; depois `python scripts/resumo_iast.py <pasta>`. O mesmo sensor fica ligado no app descartável durante o ZAP; com os POSTs adicionais observou **2.450 SQLs, 82 eventos de código dinâmico e zero achados**. Testes isolados em [`tests/test_iast.py`](../tests/test_iast.py) demonstram SQL parametrizado sem alerta e detecção de SQL literal, processo, código, arquivo e socket perigosos. Uma versão inicial do sensor marcou **56 falsos positivos** em `/reconecta/painel/doacoes`: o valor `unidade` da requisição era confundido com a coluna `unidade_medida` do SQL parametrizado. A correção exige o valor como token/literal inteiro, coberta por teste; a suíte final instrumentada passou com **340 testes, 5 pulados**, **736 instruções SQL observadas, 120 eventos de código dinâmico e zero achados**. Os resultados finais ficam em [`relatorios/seguranca/iast.json`](../relatorios/seguranca/iast.json) (suíte) e [`relatorios/seguranca/iast-dast.json`](../relatorios/seguranca/iast-dast.json) (ZAP).

Limites do sensor: taint textual simples, sem rastrear transformações/fluxo entre threads, sem binários ou JavaScript; o listener cobre o engine principal do SQLAlchemy, não todos os engines independentes. Os limites de pastas/hosts foram escolhidos para a prova local e o sensor fica desligado em produção.

### Gates no CI

Os jobs `dast` e `iast` em [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) são requisitos do job de deploy. `dast` repete Compose + ZAP e falha com alerta **ALTA/CRÍTICA**, erro de ferramenta ou achado alto do sensor durante o scan; `iast` executa a suíte instrumentada, a matriz BOLA/IDOR e falha em teste, desvio da matriz ou achado alto. Publicam `zap.json`, `iast-dast.json`, `iast.json` e `autorizacao.json` como artefatos. Os outros jobs de SAST, SCA e Docker continuam separados.

### Autorização por objeto (BOLA/IDOR)

`python scripts/avaliar_autorizacao.py` força `DATABASE_URL=sqlite://` antes de importar o app, desliga serviços externos e usa uma pasta temporária para a cópia local das fotos. Semeia **duas ONGs, duas empresas de alimentos e dois doadores fictícios**, cada um com objetos próprios. O script gera a matriz a partir das operações do `swagger.json`, classifica as **30 escritas** e falha se surgir uma rota de escrita sem cenário. Também exige prova dinâmica para as **16 leituras** com dados de sessão, campos administrativos ou detalhe que varia por autorização. O JSON versionado é [`relatorios/seguranca/autorizacao.json`](../relatorios/seguranca/autorizacao.json), sem cookies, tokens, fotos ou dados pessoais. Na execução local: **213 requisições, zero desvio de autorização** (rodada 19: a foto da validade da oferta, `GET /reconecta/excedentes/{id}/foto`, entrou com 14 GETs da foto e 14 detalhes conferindo `foto_url`: dono, as duas ONGs, empresa comum, outra pessoa e visitante, com a oferta aberta e com a reservada). Os testes em [`tests/test_autorizacao_objeto.py`](../tests/test_autorizacao_objeto.py) repetem a prova em outro processo e demonstram que uma nova escrita no Swagger bloqueia o gate.

A matriz verifica dono, outro titular do mesmo perfil, perfil diferente e ausência de sessão para reserva e cancelamento de excedente, retirada, confirmação ou recusa de entrega, pedido, foto e leituras privadas. Em rotas `/auth/me`, cada sessão é dona da própria conta: o teste compara o perfil/exportação e garante que editar ou excluir uma conta não muda a outra. Reserva de oferta livre e publicação são capacidades por **perfil**, portanto duas ONGs distintas podem reservar ofertas livres diferentes e dois doadores podem contribuir para um pedido. Os CRUDs legados usam `X-Admin-Token`, não posse do cookie: ONG, empresa, doador e visitante sem token recebem 401; token válido é exercitado em edição, criação e exclusão de pedido. GETs desses CRUDs são públicos com campos reduzidos, mas e-mail e telefone só aparecem com token. `/excedentes/reservas` devolve 200 com lista vazia para empresa comum; `/excedentes/rota` devolve 403 para ela. Nenhuma das duas respostas expõe a reserva da ONG.

Esta é uma prova dos fluxos e papéis semeados, não um modelo formal de autorização. As escritas públicas de cadastro/login e IA agregada ficam classificadas no inventário; o ZAP e os testes funcionais cobrem suas validações. O script testa também a criação de contribuição com foto e a autorização da IA com resposta local simulada, sem enviar conteúdo a provedores externos.

## Frente C — NeMo Guardrails na IA e log mínimo

Data: 2026-10-14. Base: main `a0ba325`. Relatórios: [`relatorios/seguranca/nemo-guardrails.json`](../relatorios/seguranca/nemo-guardrails.json)
e [`relatorios/seguranca/log-minimo.json`](../relatorios/seguranca/log-minimo.json).

**NeMo protege a IA; os hooks protegem o código.** O NeMo Guardrails filtra o que entra
na LLM (Groq Free/Ollama) e o que sai dela, em tempo de execução. Os hooks de pre-commit
da Frente A (gitleaks, bandit, semgrep, pip-audit) verificam o código enquanto ele é
escrito. São camadas diferentes e uma não substitui a outra.

### Ferramentas e comandos

| Ferramenta | Versão | Comando |
|---|---|---|
| NVIDIA NeMo Guardrails (Apache-2.0, gratuito) | 0.24.1 | `pip install -r requirements-guardrails.txt && python scripts/relatorio_guardrails.py` |
| Testes das guardas (ataques reais em português) | pytest 9.0.3 | `RECONECTA_NEMO=1 python -m pytest tests/test_guardrails_ia.py` |
| Captura de logs em fluxo completo | — | `python scripts/relatorio_log_minimo.py` e `python -m pytest tests/test_log_minimo.py` |
| gunicorn real em Docker, limite de 512 MB | gunicorn 23.0.0, `python:3.12-slim` | prova em `relatorios/reconecta-2026-10-14/r18/claude4/prova_docker.sh` (fora do repositório) |

No CI, o job `guardrails` instala o NeMo, roda os dois arquivos de teste com
`RECONECTA_NEMO=1` (o NeMo executa as rails de verdade), gera os relatórios como
artefato e entra no `needs` do deploy.

### Como as guardas funcionam

- `guardrails/config.yml` + `guardrails/rails.co` (Colang 1.0): fluxo de entrada
  `reconecta verificar entrada` e de saída `reconecta verificar saida`. Os dois chamam
  ações (`guardrails/actions.py`) que delegam para `guardas_ia.py`. **Nenhum modelo está
  configurado no NeMo:** as rails são locais e determinísticas e fazem **0 chamadas à
  LLM**, então não gastam a cota do Groq Free. Não há self-check por LLM. Nos 53 casos do
  corpus e nos 925 nomes do dataset não houve caso em que ele fosse necessário.
- **Entrada** (`llm_service.interpretar_pedido`, usado pelo assistente e pelo painel):
  - injeção de prompt e jailbreak em português e inglês: ordem para ignorar
    instruções/regras/orientações, troca de papel ("você agora é", "aja como", "modo
    desenvolvedor", DAN), pedido do prompt do sistema, chaves e variáveis de ambiente,
    marcadores de turno (`SYSTEM:`, `<|im_start|>`, `[INST]`), JSON pronto com as chaves
    do esquema, base64;
  - normalização contra disfarce: acentos, leetspeak (`1gn0r3 as r3gr4s`), caracteres
    invisíveis e texto soletrado (`i g n o r e`);
  - fora do tema: pedido de tarefa alheia (poema, piada, código, tradução), assunto
    alheio sem alimento (política, investimento, remédio, invasão) ou texto sem nenhum
    alimento nem quantidade. O vocabulário vem de uma lista curada e das palavras do
    dataset do classificador (`data/alimentos.csv`).

  O texto recusado **não chega à LLM**. A API responde `400 ENTRADA_RECUSADA` com a
  mensagem em `campos.texto`, que o painel e o assistente já mostram no campo. As
  mensagens ficam no `rails.co` e são a mesma fonte para o NeMo e para a produção.
- **Saída** (pedido e resumo do dashboard): a resposta é descartada se tiver dado pessoal
  (e-mail, CPF, CNPJ, telefone, CEP, IP), link ou HTML, trecho do prompt do sistema, ou,
  no resumo, número que não veio dos agregados enviados. Nesse caso entram Ollama ou as
  regras. O formato continua validado por `_validar_pedido`/`_validar_resumo` e pelo
  esquema strict do Groq.

### Memória: NeMo na produção ou só no CI?

Medido com a imagem real (gunicorn, 2 workers gthread, `docker run --memory 512m`) após
o mesmo fluxo de cadastro, login e 12 chamadas ao assistente:

| Imagem | Tamanho | Memória do contêiner (cgroup) | RSS somado (master + 2 workers) |
|---|---|---|---|
| main `a0ba325` | 284 MB | 102 MiB | 210 MB |
| esta frente, guardas sem NeMo (produção) | 284 MB | 107 MiB | 215 MB |
| esta frente com NeMo carregado (`RECONECTA_NEMO=1`) | **641 MB** | **201 MiB** | **292 MB** |

Latência por verificação: **0,2 a 0,4 ms** no motor direto e **8 a 11 ms** no NeMo. Os vereditos
são idênticos (teste de paridade em `tests/test_guardrails_ia.py`).

**Decisão:** o NeMo caberia nos 512 MB do Render free (≈ 40% do limite), mas quase dobra
a memória do serviço (+95 MiB), soma 357 MB à imagem (o cold start do plano free fica
mais lento), adiciona cerca de 90 pacotes ao inventário de SCA (onnxruntime, fastembed,
aiohttp etc.) e é 50 vezes mais lento, sem mudar nenhum veredito. Por isso ele roda no
CI e nos testes, e a produção executa **as mesmas ações** de `guardas_ia.py` com as
mensagens lidas do mesmo `rails.co`. Para ligar o NeMo em produção, basta instalar
`requirements-guardrails.txt` e definir `RECONECTA_NEMO=1`; o código já suporta.

### Achados por severidade

| Severidade | Achado (main `a0ba325`) | Correção | Teste que falhava antes |
|---|---|---|---|
| Alta | Injeção de prompt chegava à LLM sem filtro (ex.: caso 58 do conjunto de avaliação, "Ignore as instruções anteriores…", era enviado ao Groq) | guarda de entrada recusa antes de qualquer LLM | `test_injecao_de_prompt_e_bloqueada` (27 ataques), `test_injecao_nao_chega_a_llm`, `test_api_recusa_injecao_e_fora_do_tema_com_mensagem_no_campo` |
| Alta | Erro do banco ia para o log com os valores: `IntegrityError … [parameters: ('<nome>', '<CPF>', '<e-mail>', '<telefone>' …)]` | `hide_parameters=True` no engine + máscara central | `test_fluxo_completo_nao_deixa_dado_pessoal_nos_logs` |
| Média | IP completo na auditoria (7 linhas no fluxo) e no access log do gunicorn (19 linhas), com query string (`?busca=<e-mail>&cep=…`), referer com e-mail, user-agent e CNPJ no caminho | IP truncado (/24 e /48), `gunicorn.conf.py` com `%(m)s %(U)s %(s)s %(b)s %(M)sms`, máscara central | `test_fluxo_completo…`, `test_access_log_do_gunicorn_sem_ip_query_referer_nem_agente`, `test_auditoria_trunca_ip` |
| Média | Mensagem de exceção com e-mail, CPF ou IP gravada inteira no traceback | fábrica de LogRecord (`registro.py`) mascara mensagem e traceback de qualquer logger | `test_mascara_vale_para_qualquer_logger_e_traceback` |
| Média | Resposta da LLM sem guarda de saída: telefone, e-mail, link ou trecho do prompt chegariam à tela; resumo com número inventado era aceito | guarda de saída e retorno ao Ollama/regras | `test_saida_com_dado_pessoal_link_ou_vazamento_e_descartada`, `test_saida_com_telefone_cai_nas_regras`, `test_resumo_com_numero_inventado_cai_nas_regras` |
| Média | Pedido fora do tema (poema, política, código) consumia a cota do Groq Free | guarda de entrada `fora_do_tema` | `test_fora_do_tema_e_bloqueado` (11 casos) |
| Média (achado no próprio NeMo) | Com o NeMo ligado, a biblioteca registra cada evento da conversa em INFO/DEBUG: um nome citado no pedido apareceu 16 vezes no log | logger `nemoguardrails` em WARNING ao carregar | `test_nemo_nao_escreve_o_texto_do_usuario_no_log` |
| Baixa | Bandit B613 (trojan source) no primeiro rascunho de `guardas_ia.py`: caracteres invisíveis literais numa regex | trocados por escapes `​…`; nenhum caractere invisível literal no código | Bandit sem achados nos arquivos da frente |

Antes × depois no mesmo fluxo de logs (cadastro, login errado e certo, oferta com
endereço, assistente com contato, erro interno e erro de banco): main `a0ba325` vazou
nome 1×, CPF 3×, e-mail 3×, telefone 1× e IP completo 7×; esta frente vazou **0**. No
gunicorn real em Docker: IP completo 19 → 0, e-mail 2 → 0, CEP 1 → 0, user-agent 16 → 0
e CNPJ 1 → 0.

Falsos positivos: nenhum achado de ferramenta foi descartado como falso positivo. Nas
guardas, a medida de falso positivo é sobre pedidos legítimos: 0 de 15 no corpus, 0 dos
65 pedidos legítimos do conjunto de avaliação e 4 de 925 nomes soltos do dataset (`cará`,
`PF`, `itens diversos`, `produtos diversos`, que passam quando vêm com quantidade).

### Riscos residuais

- As guardas de entrada são heurísticas. Um ataque parafraseado de forma nova ou em
  outro idioma pode passar. Mesmo assim, a saída continua presa ao esquema JSON strict,
  à conferência com o texto (`_conferir_com_texto`), à guarda de saída e à revisão humana
  antes de publicar. A LLM nunca grava no banco.
- O texto com quantidade e sem alimento conhecido ("3 caixas de bombril") passa como
  `duvida` e segue para a LLM. A saída continua validada.
- Nome, endereço e texto livre não têm formato fixo, e a máscara de log não os
  reconhece. A garantia é que nenhum log do projeto os inclui (provado pelo teste de
  fluxo completo); um log novo que os inclua passaria pela máscara sem ser pego.
- Os logs de borda do Render (IP e user-agent do proxy) estão fora do controle do
  aplicativo. A retenção é a do plano: 7 dias no Hobby.
- Com o NeMo, a guarda de saída informa só o motivo genérico `saida` no log.
