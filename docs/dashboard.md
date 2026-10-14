# Dashboard de impacto e segurança

O painel público em `/dashboard` usa `GET /reconecta/dashboard` para os números anteriores e `GET /reconecta/dashboard/impacto` e `/seguranca` para esta análise. Os dados de negócio vêm do banco em uso; os dois arquivos de métricas da IA e o resumo SAST são artefatos versionados. O navegador recarrega impacto depois de `reconecta:evento`. Os relatórios SAST só mudam quando gerados e incorporados à versão do projeto.

## Modo demonstração para apresentação pública

A alternância **Dados reais | Demonstração** abre as mesmas rotas com `?modo=demonstracao`; por padrão, a página mostra dados reais. No modo de demonstração, uma faixa fixa durante a rolagem diz **“Dados de demonstração — simulados, não são doações reais”**. O endereço `/dashboard?modo=demonstracao` abre diretamente nesse estado. O resumo em linguagem natural fica desativado nesse modo porque sua rota atual usa dados reais; as métricas da avaliação da IA continuam reais e iguais nos dois modos.

`Dashboard.py` cria uma segunda instância Flask ligada a `sqlite://` com `StaticPool`. Ela semeia o banco **em memória** a partir de [data/demonstracao.json](../data/demonstracao.json), com gerador pseudoaleatório de semente fixa, e executa `montar_dashboard()` e `montar_impacto()` sem mudar o banco configurado. O acesso ao SQLite da demonstração é serializado; nenhum dado da simulação é gravado no Supabase ou no SQLite de produção. A data base é a meia-noite de Brasília do dia corrente, igual em todos os processos. Quando esse dia muda, cada processo cria uma nova instância em memória para manter os gráficos dos últimos 30 dias atuais; para o mesmo dia e a mesma semente, os valores são reprodutíveis.

A semente cria 25 ONGs e 5 mercados com nomes explicitamente fictícios, 8 pessoas de exemplo, 320 pedidos/doações e 160 excedentes distribuídos em 60 dias e nas cinco macrorregiões. CNPJ e CPF são marcadores inválidos com prefixo `DEMO`, e contatos usam `example.invalid`. Doações confirmadas e retiradas seguem o mesmo cálculo que o modo real. O snapshot SAST também é copiado em `data/resumo_sast.json` pelo script gerador, pois `relatorios/` não entra na imagem Docker; o código usa essa cópia apenas quando o relatório principal não está presente.

## Interpretação dos números

| Indicador | Regra | Limite |
|---|---|---|
| Kg em unidades físicas | Apenas `Contribuicao.status=ENTREGUE` e `Excedente.status=RETIRADO`; `kg=1`, `g=0,001`, `L=1` em `data/conversao_kg.csv` | Litro usa a premissa operacional de densidade 1 kg/L; não é pesagem |
| Kg por média de categoria | Para `unidade`, `pacote`, `caixa`, fatores declarados por categoria no mesmo CSV | Estimativa separada do valor acima; médias escolhidas para a apresentação, sem medição amostral |
| Refeições potenciais | `(kg físico + kg estimado) / 0,5`, por UF e macrorregião do endereço da organização que recebeu | 0,5 kg/refeição é premissa configurável em `Dashboard.KG_POR_REFEICAO`; não mede refeições servidas. Endereço sem UF válida vai para "Não informada" |
| Tempo de match | Média de `Contribuicao.criado_em - Doacao.data_cadastro` para doações aceitas/entregues e de `Excedente.reservado_em - Excedente.criado_em` para ofertas reservadas/retiradas | Mede o registro da aceitação/reserva, não o primeiro contato. Casos cancelados e datas inválidas ficam fora |
| Acurácia da IA | `modelo/metricas.json`: classificador em 185 alimentos de teste; top-1/top-3 em 64 ofertas com destino e sem sugestão em 22 sem destino. Comparação com `modelo/limiares.json` | Avaliação offline de 2026-10-14, não taxa de acerto em produção |
| Calor por UF | Refeições potenciais por destino em cartograma de 27 UFs; tabela acessível inclui valores | Cor não normaliza pela população nem afirma densidade geográfica exata |
| Calor dia × hora | Contagem de doações `ACEITA` ou `ENTREGUE` por hora de Brasília no histórico todo | Registro de aceitação, não horário de retirada |
| Refeições geradas por mês | Mesma premissa (kg físico + kg estimado ÷ 0,5) agrupada por mês civil de Brasília sobre a data de entrega/retirada | Linha do tempo de impacto confirmado, não de publicações |
| Predição de descarte | `modelo/metricas.json → risco_descarte` exibido como "Acurácia na predição de descarte"; mostra "ainda não avaliada" quando o modelo não a publica | Métrica do modelo de risco; só aparece quando versionada |

## Segurança

`python scripts/resumo_sast.py` lê `relatorios/sast/{bandit,trivy-fs,trivy-config,trivy-image}.json`, `modelo/{metricas,limiares}.json`, `docs/sast.md` e a matriz `docs/stride.md` e grava `relatorios/sast/resumo.json`. Cada fonte preserva a própria data. O resumo inclui `gates`: a lista dos Security Gates do CI (`ci.yml`) com a regra, o resultado reproduzido sobre o último relatório (`passou`/`falhou`/`sem_dados`) e o detalhe da contagem — Bandit em HIGH, Trivy `fs` em HIGH/CRITICAL corrigível + segredo + misconfig, `trivy config` em HIGH/CRITICAL, Trivy `image` em CRITICAL corrigível e `ia` nos limiares do modelo. A página desenha essa lista e a rosca "Mitigadas / Em análise / Críticas" (mitigadas = correções documentadas em `docs/sast.md`; críticas = HIGH+CRITICAL do snapshot; em análise = o restante, incluindo segredos e misconfigs). A triagem documenta **4 CVEs de dependências corrigidas** e **1 achado Bandit B104 corrigido**; os 4 B608 foram justificados, não contabilizados como correção de CVE. Neste snapshot, Bandit, Trivy de arquivos e de configuração têm zero achados; a varredura da imagem de 2026-10-13 ainda tem **44 HIGH** de pacotes Debian e não é apresentada como mitigada. A matriz marca 23 riscos mitigados e 31 com residual; isso é um estado de análise de ameaça, não número de CVEs corrigidas. O CI produz um resumo novo como artefato após os jobs SAST; a página usa o snapshot versionado até a próxima atualização do repositório.

O cartão de controles lista os cabeçalhos configurados em `app.py` e as cotas da aplicação. HSTS só é ativo com `COOKIE_SEGURO=1`. Falhas e bloqueios de login são registrados no log de auditoria, mas não há contador persistente; o painel indica **não medido**.

Validação: `python -m pytest -q tests/test_dashboard_impacto.py tests/test_dashboard_demo.py`, `python scripts/resumo_sast.py`, `/reconecta/dashboard/impacto`, `/reconecta/dashboard/seguranca`. Os testes cobrem conversão, entregas e retiradas, UF, médias, IA, SAST, STRIDE, isolamento do banco real, reprodutibilidade da semente e privacidade da resposta.
