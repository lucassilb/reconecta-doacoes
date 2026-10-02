# Critério "relacionado a alimentação" por CNAE

`cnae_alimentos.py` decide se o CNPJ de um estabelecimento tem relação com
alimentação/doação de alimentos olhando **só para o código CNAE** (IBGE,
CNAE-Subclasses 2.3) — fiscal (principal) + secundários. A descrição textual
nunca é usada para classificar.

- Código normalizado para 7 dígitos (a BrasilAPI devolve int e perde o zero
  à esquerda: `0155-5/02` chega como `155502`).
- Casamento por **prefixo mais longo** sobre o catálogo abaixo.
- Sem prefixo casado → não alimentar (default seguro).

## Catálogo aceito

| Prefixo | Escopo CNAE 2.3 | Categoria retornada | Por que entra |
|---|---|---|---|
| `0111` | Cultivo de cereais | Lavouras temporárias de alimentos | produz alimento |
| `0113` | Cultivo de cana-de-açúcar | Lavouras temporárias de alimentos | matéria-prima do açúcar |
| `0115` | Cultivo de soja | Lavouras temporárias de alimentos | produz alimento |
| `0116` | Oleaginosas temporárias | Lavouras temporárias de alimentos | amendoim, girassol etc. |
| `0119` | Outras lavouras temporárias | Lavouras temporárias de alimentos | feijão, mandioca, batata, tomate, frutas temporárias |
| `0121` | Horticultura | Horticultura | produz alimento |
| `013` | Lavouras permanentes | Lavouras permanentes de alimentos | frutas, café, cacau, chá, especiarias |
| `015` | Pecuária | Pecuária e produção animal | carnes, leite, ovos, mel |
| `0163` | Pós-colheita | Pós-colheita e beneficiamento | manipula produtos agrícolas diretamente |
| `03` | Pesca e aquicultura | Pesca e aquicultura | produz alimento |
| `10` | Indústria de produtos alimentícios | Indústria de alimentos | divisão inteira, incluindo 10.66 (alimentos para animais — ver limitações) |
| `112` | Bebidas não alcoólicas | Indústria de bebidas não alcoólicas | águas (1121-6), refrigerantes/sucos/chás (1122-4) |
| `4631`–`4635`, `4637`, `4639` | Atacado de alimentos e bebidas | Atacado de alimentos / Atacado de bebidas | distribuidores geram excedente doável |
| `4711`, `4712` | Mercadorias em geral **com** predominância alimentar | Supermercados e mercearias | hiper/supermercados (4711-3/01–02), minimercados (4712-1/00) |
| `4721`–`4724` | Varejo especializado | Varejo especializado de alimentos | padarias, açougues, peixarias, hortifruti, bebidas |
| `4729602`, `4729699` | 4729-6/02 e /99 | Varejo de alimentos | lojas de conveniência e outros alimentícios |
| `56` | Alimentação | Serviços de alimentação | restaurantes, lanchonetes, catering, cantinas |
| `8800` | Serviços sociais sem alojamento | Assistência social sem alojamento | bancos de alimentos e cozinhas comunitárias se registram aqui |

## Excluído de propósito

| Prefixo | O que é | Por que fica fora |
|---|---|---|
| `0112` | Algodão e fibras | não é alimento |
| `0114` | Fumo | não é alimento |
| `0122` | Floricultura | não é alimento |
| `014` | Sementes/mudas certificadas | insumo agrícola, não manipula alimento |
| `0161`, `0162` | Serviços de apoio a agro/pecuária | serviços, não manipulam alimento |
| `017` | Caça | vedado/atípico |
| `02` | Produção florestal | madeira/car-vão; o extrativismo de palmito/castanha (02.09) fica fora junto — raro |
| `111` | Bebidas alcoólicas (aguardente, vinho, cerveja) | excluído a pedido do brief — fora do escopo de doação de alimentos |
| `12` | Produtos do fumo | não é alimento |
| `462` | Atacado de matérias-primas agrícolas e animais vivos | commodity/insumo, não produto doável; brief restringe a 463* |
| `4636` | Atacado de fumo | não é alimento |
| `461`, `464`–`469` | Representantes e atacado não alimentar | sem vínculo alimentar |
| `4713` | Mercadorias em geral **sem** predominância alimentar | literalmente a definição oposta |
| `4729601` | Tabacaria (4729-6/01) | única subclasse não alimentar dentro da classe 4729-6 |
| `473`–`479` | Combustíveis, farmácia, outros varejos | sem vínculo alimentar |
| `55` | Hospedagem | hotelaria não é a atividade doadora-alvo |
| `87` | Assistência social **com** alojamento | instituições residentes, não doadoras |
| `94` | Associações genéricas (9430-8, 9499-5…) | não comprovam vínculo alimentar; uma ONG de tecnologia não pode passar |

