# Dados do ReConecta

Dois conjuntos estruturados, escritos para o projeto. **São sintéticos e curados à mão: nenhum dado foi coletado de usuários, de empresas ou do banco da aplicação.** Não há nome de pessoa, documento, contato nem endereço.

| Arquivo | Conteúdo | Tamanho | Uso |
|---|---|---|---|
| `alimentos.csv` | Nome de alimento → categoria | 925 linhas | Treino e teste do classificador de categorias |
| `pedidos_avaliacao.jsonl` | Pedido em texto livre → gabarito estruturado | 66 pedidos, 130 itens | Avaliação das regras, do classificador e da LLM |
| `gerar_dataset.py` | Lista curada e gerador do CSV | — | Refaz `alimentos.csv` |

## `alimentos.csv`

UTF-8, separador vírgula, cabeçalho na primeira linha, uma linha por grafia.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | inteiro | Sequencial, de 1 a 925. |
| `texto` | texto (2 a 100 caracteres) | O alimento como uma empresa escreveria num pedido: "leite integral 1L", "pao frances", "arroz tipo 1 5kg". |
| `categoria` | texto | Uma das 8 categorias da aplicação (`Publico.CATEGORIAS`). |
| `unidade_sugerida` | texto | Unidade mais comum para pedir aquele alimento, dentro de `Publico.UNIDADES` (`kg`, `g`, `L`, `unidade`, `pacote`, `caixa`). É informativa; o classificador não usa. |
| `origem` | texto | `nome_base` (nome principal do alimento), `variacao_escrita` (plural, sem acento, sinônimo, abreviação) ou `embalagem` (grafia com peso, volume ou quantidade por embalagem). |

### Como foi construído

1. Para cada categoria foram listados à mão de 30 a 40 alimentos que aparecem em doações de padarias, mercados, restaurantes e cozinhas (254 alimentos no total).
2. Para cada alimento foram escritas de 3 a 5 grafias, contando o nome principal, do jeito que se digita num pedido: plural ("bananas"), sem acento ("feijao carioca 1kg"), sinônimo regional ("aipim", "macaxeira"), abreviação ("pct", "cx", "un"), marca usada como nome genérico ("miojo", "danone") e embalagem ("leite uht cx 12").
3. `gerar_dataset.py` junta a lista, numera as linhas, marca a `origem` e **descarta grafias repetidas ignorando acento e caixa**. Assim nenhuma linha do teste é cópia de uma linha do treino.

Para refazer: `python data/gerar_dataset.py`. O teste `test_dataset_e_o_que_o_gerador_produz` garante que o CSV versionado é exatamente o que o gerador produz.

### Critérios de categoria

As 8 categorias são as do formulário da aplicação. Nos casos de fronteira o dataset segue estas convenções:

| Categoria | Entra | Casos de fronteira |
|---|---|---|
| Hortifrúti | Frutas, verduras, legumes, raízes e temperos frescos | "milho verde espiga" é Hortifrúti; "milho verde em lata" é Outros |
| Padaria | Pães, bolos, biscoitos, torradas e massas de padaria | "pão de queijo" e "pão de alho" são Padaria; "massa de pizza" é Padaria, "pizza" é Refeições prontas |
| Laticínios | Leite e derivados | "leite de coco" é Outros; "leite de soja" é Bebidas; "margarina" é Outros |
| Carnes e peixes | Carnes, aves, peixes, embutidos, ovos e pescado em lata | "coxinha da asa" é Carnes; "coxinha" é Refeições prontas |
| Grãos e cereais | Arroz, feijões, massas secas, farinhas, cereais e sementes | "proteína de soja" e "carne de soja" são Grãos; "milho de pipoca" é Grãos |
| Refeições prontas | Comida pronta para consumo: marmitas, sopas, lanches, salgados, congelados | "caldo de galinha em cubo" é Outros; "caldo verde" é Refeições prontas |
| Bebidas não alcoólicas | Água, sucos, refrigerantes, chás e bebidas vegetais | "café coado" é Bebidas; "café em pó" é Outros; "suco em pó" é Bebidas |
| Outros | Mercearia que não cabe nas demais: açúcar, sal, óleo, café, molhos, conservas, doces, temperos secos | "molho de tomate" e "batata palha" são Outros |

### Distribuição

| Categoria | Linhas | % |
|---|---|---|
| Hortifrúti | 138 | 14,9% |
| Padaria | 111 | 12,0% |
| Laticínios | 107 | 11,6% |
| Carnes e peixes | 113 | 12,2% |
| Grãos e cereais | 112 | 12,1% |
| Refeições prontas | 109 | 11,8% |
| Bebidas não alcoólicas | 107 | 11,6% |
| Outros | 128 | 13,8% |
| **Total** | **925** | 100% |

Por origem: 254 `nome_base`, 547 `variacao_escrita` e 124 `embalagem`.

### Divisão treino/teste

Feita em `scripts/treinar_modelo.py`, não em arquivos separados:

- **Estratificada por categoria**: 80% treino (740 linhas) e 20% teste (185 linhas), com a mesma proporção em cada categoria.
- **Semente fixa** (`SEMENTE = 42`): a divisão é sempre a mesma.
- A validação cruzada usa 5 dobras estratificadas com a mesma semente.

## `pedidos_avaliacao.jsonl`

Um objeto JSON por linha, UTF-8.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | inteiro | Sequencial, de 1 a 66. |
| `dificuldade` | texto | `facil` (20), `medio` (22) ou `dificil` (24). |
| `texto` | texto | O pedido como a empresa digitaria no campo "Preencher com IA" (5 a 600 caracteres). |
| `itens` | lista | Gabarito: `nome`, `categoria`, `quantidade` (número) e `unidade_medida` de cada item. |
| `prazo` | objeto ou `null` | Gabarito do prazo, independente do dia da execução: `{"tipo":"dia_semana","valor":"sexta"}`, `{"tipo":"amanha"}`, `{"tipo":"dia_mes","valor":20}`, `{"tipo":"em_dias","valor":3}` ou `{"tipo":"data","valor":"2027-03-10"}`. |

Níveis:

- **Fáceis**: uma frase direta com número, unidade e alimento.
- **Médios**: escrita informal, sem acento, caixa alta, vírgula decimal, saudação antes do pedido, três ou quatro itens.
- **Difíceis**: números por extenso ("dez caixas"), dúzia e tonelada, unidade fora da lista ("fardos", "latas"), conversão ("500 ml"), formato "Arroz: 50 kg", negação ("não precisamos de feijão"), telefone no texto e uma tentativa de injeção de instrução.

O telefone que aparece em um pedido difícil é fictício e está lá para testar a remoção de identificadores.

## Licença

Os dois conjuntos e o gerador seguem a licença do repositório (Apache 2.0, arquivo `LICENSE`). Como foram escritos para o projeto, podem ser reutilizados nos mesmos termos.

## Limitações

- O vocabulário é o de 254 alimentos comuns no Brasil. Alimento que não se parece com nenhum deles pode ser classificado errado.
- As grafias imitam a escrita de pedidos, mas não vêm de pedidos reais; a frequência de cada alimento não representa a demanda de nenhuma empresa.
- `unidade_sugerida` é uma só por alimento, embora o mesmo alimento possa ser pedido em unidades diferentes.
- O conjunto de pedidos é pequeno: serve para comparar sistemas, não para estimar desempenho em produção.
