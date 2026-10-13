# Avaliação dos modelos de interpretação de pedidos

Execução de **2026-10-13 17:37** (horário de Brasília), gerada por `python scripts/avaliar_modelos.py`. Os números abaixo são desta execução; rodar de novo regrava este arquivo.

- Conjunto: `data/pedidos_avaliacao.jsonl`, 66 pedidos (20 fáceis, 22 médios, 24 difíceis) e 130 itens no gabarito.
- Classificador: `modelo/classificador_categorias.json`, treinado em 2026-10-13, limiar 0.15.
- LLM: `qwen2.5:3b` no Ollama local (`http://localhost:11434`), temperatura 0,2, uma chamada por pedido.

## Sistemas comparados

- **(a) Regras**: expressões regulares para quantidade, unidade e prazo; categoria por palavras-chave.
- **(b) Classificador + regras**: as mesmas regras, com a categoria vinda do modelo treinado quando a confiança passa do limiar. É o que a aplicação responde sem o Ollama (`fonte: "regras"`).
- **(c1) LLM, saída validada**: resposta do `qwen2.5:3b` depois da validação de formato, sem conferência.
- **(c2) LLM na aplicação**: o caminho completo de `interpretar_pedido`: a saída da LLM é conferida com os números do texto e, se for rejeitada, a resposta vem de (b).

## Resultados

Os percentuais de categoria, quantidade e unidade são sobre os itens do gabarito: item que o sistema não encontrou conta como erro.

| Medida | (a) Regras | (b) Classificador + regras | (c1) LLM, saída validada | (c2) LLM na aplicação |
|---|---|---|---|---|
| Itens encontrados | 116/130 (89.2%) | 116/130 (89.2%) | 128/130 (98.5%) | 122/130 (93.8%) |
| Categoria certa | 73/130 (56.2%) | 110/130 (84.6%) | 97/130 (74.6%) | 115/130 (88.5%) |
| Quantidade certa | 110/130 (84.6%) | 110/130 (84.6%) | 123/130 (94.6%) | 115/130 (88.5%) |
| Unidade certa | 113/130 (86.9%) | 113/130 (86.9%) | 121/130 (93.1%) | 119/130 (91.5%) |
| Itens a mais (não estão no gabarito) | 3 | 3 | 11 | 3 |
| Prazo certo (por pedido) | 62/66 (93.9%) | 62/66 (93.9%) | 44/66 (66.7%) | 62/66 (93.9%) |
| Pedido inteiro certo | 25/66 (37.9%) | 48/66 (72.7%) | 22/66 (33.3%) | 50/66 (75.8%) |
| Pedido inteiro certo: fáceis | 17/20 (85.0%) | 20/20 (100.0%) | 8/20 (40.0%) | 20/20 (100.0%) |
| Pedido inteiro certo: médios | 5/22 (22.7%) | 21/22 (95.5%) | 7/22 (31.8%) | 21/22 (95.5%) |
| Pedido inteiro certo: difíceis | 3/24 (12.5%) | 7/24 (29.2%) | 7/24 (29.2%) | 9/24 (37.5%) |
| Latência média por pedido | 0.0 s | 0.0 s | 3.572 s | 3.572 s |
| Latência mediana / máxima | 0.0 s / 0.001 s | 0.0 s / 0.0 s | 3.519 s / 7.734 s | 3.519 s / 7.734 s |

Na aplicação com a LLM ligada, 54 de 66 respostas saíram com `fonte: "llm"` e 12 caíram para as regras. A LLM não devolveu um objeto válido em 0 pedidos.

## Exemplos de erro

### (a) Regras

- Pedido 5 (facil): "Precisamos de 40 litros de suco de laranja até amanhã"
  - Esperado: 40 L suco de laranja [Bebidas não alcoólicas]; prazo 2026-10-14
  - Obtido: 40 L suco de laranja [Hortifrúti]; prazo 2026-10-14
- Pedido 11 (facil): "Queremos 80 marmitas até quinta-feira"
  - Esperado: 80 unidade marmitas [Refeições prontas]; prazo 2026-10-15
  - Obtido: 80 unidade marmitas [Outros]; prazo 2026-10-15