## Limitações conhecidas (casos reais)

- **ONG Banco de Alimentos** (02.736.449/0001-48, ATIVA) é um banco de
  alimentos de verdade, mas registrada como `9430-8/00` + `9499-5/00`
  (associações genéricas) → **recusada**. O código não distingue ONG de
  doação de alimentos de ONG de tecnologia; abrir `94xx` quebraria a regra
  do brief. Saída: entidade assistencial se registra em `8800-6/00`, ou
  rever por lista manual se o Lucas quiser admitir associações.
- **Diageo Brasil** (62.166.848/0001-42): atacado de bebidas `4635-4/99`
  (destilados) **passa** — a classe mistura alcoólicas e não alcoólicas e a
  Receita não separa. Aceito deliberadamente: `4635-4` cobre distribuidoras
  de água/suco/refrigerante; filtrar por descrição feriria a regra "o código
  manda".
- **Ambev/Pitú/Aurora** passam por secundários alimentares reais
  (refrigerantes 1122-4, sucos 1033-3, atacado de alimentos). Correto pelo
  critério — não são "só álcool". **Salton** (só vinho + turismo + flores)
  é recusada.
- **10.66-0** (ração/alimentos para animais) entra junto com a divisão 10
  — brief pediu a divisão inteira.
- **Versão CNAE**: os prefixos seguem a numeração de subclasses CNAE 2.3
  (o que a BrasilAPI devolve). Em CNAE 2.0, `4729-6/01` era alimentício e
  `/02` era tabacaria (inverteu em 2.2/2.3); cadastros antigos podem carregar
  o sentido antigo — risco residual aceito.

## Casos reais testados

Fonte: BrasilAPI, 2026-10-02 (`tests/fixtures/cnpjs_reais.json`).

| CNPJ | Empresa | Situação | CNAE principal | Resultado |
|---|---|---|---|---|
| 02.916.265/0001-60 | JBS | ATIVA | 1011-2/01 frigorífico | alimentar |
| 42.591.651/0001-43 | Arcos Dourados (McDonald's) | ATIVA | 5611-2/03 lanchonetes | alimentar |
| 47.508.411/0001-56 | Pão de Açúcar | ATIVA | 4789-0/99 (não alimentar) | alimentar via secundários |
| 07.526.557/0001-00 | Ambev | ATIVA | 1113-5/02 cerveja | alimentar via secundários |
| 11.856.283/0001-94 | Pitú | ATIVA | 1111-9/01 aguardente | alimentar via 1122-4/99 + comércio de bebidas |
| 87.547.188/0001-70 | Vinícola Aurora | ATIVA | 1112-7/00 vinho | alimentar via 1033-3/02 sucos |
| 62.166.848/0001-42 | Diageo | ATIVA | 4635-4/99 atacado bebidas | alimentar (caso-limite) |
| 20.730.099/0001-94 | Sadia | **BAIXADA** | 1012-1/03 frigorífico | alimentar, mas inapta pela situação |
| 06.990.590/0001-23 | Google Brasil | ATIVA | 6319-4/00 tecnologia | recusada |
| 87.547.428/0001-37 | Vinícola Salton | ATIVA | 1112-7/00 vinho | recusada (só alcoólica) |
| 02.736.449/0001-48 | ONG Banco de Alimentos | ATIVA | 9430-8/00 | recusada (CNAE genérico) |
| 00.390.654/0001-79 | Banco de Alimentos | BAIXADA | 9430-8/00 | recusada (baixada + CNAE genérico) |
