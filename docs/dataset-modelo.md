# Dataset estruturado e modelo local

O ReConecta tem um dataset próprio de alimentos e um classificador treinado nele, que roda dentro da aplicação sem serviço externo, sem GPU e sem dependência nova. Ele escolhe a **categoria** de cada item quando a empresa usa "Preencher com IA" no pedido. Custo zero: Python puro e arquivos de texto.

| O que | Onde |
|---|---|
| Dataset de alimentos (925 linhas) | [`data/alimentos.csv`](../data/alimentos.csv) |
| Pedidos de avaliação com gabarito (66) | [`data/pedidos_avaliacao.jsonl`](../data/pedidos_avaliacao.jsonl) |
| Ofertas e pedidos com destino esperado (86) | [`data/ofertas_avaliacao.jsonl`](../data/ofertas_avaliacao.jsonl) |
| Dicionário de dados e construção | [`data/README.md`](../data/README.md) |
| Código do classificador | [`classificador.py`](../classificador.py) |
| Modelo treinado (JSON, 115 KB) | [`modelo/classificador_categorias.json`](../modelo/classificador_categorias.json) |
| Métricas completas do treino | [`modelo/metricas.json`](../modelo/metricas.json) |
| Treino | `python scripts/treinar_modelo.py` |
| Demonstração no terminal | `python scripts/classificar.py "leite integral 1L"` |
| Comparação com regras e LLM | `python scripts/avaliar_modelos.py` → [avaliacao-modelos.md](avaliacao-modelos.md) |
| Ciclo automático e limiares | `python scripts/ciclo_ia.py` → [`modelo/metricas.json`](../modelo/metricas.json) |

## Validação da inteligência central e ciclo automático

| Critério | Como validar e resultado local de 2026-10-14 | Limiar do CI |
|---|---|---|
| Categoria do alimento | `python scripts/ciclo_ia.py` treina com semente 42 em 740 das 925 linhas de `data/alimentos.csv` e avalia nas 185 separadas: **144/185 (77,84%)**. O teste não participa da escolha de configuração ou limiar do classificador. | Acurácia ≥ **75%**. |
| Destino recomendado | `python scripts/avaliar_conexao.py` roda `conexao.casar` em 86 ofertas com pedidos abertos rotulados manualmente: 64 têm destino e 22 não. **Top-1: 57/64 (89,06%); top-3: 57/64 (89,06%)**. O denominador é só o conjunto com destino. | Top-1 e top-3 ≥ **85%**. |
| Sem sugestão correta | Nos 22 casos sem pedido que receba o alimento e a unidade oferecidos, `casar` retornou vazio em **22/22 (100%)**. O arquivo [`modelo/avaliacao_conexao.json`](../modelo/avaliacao_conexao.json) inclui os erros por caso. | Taxa ≥ **95%**. |
| Automação | `scripts/ciclo_ia.py` grava o modelo e `modelo/metricas.json` com data, versão, métricas e tamanhos; lê os mínimos em [`modelo/limiares.json`](../modelo/limiares.json) e sai com erro se algum cair. O job `ia` de [CI](../.github/workflows/ci.yml) publica as métricas como artefato e é exigido por `deploy`. | Todos os mínimos acima. |

O gabarito da conexão foi escrito antes de rodar a recomendação: o destino correto exige o mesmo alimento (ou equivalência comum), unidade compatível e quantidade ainda pendente; havendo mais de um destino, prioriza atendimento de mais itens, proximidade por UF e prazo. Os 86 casos incluem oito categorias, várias UFs, restrições alimentares, ofertas com dois itens e seis novos casos de variação do nome de pão, inclusive um sem destino. No mesmo conjunto ampliado, antes da correção, top-1 e top-3 foram **53/64 (82,81%)** e a rejeição **22/22 (100%)**. Sete equivalências de nomes regionais ou grafias continuam sem sugestão (por exemplo, “mandioca”/“aipim”); elas permanecem no relatório. É um conjunto sintético de regressão, não uma estimativa de acerto em uso real. O ciclo é local, sem Ollama e sem serviço pago.

## Dataset

`data/alimentos.csv` tem 925 nomes de alimentos escritos como uma empresa digitaria num pedido, cada um com a categoria (uma das 8 da aplicação), a unidade sugerida e a origem da grafia. `data/pedidos_avaliacao.jsonl` tem 66 pedidos em texto livre, de fáceis a difíceis, com o gabarito de itens e prazo.

