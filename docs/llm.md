# IA local no ReConecta

## Resumo para a apresentação (critério 8 do CP2)

| O que o critério pede explicar | Resposta |
|---|---|
| Modelo ou serviço utilizado | **Ollama** (código aberto, gratuito) rodando no próprio computador, com o modelo aberto **`qwen2.5:3b`**. Sem API paga, sem chave, sem nuvem. Detalhes em "Serviço e finalidade". |
| Finalidade da LLM | (1) **Interpretar o pedido** escrito em texto livre pela empresa e transformar em itens estruturados (nome, categoria, quantidade, unidade, prazo) — classificação de informações e análise textual. (2) **Resumir o dashboard** e sugerir **recomendações** — interpretação de dados, geração de relatório e apoio à tomada de decisão. |
| Dados enviados | (1) Só o texto que a empresa digitou, com e-mail, telefone, CPF e CNPJ removidos, mais as listas fixas de categorias e unidades e a data de hoje. (2) Só números agregados do dashboard (contadores, percentual, totais por categoria, contagem de alertas). Nenhum nome, documento, contato ou endereço. Ver "O que a aplicação envia e recebe". |
| Resposta obtida | JSON com `itens`, `receber_ate` e `observacoes` (pedido) ou `resumo` e `recomendacoes` (dashboard), sempre com `fonte` (`llm` ou `regras`) e `modelo`. Exemplos reais abaixo. |
| Como a resposta é usada | (1) **Pré-preenche** o formulário "Publicar pedido de doação" no painel; a empresa revisa e só então publica — o endpoint de IA não grava nada e o POST de publicação valida tudo de novo. (2) Mostra o resumo e as recomendações no cartão "Resumo com IA" do dashboard, com o selo da origem. |
| Limitações identificadas | Ver "Limitações identificadas". |
| Cuidados com segurança e dados sensíveis | Ver "Segurança e dados sensíveis". |

## Serviço e finalidade

O recurso usa **Ollama rodando no próprio computador**, com o modelo `qwen2.5:3b`. Não usa API paga, conta de nuvem, chave, OpenAI, Anthropic, Gemini, Groq ou Hugging Face. O backend chama somente `POST http://localhost:11434/api/chat`, via `requests`, com `stream: false`, temperatura `0.2` e tempo limite. A interpretação de pedidos envia um JSON Schema em `format` para exigir a lista `itens` e valores das listas fixas; o resumo usa `format: "json"`. A implementação aceita `OLLAMA_URL` apenas com HTTP em `localhost`, `127.0.0.1` ou `::1`, e `OLLAMA_MODELO` apenas como `qwen2.5:3b`; modelos `:cloud` não são chamados. Redirecionamentos e proxies do ambiente são desativados. Se o serviço não responder, responder mal ou devolver dados fora do contrato, regras locais geram a resposta com `fonte: "regras"` e `modelo: null`.

