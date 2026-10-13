<!-- Trecho da Frente C (rodada 10) para o README. Colar como seções; ajustar a numeração se preciso. -->

## Dataset estruturado

O projeto tem dois conjuntos de dados próprios em `data/`, **sintéticos e curados à mão** (nenhum dado coletado de usuários, nenhum dado pessoal):

| Arquivo | Conteúdo |
|---|---|
| [`data/alimentos.csv`](data/alimentos.csv) | 925 nomes de alimentos como uma empresa escreve num pedido ("leite integral 1L", "pao frances", "arroz tipo 1 5kg"), com `id`, `texto`, `categoria` (as 8 da aplicação), `unidade_sugerida` e `origem`. Sem duplicata, nem ignorando acento e caixa. |
| [`data/pedidos_avaliacao.jsonl`](data/pedidos_avaliacao.jsonl) | 66 pedidos em texto livre (20 fáceis, 22 médios, 24 difíceis) com o gabarito de itens e prazo: 130 itens. |
| [`data/README.md`](data/README.md) | Dicionário de dados, como foi construído, critérios de categoria, distribuição, divisão treino/teste e licença. |

Divisão treino/teste estratificada por categoria (740/185), com semente fixa. Para refazer o CSV: `python data/gerar_dataset.py`.

## Modelo funcional local

Além da LLM local (Ollama + `qwen2.5:3b`), o ReConecta tem um **modelo treinado no próprio dataset**: um classificador Naive Bayes multinomial que escolhe a categoria de cada item do pedido. É Python puro (só biblioteca padrão), roda dentro da aplicação em menos de 1 ms, não precisa de GPU nem de serviço externo e é salvo em JSON, sem `pickle`.

| Medida (execução de 2026-10-13) | Classificador treinado | Regra de palavras-chave anterior |
|---|---|---|
| Acurácia no teste (185 linhas) | **77,8%** | 40,0% |
| F1 macro no teste | **0,78** | 0,45 |
| Validação cruzada de 5 dobras (925 linhas) | **81,2% ± 1,7** | — |
| Categoria certa nos 130 itens dos pedidos de avaliação | **84,6%** | 56,2% |
| Pedidos inteiros certos, sem a LLM (66 pedidos) | **48** | 25 |

Com a LLM local ligada, o conjunto completo acerta 50 dos 66 pedidos inteiros, com 3,6 s de latência média por pedido. A comparação entre regras, classificador e LLM, com exemplos de erro, está em [docs/avaliacao-modelos.md](docs/avaliacao-modelos.md).

Uso na aplicação: em `POST /reconecta/ia/interpretar-pedido`, a categoria de um item vem do classificador quando a confiança passa do limiar (0,15, escolhido pelos dados); senão das palavras-chave; senão "Outros". Na nuvem, onde o Ollama não roda, é o classificador que responde. O contrato da API e as telas não mudaram, e a empresa continua revisando antes de publicar.

```bash
python scripts/treinar_modelo.py                 # treina, avalia e grava modelo/classificador_categorias.json
python scripts/classificar.py "pao de queijo"    # demonstração no terminal
python scripts/avaliar_modelos.py                # regras x classificador x LLM (use --sem-llm sem o Ollama)
```

Detalhes (atributos, treino, métricas por categoria, matriz de confusão, limiar e limitações) em [docs/dataset-modelo.md](docs/dataset-modelo.md).

<!-- Linhas para as tabelas existentes do README -->

Arquitetura (acrescentar):

```text
├── classificador.py       # Classificador de categorias (Naive Bayes em Python puro)
├── modelo/                # Modelo treinado em JSON, métricas do treino e da avaliação
├── data/                  # Dataset de alimentos, pedidos de avaliação e gerador
├── scripts/               # treinar_modelo.py, classificar.py, avaliar_modelos.py
```

Variáveis de ambiente (acrescentar):

| Variável | Obrigatória | Padrão | Uso |
|---|---|---|---|
| `OLLAMA_PERMITIR_DOCKER` | não | desligado | `1` aceita também, e somente, o host `ollama` do Docker Compose em `OLLAMA_URL` (`http://ollama:11434`). Sem ela, só `localhost`, `127.0.0.1` e `::1`. |

Endpoints (trocar a linha de `interpretar-pedido`):

| POST | `/reconecta/ia/interpretar-pedido` | Empresa logada: texto livre → itens sugeridos para revisão. Categoria pelo classificador treinado. Limite de 10 por minuto por empresa (429 `MUITAS_TENTATIVAS`). |

Documentação complementar (acrescentar):

- [docs/dataset-modelo.md](docs/dataset-modelo.md) — dataset, classificador treinado, métricas e uso na aplicação;
- [docs/avaliacao-modelos.md](docs/avaliacao-modelos.md) — comparação entre regras, classificador e LLM local;
- [data/README.md](data/README.md) — dicionário de dados.

Limitações conhecidas (acrescentar):

- O classificador conhece o vocabulário de 254 alimentos do dataset, que é sintético; alimento muito diferente pode cair na categoria errada, e a empresa sempre revisa antes de publicar.