Os dois são **sintéticos e curados à mão para o projeto**. Não há dado coletado de usuários nem dado pessoal. O dicionário de dados, os critérios de categoria, a distribuição e a divisão treino/teste estão em [`data/README.md`](../data/README.md).

## Modelo

**Naive Bayes multinomial**, implementado em Python puro em `classificador.py` (cerca de 150 linhas, só biblioteca padrão).

- **Entrada**: o nome do alimento. O texto vai para minúsculas, perde os acentos e tem os dígitos trocados por `0` ("5kg" e "1kg" viram o mesmo padrão).
- **Atributos**: n-gramas de 2 a 4 caracteres de cada palavra, com marca de início e fim; as palavras inteiras; e a primeira palavra, que costuma ser o alimento em si ("molho de tomate" é molho, não tomate) e por isso conta 4 vezes.
- **Saída**: `classificar(texto) -> (categoria, confiança)`. A confiança é a softmax da média do log-verossimilhança por atributo: fica entre 0 e 1 e serve para comparar com o limiar, mas não é probabilidade calibrada. Texto só com números ou símbolos devolve `(None, 0.0)`.
- **Arquivo do modelo**: JSON com as contagens por atributo e categoria, o limiar e os metadados (data, semente, tamanhos, métricas). **Não usa `pickle` nem `joblib`**: carregar o modelo é ler texto, sem executar código, e o mesmo arquivo serve no Python 3.14 local e na imagem Docker com Python 3.12.

### Treino

`python scripts/treinar_modelo.py` faz tudo em poucos segundos e sempre dá o mesmo resultado (semente 42):

1. Divide o dataset de forma estratificada: 740 linhas de treino e 185 de teste.
2. Escolhe a configuração (tamanho dos n-gramas, peso da primeira palavra e suavização) por validação cruzada de 5 dobras **só no treino**, numa grade de 32 combinações. Escolhida: n-gramas de 2 a 4, primeira palavra com peso 4, suavização 0,3.
3. Escolhe o **limiar de confiança** com as previsões fora da dobra: o valor que dá a maior acurácia para o conjunto "classificador se confiante, senão palavras-chave". Escolhido: **0,15**.
4. Avalia uma única vez no teste, com o modelo treinado só no treino.
5. Treina o modelo final com as 925 linhas e grava o JSON.

### Métricas

Execução de 2026-10-13. Números completos em `modelo/metricas.json`.

| Medida | Classificador | Regra de palavras-chave (antes) |
|---|---|---|
| Acurácia no teste (185 linhas) | **77,8%** | 40,0% |
| F1 macro no teste | **0,78** | 0,45 |
| Acurácia em validação cruzada (5 dobras, 925 linhas) | **81,2% ± 1,7** | — |

A validação cruzada por dobra deu 78,3%, 81,4%, 81,6%, 81,3% e 83,4%.

Por categoria, no teste:

| Categoria | Precisão | Recall | F1 | Linhas |
|---|---|---|---|---|
| Hortifrúti | 0,88 | 0,79 | 0,83 | 28 |
| Padaria | 0,93 | 0,64 | 0,76 | 22 |
| Laticínios | 0,90 | 0,90 | 0,90 | 21 |
| Carnes e peixes | 0,83 | 0,87 | 0,85 | 23 |
| Grãos e cereais | 0,67 | 0,73 | 0,70 | 22 |
| Refeições prontas | 0,56 | 0,82 | 0,67 | 22 |
| Bebidas não alcoólicas | 0,79 | 0,90 | 0,84 | 21 |
| Outros | 0,80 | 0,62 | 0,70 | 26 |

Matriz de confusão no teste (linha = categoria real, coluna = prevista):

| Real \ Previsto | Hort. | Pad. | Lat. | Carnes | Grãos | Refeições | Bebidas | Outros |
|---|---|---|---|---|---|---|---|---|
| Hortifrúti | **22** | 0 | 0 | 0 | 0 | 1 | 2 | 3 |
| Padaria | 0 | **14** | 0 | 0 | 4 | 3 | 1 | 0 |
| Laticínios | 0 | 0 | **19** | 1 | 0 | 1 | 0 | 0 |
| Carnes e peixes | 1 | 0 | 0 | **20** | 0 | 1 | 0 | 1 |
| Grãos e cereais | 1 | 1 | 0 | 1 | **16** | 3 | 0 | 0 |
| Refeições prontas | 0 | 0 | 0 | 2 | 0 | **18** | 2 | 0 |
| Bebidas não alcoólicas | 0 | 0 | 0 | 0 | 1 | 1 | **19** | 0 |
| Outros | 1 | 0 | 2 | 0 | 3 | 4 | 0 | **16** |