A página oficial do [modelo `qwen2.5:3b`](https://ollama.com/library/qwen2.5%3A3b) informa **Qwen Research License** para a variante 3B. A menção a Apache 2.0 no brief do CP2 não se aplica a essa variante. O modelo é baixado e executado localmente sem API paga; verifique os termos da licença antes de qualquer uso além do contexto acadêmico.

## O que a aplicação envia e recebe

`POST /reconecta/ia/interpretar-pedido` exige sessão de empresa. Recebe `{"texto":"Precisamos de 100 caixas de leite e 100 pães até sexta-feira"}` com 5 a 600 caracteres. Ao Ollama vai apenas esse texto, depois da remoção básica de padrões de email, telefone, CPF e CNPJ, junto com instruções e as listas fixas de categorias e unidades. Não vão nome, documento, email, endereço nem sessão do cadastro. A saída é validada e limitada a dez itens:

```json
{"itens":[{"nome":"leite","categoria":"Laticínios","quantidade":100.0,"unidade_medida":"caixa"}],"receber_ate":"2026-10-09","observacoes":"Revise antes de publicar.","fonte":"llm","modelo":"qwen2.5:3b"}
```

O prompt informa a data e o dia da semana atuais e mostra um exemplo com dois itens. Categorias desconhecidas são inferidas do nome do alimento ou viram `Outros`; unidades comuns no plural são normalizadas. Uma resposta plana de um único item também é aceita para tolerar versões pequenas do modelo. Os itens devolvidos são confrontados com quantidades, nomes e unidades explícitos no texto; um item omitido, como o segundo alimento em “100 caixas de leite e 100 pães”, é recuperado por regras. O prazo explícito do texto prevalece sobre a data calculada pelo modelo, inclusive quando ela é futura, mas corresponde ao dia errado. Itens sem nome, quantidade positiva ou unidade permitida são descartados. Se nada válido restar, o extrator por regras interpreta quantidade, unidade, alimento e prazo e a fonte passa a ser `regras`. A data sugerida é somente `YYYY-MM-DD` ou `null`: a empresa deve informar e revisar a hora antes de publicar. O endpoint **não publica o pedido**; o formulário e o POST de publicação continuam validando todos os campos.

`POST /reconecta/ia/resumo-dashboard` é público e aceita no máximo **10 chamadas por minuto por IP** em cada processo da aplicação. Ele ignora o corpo do cliente e chama `montar_dashboard()` no servidor. O prompt contém apenas contadores, percentual, categoria com totais, total de doações nos últimos 30 dias e contagem de alertas por tipo. Nomes de empresas, endereços, itens, mensagens livres, IDs e doações individuais não entram no prompt. Retorna um resumo de 3 a 5 frases e recomendações em texto:

```json
{"resumo":"Há 2 pedidos abertos. Os itens atingiram 50% da meta. Foram registradas 3 doações nos últimos 30 dias.","recomendacoes":["Divulgue os pedidos com prazo próximo."],"fonte":"llm","modelo":"qwen2.5:3b","gerado_em":"2026-10-05T12:00:00"}
```

No fallback, o resumo tem três frases e recomendações determinísticas calculadas dos números; a origem aparece como `regras`. A interface deve mostrar o texto com `textContent`, nunca como HTML. O texto do modelo não é fonte de verdade para decidir a publicação ou alterar o banco.

## Instalação gratuita e local

1. Instale o Ollama para Windows pelo [site oficial](https://ollama.com/download/windows). A [documentação Windows](https://docs.ollama.com/windows) informa que o serviço fica em `http://localhost:11434` quando ativo.
2. No terminal interno, baixe o modelo uma vez: `ollama pull qwen2.5:3b`. Confira com `ollama list`. O download ocupa espaço em disco; a página do modelo informa cerca de 1,9 GB para a variante padrão.
3. Configure `.env` com `OLLAMA_URL=http://localhost:11434` e `OLLAMA_MODELO=qwen2.5:3b`; sem essas variáveis, esses valores já são o padrão. Não há variável de chave de API.
4. Inicie o ReConecta normalmente. Consulte `/reconecta/ia/interpretar-pedido` com sessão de empresa ou `/reconecta/ia/resumo-dashboard` sem sessão. A [referência oficial de `/api/chat`](https://docs.ollama.com/api/chat) documenta `messages`, `format`, `options` e `stream`.

O serviço funciona sem Ollama, com sugestões por regras. O primeiro uso do modelo pode demorar para carregá-lo; a chamada tem timeout de conexão de 2 s e de leitura de 90 s. O limite por IP é mantido em memória por processo: múltiplos workers não compartilham a contagem. Os padrões de remoção de identificadores não cobrem todos os formatos possíveis; evite escrever dados pessoais no texto livre. A interpretação de alimentos e datas relativas é heurística, e toda sugestão precisa da revisão da empresa.

## Limitações identificadas

- O `qwen2.5:3b` é um modelo pequeno: às vezes omite um item, devolve um objeto de um item só ou inventa datas. Por isso a saída passa por JSON Schema, validação contra as listas fixas, conferência com o texto original e, se necessário, recuperação por regras.
- Datas relativas ("sexta", "amanhã") e nomes de alimentos são interpretados de forma heurística; a hora do prazo sempre precisa ser informada/revisada pela empresa.
- O primeiro uso pode demorar enquanto o modelo carrega; em máquina sem GPU a resposta é mais lenta (timeout de 90 s).
- O Ollama precisa estar instalado e ativo no servidor; sem ele as funções continuam funcionando por regras automáticas, avisando `fonte: "regras"`.
- O limite de 10 chamadas por minuto do resumo fica na memória de cada processo.
- Licença do modelo: Qwen Research License — adequada ao uso acadêmico; revisar antes de qualquer uso comercial.

## Segurança e dados sensíveis

- **Local**: o modelo roda no próprio PC; nenhum dado sai para serviços externos. O backend só aceita `OLLAMA_URL` em `localhost`, ignora proxies e redirecionamentos e não chama modelos `:cloud`.
- **Mínimo de dados**: o texto do pedido passa por remoção de e-mail, telefone, CPF e CNPJ antes de ir ao modelo; o resumo usa só agregados calculados no servidor (o cliente não consegue injetar dados nele).
- **Acesso**: interpretar pedido exige sessão de empresa; o resumo tem limite de chamadas por IP.
- **Saída tratada como dado não confiável**: validada contra listas e tamanhos, exibida com `textContent` (nunca como HTML) e nunca grava no banco nem decide publicação sozinha.
- **Transparência**: toda resposta informa se veio do modelo (`fonte: "llm"`, com o nome do modelo) ou das regras.
- **Sem segredos**: não há chave de API; nada sensível em variáveis da IA.