- Pedido 19 (facil): "Quero 24 pacotes de pão de forma e 12 kg de presunto"
  - Esperado: 24 pacote pão de forma [Padaria]; 12 kg presunto [Carnes e peixes]; prazo None
  - Obtido: 24 pacote pão de forma [Padaria]; 12 kg presunto [Outros]; prazo None
- Pedido 22 (medio): "Bom dia! A cozinha solidária precisa de 45 kg de coxa e sobrecoxa e 30 kg de linguiça até quinta."
  - Esperado: 45 kg coxa e sobrecoxa [Carnes e peixes]; 30 kg linguiça [Carnes e peixes]; prazo 2026-10-15
  - Obtido: 45 kg coxa e sobrecoxa [Outros]; 30 kg linguiça [Carnes e peixes]; prazo 2026-10-15
- Pedido 24 (medio): "Estamos sem estoque: 60 pacotes de pão de forma integral; 40 unidades de requeijão; 15 kg de mortadela. Receber até terça-feira."
  - Esperado: 60 pacote pão de forma integral [Padaria]; 40 unidade requeijão [Laticínios]; 15 kg mortadela [Carnes e peixes]; prazo 2026-10-20
  - Obtido: 60 pacote pão de forma integral [Padaria]; 40 unidade requeijão [Laticínios]; 15 kg mortadela [Outros]; prazo 2026-10-20
- Pedido 25 (medio): "PRECISAMOS DE 300 UNIDADES DE PAO DE QUEIJO E 100 LITROS DE SUCO DE UVA"
  - Esperado: 300 unidade pao de queijo [Padaria]; 100 L suco de uva [Bebidas não alcoólicas]; prazo None
  - Obtido: 300 unidade PAO DE QUEIJO [Laticínios]; 100 L SUCO DE UVA [Bebidas não alcoólicas]; prazo None

### (b) Classificador + regras

- Pedido 27 (medio): "queria 30 unidades de leite de coco e 15 kg de coco ralado"
  - Esperado: 30 unidade leite de coco [Outros]; 15 kg coco ralado [Outros]; prazo None
  - Obtido: 30 unidade leite de coco [Laticínios]; 15 kg coco ralado [Outros]; prazo None
- Pedido 43 (dificil): "Precisamos de dez caixas de leite e vinte pacotes de arroz até sexta"
  - Esperado: 10 caixa leite [Laticínios]; 20 pacote arroz [Grãos e cereais]; prazo 2026-10-16
  - Obtido: (nenhum item); prazo 2026-10-16
- Pedido 44 (dificil): "Precisamos de duas dúzias de ovos"
  - Esperado: 24 unidade ovos [Carnes e peixes]; prazo None
  - Obtido: (nenhum item); prazo None
- Pedido 45 (dificil): "Arroz: 50 kg. Feijão: 30 kg. Óleo: 10 litros. Entregar até quinta."
  - Esperado: 50 kg arroz [Grãos e cereais]; 30 kg feijão [Grãos e cereais]; 10 L óleo [Outros]; prazo 2026-10-15
  - Obtido: 50 unidade kg [Hortifrúti]; prazo 2026-10-15
- Pedido 46 (dificil): "Leite (100 caixas), pão (200 unidades) e queijo (15 kg)"
  - Esperado: 100 caixa leite [Laticínios]; 200 unidade pão [Padaria]; 15 kg queijo [Laticínios]; prazo None
  - Obtido: 100 unidade caixas), pão (200 unidades) e queijo (15 kg) [Laticínios]; prazo None
- Pedido 47 (dificil): "Precisamos de 500 ml de azeite e 2 litros de vinagre"
  - Esperado: 0.5 L azeite [Outros]; 2 L vinagre [Outros]; prazo None
  - Obtido: 500 unidade ml de azeite [Outros]; 2 L vinagre [Outros]; prazo None

### (c1) LLM, saída validada

- Pedido 1 (facil): "Precisamos de 100 caixas de leite e 100 pães até sexta-feira"
  - Esperado: 100 caixa leite [Laticínios]; 100 unidade pães [Padaria]; prazo 2026-10-16
  - Obtido: 100 caixa Leite [Laticínios]; 100 caixa Pães [Padaria]; prazo 2026-10-17