A regra de palavras-chave acerta quando a palavra está na lista dela (precisão de 0,75 a 1,00 em seis das sete categorias com regra), mas só conhece cerca de 40 palavras: o recall fica entre 0,11 e 0,52 e o resto cai em "Outros" (precisão 0,17). Ela também erra por construção casos como "pão de queijo" (Laticínios, por causa de "queijo") e "molho de tomate" (Hortifrúti).

Os 41 erros do classificador no teste são quase todos alimentos cuja palavra principal não aparece no treino ("kiwi", "avocado", "sequilhos") ou que ficam na fronteira entre categorias ("broa de milho" → Grãos, "massa de pizza" → Refeições prontas, "laranjas" → Bebidas, por causa de "suco de laranja").

### Limiar

| Limiar | Itens que o classificador decide | Acerto nesses itens | Acurácia do conjunto classificador + regras |
|---|---|---|---|
| 0,15 (escolhido) | 100% | 78,2% | 78,2% |
| 0,20 | 87,2% | 84,0% | 77,7% |
| 0,25 | 66,8% | 92,5% | 73,0% |
| 0,30 | 44,9% | 97,0% | 63,9% |

Valores medidos fora da dobra, no treino. Subir o limiar deixa o classificador mais certeiro nos itens que decide, mas devolve mais itens à regra de palavras-chave, que acerta menos. Por isso o melhor conjunto é o de limiar baixo: na prática o classificador decide quase tudo e a regra fica como rede de segurança para quando o modelo não opina ou o arquivo do modelo não existe.

## Uso na aplicação

Em `llm_service.py`, a função `_categoria_item(nome)` decide a categoria nesta ordem:

1. **classificador treinado**, se a confiança for igual ou maior que o limiar;
2. senão, a **regra de palavras-chave** (`_categoria`);
3. senão, **"Outros"**.

Ela é usada em dois pontos de `POST /reconecta/ia/interpretar-pedido`:

- quando a LLM devolve uma categoria fora da lista;
- quando a resposta vem das regras, com o Ollama desligado ou com a saída da LLM rejeitada. É o caso da nuvem: o plano gratuito do Render não roda o Ollama, então lá a categoria vem sempre do classificador.

O contrato da API não mudou: mesmos campos, e `fonte` continua `"llm"` ou `"regras"`. O painel não mudou. A empresa sempre revisa os itens antes de publicar, e o POST de publicação valida tudo de novo. Se o arquivo do modelo faltar ou estiver inválido, a aplicação segue só com as palavras-chave, sem erro.

Na mesma rodada as regras de extração ganharam duas correções, achadas pela avaliação: vírgula decimal ("2,5 kg" virava 5 kg) e frase antes do pedido ("Bom dia! Precisamos de…" perdia o primeiro item).

### Variáveis e limites da IA

- `OLLAMA_PERMITIR_DOCKER=1`: no Docker Compose o Ollama fica em outro contêiner. Com essa variável o backend aceita também, e somente, o host `ollama` (`OLLAMA_URL=http://ollama:11434`). Continuam valendo: só HTTP, porta explícita, sem usuário na URL, sem redirecionamento e sem proxy. Sem a variável, só `localhost`, `127.0.0.1` e `::1`.
- `POST /reconecta/ia/interpretar-pedido` aceita no máximo 10 chamadas por minuto por empresa logada (429 `MUITAS_TENTATIVAS`, `Retry-After: 60`). A contagem fica na memória de cada processo.

## Comparação com as regras e com a LLM

`python scripts/avaliar_modelos.py` roda os 66 pedidos de `data/pedidos_avaliacao.jsonl` contra as regras, o classificador + regras e a LLM local, e grava [avaliacao-modelos.md](avaliacao-modelos.md) com os números da execução, a latência e exemplos de erro.

Execução de 2026-10-13, 66 pedidos e 130 itens:

| Medida | (a) Regras | (b) Classificador + regras | (c1) LLM, saída só validada | (c2) LLM na aplicação |
|---|---|---|---|---|
| Itens encontrados | 116/130 (89,2%) | 116/130 (89,2%) | 128/130 (98,5%) | 122/130 (93,8%) |
| Categoria certa | 73/130 (56,2%) | **110/130 (84,6%)** | 97/130 (74,6%) | 115/130 (88,5%) |
| Quantidade certa | 110/130 (84,6%) | 110/130 (84,6%) | 123/130 (94,6%) | 115/130 (88,5%) |
| Unidade certa | 113/130 (86,9%) | 113/130 (86,9%) | 121/130 (93,1%) | 119/130 (91,5%) |
| Prazo certo | 62/66 (93,9%) | 62/66 (93,9%) | 44/66 (66,7%) | 62/66 (93,9%) |
| Pedido inteiro certo | 25/66 (37,9%) | **48/66 (72,7%)** | 22/66 (33,3%) | 50/66 (75,8%) |
| Latência média | menos de 1 ms | menos de 1 ms | 3,6 s | 3,6 s |

O que os números mostram:

- **O classificador é o que mais muda o resultado sem a LLM**: a categoria certa sobe de 56% para 85% dos itens e o pedido inteiro certo quase dobra, de 25 para 48 em 66, sem custo de tempo. É esse o caminho usado na nuvem, onde não há Ollama.
- **A LLM sozinha encontra mais itens** (128 de 130) e entende números por extenso, mas erra prazo em um terço dos pedidos e troca quantidades ("80 marmitas" virou 1). Por isso a aplicação não usa a saída dela direto.
- **O conjunto completo (c2) é o melhor**: 50 de 66 pedidos inteiros certos. Em 54 dos 66 a resposta saiu com `fonte: "llm"`; nos outros 12 a saída da LLM foi rejeitada na conferência e a resposta veio de (b).
- **Fáceis e médios ficam resolvidos** com (b): 20 de 20 e 21 de 22. Os difíceis continuam difíceis para todos: 7 de 24 com (b) e 9 de 24 com (c2). Formatos como "Arroz: 50 kg" e "Leite (100 caixas)" não são entendidos pelas regras.
- Um erro do classificador que sobrou: "leite de coco" sai como Laticínios, porque a primeira palavra pesa mais.

## Limitações

- **Vocabulário**: o modelo conhece 254 alimentos e suas grafias. Alimento com nome que não se parece com nenhum deles tende a ser classificado errado, e com confiança parecida com a dos acertos.
- **Tamanho do teste**: 185 linhas. A diferença para a regra antiga (38 pontos) é grande, mas diferenças de 1 ou 2 pontos entre configurações não são confiáveis.
- **Dados sintéticos**: as grafias imitam pedidos, mas não vêm de pedidos reais. O desempenho com texto de usuários pode ser diferente.
- **Escolhas feitas olhando os resultados**: o atributo "primeira palavra" entrou depois que a primeira avaliação dos pedidos mostrou "tomate" classificado como "Outros". O conjunto de pedidos, portanto, não é totalmente independente do desenho do modelo.
- **Confiança não calibrada**: o número serve para o limiar, não como probabilidade.
- **Só categoria**: quantidade, unidade e prazo continuam vindo das regras ou da LLM.
- **Fronteiras**: várias categorias dependem de convenção (ovos em "Carnes e peixes", farinhas em "Grãos e cereais"). As convenções estão em `data/README.md`; mudar uma delas exige ajustar o dataset e treinar de novo.

## Como refazer

```bash
python data/gerar_dataset.py        # refaz data/alimentos.csv a partir da lista curada
python scripts/treinar_modelo.py    # treina, avalia e grava modelo/*.json
python scripts/classificar.py "pao de queijo" "kiwi"
python scripts/avaliar_modelos.py   # precisa do Ollama com qwen2.5:3b; use --sem-llm sem ele
python -m pytest tests/test_classificador.py tests/test_ia.py -q
```

O teste `test_treino_e_reprodutivel_e_o_modelo_do_repositorio_esta_em_dia` falha se o dataset ou o treino mudarem sem o modelo ser treinado de novo.

## Sugerir destino (IA de conexão)

