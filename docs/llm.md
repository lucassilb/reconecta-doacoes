# LLM gratuita para interpretar alimentos e resumir o dashboard

## Serviço e finalidade

O backend tenta, nesta ordem, **Groq Free** (`openai/gpt-oss-20b` por padrão), **Ollama local** (`qwen2.5:3b`) e **regras + classificador treinado**. O Groq é opcional: sem `GROQ_API_KEY`, a aplicação não faz chamada externa de LLM. O Groq interpreta texto de pedidos e resume apenas indicadores agregados do dashboard; `conexao.casar`, classificador, risco de descarte e geolocalização mantêm suas implementações. A resposta inclui `fonte: "llm"` e `modelo: "groq:openai/gpt-oss-20b"` quando o Groq é aceito, `modelo: "qwen2.5:3b"` para Ollama, ou `fonte: "regras"` e `modelo: null`.

O endpoint oficial é `https://api.groq.com/openai/v1/chat/completions`. A requisição usa `response_format: json_schema` com `strict: true`, sem streaming ou ferramentas. O modelo pode ser alterado por `GROQ_MODEL` somente para `openai/gpt-oss-20b`, `openai/gpt-oss-120b` ou `qwen/qwen3.8-27b`, listados com saída strict e limites Free nas [documentações de saída estruturada](https://console.groq.com/docs/structured-outputs) e [cotas](https://console.groq.com/docs/rate-limits). Nenhum modelo pago ou fora dessa lista é chamado. A chave fica somente em variável de ambiente; no Render, `GROQ_API_KEY` é `sync: false` no Blueprint e deve ser preenchida no painel sem registrar valor no Git.

## Dados enviados e uso da resposta

`POST /reconecta/ia/interpretar-pedido` recebe texto de 5 a 600 caracteres de uma conta de organização e mantém o limite da rota de 10 chamadas por minuto por conta. Antes da chamada à LLM, `_sem_identificadores` remove padrões comuns de CPF, CNPJ, telefone e e-mail. Só o texto tratado, a data de hoje e as listas fixas de categorias e unidades seguem ao Groq. Nome da conta, documentos do cadastro, endereço, sessão e foto não entram no prompt. A saída é limitada a dez itens e passa por `_validar_pedido` e `_conferir_com_texto`; quantidades, unidades e prazo explícitos são conferidos com o texto. O resultado apenas pré-preenche o formulário. A organização revisa tudo e o POST de publicação valida novamente.

`POST /reconecta/ia/resumo-dashboard` é público e tem limite de 10 chamadas por minuto por IP. Ignora o corpo enviado pelo cliente. Sem parâmetro, chama `montar_dashboard()` sobre o banco configurado. Com `?modo=demonstracao`, usa o dashboard semeado no SQLite isolado em memória e responde com `modo: "demonstracao"`; o resumo da demonstração é guardado em memória por dia e processo, sem dispensar o limite por IP. `_dados_agregados` seleciona apenas contadores, totais por categoria e alertas por tipo. Nomes, endereços, itens individuais, identificadores e texto livre não seguem ao Groq. O resumo aceito tem 3 a 5 frases e 1 a 5 recomendações; a interface o exibe como texto, sem HTML. Se a saída for inválida, o Ollama local ou as regras assumem.

Groq é um **operador externo** desses dados tratados. As expressões de remoção não cobrem todos os formatos de dados pessoais; evite incluir contatos ou documentos no texto livre. A [política de privacidade](/privacidade) e [mapa LGPD](lgpd.md) informam o compartilhamento. O tráfego usa HTTPS e a chave não vai ao navegador, à resposta da API nem aos logs.

## Guardas de entrada e saída (NeMo Guardrails)

Antes de qualquer LLM, `guardas_ia.checar_entrada` recusa injeção de prompt/jailbreak e pedido fora do tema: a API responde `400 ENTRADA_RECUSADA` com a mensagem em `campos.texto`, sem gastar cota. Depois da validação de formato, `guardas_ia.checar_saida` descarta resposta com dado pessoal, link/HTML, trecho do prompt ou, no resumo, número que não veio dos agregados; aí entram Ollama ou regras. As regras estão em `guardrails/` (Colang do NVIDIA NeMo Guardrails), que o CI executa com o NeMo de verdade; a produção roda as mesmas ações sem a biblioteca, pelos números de memória em [seguranca.md](seguranca.md). Nenhuma rail chama a LLM.

## Limites, falhas e fallback

O Groq Free informa 30 requisições/minuto, 1.000/dia, 8 mil tokens/minuto e 200 mil/dia **por organização** para o modelo padrão. Cada processo reserva no máximo 25 requisições/minuto, 900/dia, 7.200 tokens estimados/minuto e 180 mil/dia. Vários workers não compartilham a guarda local; os limites do Groq continuam sendo a barreira da organização. `429` abre um disjuntor em memória pelo `retry-after` (ou 60 s), sem retry na requisição. Após três falhas HTTP, de rede, de JSON ou de conteúdo, o disjuntor abre por 60 s. `401/403` geram log de status sem chave, prompt, corpo da resposta ou exceção. Timeout do Groq: 2 s de conexão e 8 s de leitura. Falhas e cota local fazem a execução seguir para Ollama quando disponível e depois para regras. O Ollama mantém URL local restrita, sem redirecionamento/proxy, e timeout próprio.

## Configuração e avaliação

- Render/produção: cadastrar `GROQ_API_KEY` da conta **Groq Free**, sem cartão nem plano pago. O Blueprint deixa o valor ausente (`sync: false`); sem ele, as funções continuam locais.
- Local: opcionalmente definir `GROQ_API_KEY` no ambiente. `GROQ_MODEL` usa `openai/gpt-oss-20b` por padrão. `OLLAMA_URL` e `OLLAMA_MODELO` continuam válidos como segundo provedor.
- Avaliação: `python scripts/avaliar_groq.py` mede pedidos inteiros corretos no conjunto de 66 casos em `data/pedidos_avaliacao.jsonl`. Se existir `C:/Users/lucas/relatorios/reconecta-2026-10-14/r17/groq.key`, lê a chave sem exibi-la e espaça chamadas reais em pelo menos 12,2 s; também aceita `--key-file`. Sem chave, mede regras/classificador e marca o Groq como **não avaliado**. Resultado em `modelo/avaliacao_groq.json`.

Na execução com chave Free em 2026-10-14: regras **25/66**, classificador + regras **48/66** e fluxo Groq → Ollama → regras **51/66** pedidos inteiros. Foram feitas 66 chamadas ao Groq; **44** respostas dele passaram pela validação, **11** respostas finais vieram do Ollama local e **11** das regras. A avaliação não separa quantos dos 51 acertos foram produzidos por cada fonte. O Ollama tem registro anterior de **50/66** (2026-10-13), sem nova avaliação isolada nesta rodada. Esses 66 casos sintéticos são um gabarito de regressão, não uma estimativa de desempenho no público.