- Pedido 3 (facil): "Precisamos de 30 kg de feijão e 20 kg de arroz até quarta"
  - Esperado: 30 kg feijão [Grãos e cereais]; 20 kg arroz [Grãos e cereais]; prazo 2026-10-14
  - Obtido: 30 kg Feijão [Grãos e cereais]; 20 kg Arroz [Grãos e cereais]; prazo None
- Pedido 7 (facil): "Preciso de 200 unidades de pão francês até sábado"
  - Esperado: 200 unidade pão francês [Padaria]; prazo 2026-10-17
  - Obtido: 200 unidade Pão francês [Padaria]; prazo 2026-10-18
- Pedido 8 (facil): "60 caixas de leite integral até segunda-feira"
  - Esperado: 60 caixa leite integral [Laticínios]; prazo 2026-10-19
  - Obtido: 60 caixa Leite integral [Laticínios]; prazo 2026-10-14
- Pedido 11 (facil): "Queremos 80 marmitas até quinta-feira"
  - Esperado: 80 unidade marmitas [Refeições prontas]; prazo 2026-10-15
  - Obtido: 1 unidade Marmitas [Refeições prontas]; prazo 2026-10-17
- Pedido 12 (facil): "100 litros de água mineral"
  - Esperado: 100 L água mineral [Bebidas não alcoólicas]; prazo None
  - Obtido: 1 L Água Mineral [Bebidas não alcoólicas]; prazo None

### (c2) LLM na aplicação

- Pedido 27 (medio): "queria 30 unidades de leite de coco e 15 kg de coco ralado"
  - Esperado: 30 unidade leite de coco [Outros]; 15 kg coco ralado [Outros]; prazo None
  - Obtido: 30 unidade Leite de coco [Laticínios]; 15 kg Coco ralado [Outros]; prazo None
- Pedido 44 (dificil): "Precisamos de duas dúzias de ovos"
  - Esperado: 24 unidade ovos [Carnes e peixes]; prazo None
  - Obtido: 24 unidade Ovos [Refeições prontas]; prazo None
- Pedido 45 (dificil): "Arroz: 50 kg. Feijão: 30 kg. Óleo: 10 litros. Entregar até quinta."
  - Esperado: 50 kg arroz [Grãos e cereais]; 30 kg feijão [Grãos e cereais]; 10 L óleo [Outros]; prazo 2026-10-15
  - Obtido: 50 unidade kg [Hortifrúti]; prazo 2026-10-15
- Pedido 46 (dificil): "Leite (100 caixas), pão (200 unidades) e queijo (15 kg)"
  - Esperado: 100 caixa leite [Laticínios]; 200 unidade pão [Padaria]; 15 kg queijo [Laticínios]; prazo None
  - Obtido: 100 unidade caixas), pão (200 unidades) e queijo (15 kg) [Laticínios]; prazo None
- Pedido 47 (dificil): "Precisamos de 500 ml de azeite e 2 litros de vinagre"
  - Esperado: 0.5 L azeite [Outros]; 2 L vinagre [Outros]; prazo None
  - Obtido: 500 unidade ml de azeite [Outros]; 2 L Vinagre [Outros]; prazo None
- Pedido 50 (dificil): "Se possível, uns 40 kg de carne (pode ser de segunda) e 25 kg de frango; o prazo é sábado"
  - Esperado: 40 kg carne [Carnes e peixes]; 25 kg frango [Carnes e peixes]; prazo 2026-10-17
  - Obtido: 40 kg carne (pode ser de segunda) [Carnes e peixes]; 25 kg frango; o prazo é sábado [Carnes e peixes]; prazo None

## Como ler

- O conjunto é pequeno e foi escrito para o projeto: serve para comparar os sistemas entre si, não para estimar o desempenho com pedidos reais.
- Os prazos relativos ("até sexta") são resolvidos para a data da execução, então o gabarito de prazo muda conforme o dia em que o script roda.
- A latência depende desta máquina; a da LLM inclui a carga do modelo na primeira chamada.