O classificador treinado também alimenta `POST /reconecta/ia/sugerir-destino`: o texto do
que sobrou vira itens pelo pipeline de sempre (LLM → classificador → regras) e a função
pura `conexao.casar` pontua os pedidos abertos que combinam — categoria (do classificador
quando a LLM não acerta), nome parecido, quanto falta, prazo e UF. Os dados usados são só
os campos públicos do pedido; o resultado é recomendação explicável (`motivos`), e quem
decide é a pessoa. Detalhes em [llm.md](llm.md#sugestão-de-destino-post-reconecta-ia-sugerir-destino)
e no código `conexao.py`.

## Risco de descarte e prioridade dos excedentes

`data/lotes_descarte.csv` contém **3.200 lotes simulados**, gerados por
`python scripts/treinar_risco.py --gerar-dados` com semente 1402. Cada linha tem
categoria, perecibilidade, dias até a validade, quantidade em kg, temperatura,
armazenamento, dia e hora de publicação, UF, distância informada até a ONG mais
próxima e o rótulo `descartado`. O rótulo é sorteado por uma regra declarada no
gerador: validade curta, perecibilidade, temperatura elevada, volume, distância,
fim de semana e horário noturno aumentam a chance simulada de não retirada.
**Essas taxas são premissas didáticas, não foram estimadas de perdas reais.** A
UF está no conjunto para documentar a abrangência, mas não é um atributo do
modelo: sem evidência de campo, atribuir risco direto a um estado seria indevido.
Temperatura e distância podem faltar; o modelo recebe marcadores explícitos de
ausência e não inventa uma medição.

`scripts/treinar_risco.py` lê o CSV com pandas e compara regressão logística e
floresta aleatória do scikit-learn em cinco dobras estratificadas somente no
treino (2.560 linhas). Seleciona pela média de F1, confere uma vez no teste
separado (640 linhas), refaz o ajuste com todos os lotes e exporta
`modelo/risco_descarte.json`, sem pickle. A API usa `risco_descarte.py` em Python
puro; pandas e scikit-learn entram apenas em `requirements-dev.txt` e no job
`ia` do CI, fora da imagem de produção. As versões de treino estão fixadas em
[pandas 3.0.6](https://pypi.org/project/pandas/3.0.6/) e
[scikit-learn 1.9.1](https://pypi.org/project/scikit-learn/1.9.1/).

| Medida no teste simulado | Resultado | Mínimo no CI |
|---|---:|---:|
| Acurácia | 0,6750 | 0,64 |
| Precisão | 0,5889 | — |
| Recall | 0,4417 | — |
| F1 | 0,5048 | 0,47 |
| ROC-AUC | 0,7015 | 0,67 |

A matriz de confusão (linhas reais 0/1, colunas previstas 0/1) é
`[[326, 74], [134, 106]]`. A regressão logística venceu a validação cruzada
por F1 (0,5565 contra 0,5413 da floresta). O modelo avaliado no teste foi
ajustado só no treino; o JSON servido é reajustado depois com as 3.200 linhas.
Esses números medem a recuperação da própria regra sintética. Não comprovam
acurácia de descarte na operação e não autorizam descartar ou aceitar alimentos
automaticamente.

`POST /reconecta/ia/risco-descarte` aceita um lote sem dados pessoais e devolve
probabilidade estimada, nível `alto`/`medio`/`baixo`, sinais observáveis e o aviso
de simulação. A lista pública `GET /reconecta/excedentes` ordena ofertas pela
probabilidade antes da paginação e expõe `prioridade.selo = "Prioridade alta"`
quando o nível é alto. Só categoria, validade, peso convertido e horário são
conhecidos para uma oferta publicada; temperatura, armazenamento e distância
ficam marcados como não informados. Os motivos descrevem sinais do lote, não
explicações causais da previsão. A escolha de reserva continua humana.

No mesmo teste independente de 185 nomes de alimentos, TF-IDF de caracteres
com regressão logística do scikit-learn acertou **0,7459** (F1 macro 0,7470),
contra **0,7784** (F1 macro 0,7807) do Naive Bayes existente. Por isso o
classificador atual permaneceu em produção. A acurácia cruzada do TF-IDF no
treino foi 0,7649; o resultado da comparação fica em
`modelo/metricas.json → comparacao_classificador`. Se o TF-IDF superar o
Naive Bayes em uma futura atualização do dataset, o ciclo falha até a adoção
explícita de um artefato leve e compatível com a API.

Para reproduzir: instale `requirements.txt` e `requirements-dev.txt`, rode
`python scripts/treinar_risco.py --gerar-dados` e `python scripts/ciclo_ia.py`.
O ciclo grava as métricas de descarte em `modelo/metricas.json → risco_descarte`
e falha se acurácia, F1 ou AUC caírem abaixo dos limites versionados em
`modelo/limiares.json`. Testes em `tests/test_risco_descarte.py` conferem
reprodutibilidade, equivalência de inferência com scikit-learn, API e ordenação.
