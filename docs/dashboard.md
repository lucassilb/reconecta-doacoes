# Dashboard de impacto e segurança

O painel público em `/dashboard` usa `GET /reconecta/dashboard` para os números anteriores e `GET /reconecta/dashboard/impacto` e `/seguranca` para esta análise. Os dados de negócio vêm do banco em uso; os dois arquivos de métricas da IA e o resumo SAST são artefatos versionados. O navegador recarrega impacto depois de `reconecta:evento`. Os relatórios SAST só mudam quando gerados e incorporados à versão do projeto.

## Interpretação dos números

| Indicador | Regra | Limite |
|---|---|---|
| Kg em unidades físicas | Apenas `Contribuicao.status=ENTREGUE` e `Excedente.status=RETIRADO`; `kg=1`, `g=0,001`, `L=1` em `data/conversao_kg.csv` | Litro usa a premissa operacional de densidade 1 kg/L; não é pesagem |
| Kg por média de categoria | Para `unidade`, `pacote`, `caixa`, fatores declarados por categoria no mesmo CSV | Estimativa separada do valor acima; médias escolhidas para a apresentação, sem medição amostral |
| Refeições potenciais | `(kg físico + kg estimado) / 0,5`, por UF e macrorregião do endereço da organização que recebeu | 0,5 kg/refeição é premissa configurável em `Dashboard.KG_POR_REFEICAO`; não mede refeições servidas. Endereço sem UF válida vai para "Não informada" |
| Tempo de match | Média de `Contribuicao.criado_em - Doacao.data_cadastro` para doações aceitas/entregues e de `Excedente.reservado_em - Excedente.criado_em` para ofertas reservadas/retiradas | Mede o registro da aceitação/reserva, não o primeiro contato. Casos cancelados e datas inválidas ficam fora |
| Acurácia da IA | `modelo/metricas.json`: classificador em 185 alimentos de teste; top-1/top-3 em 59 ofertas com destino e sem sugestão em 21 sem destino. Comparação com `modelo/limiares.json` | Avaliação offline de 2026-10-14, não taxa de acerto em produção |
| Calor por UF | Refeições potenciais por destino em cartograma de 27 UFs; tabela acessível inclui valores | Cor não normaliza pela população nem afirma densidade geográfica exata |
| Calor dia × hora | Contagem de doações `ACEITA` ou `ENTREGUE` por hora de Brasília no histórico todo | Registro de aceitação, não horário de retirada |

## Segurança

`python scripts/resumo_sast.py` lê `relatorios/sast/{bandit,trivy-fs,trivy-config,trivy-image}.json`, `docs/sast.md` e a matriz `docs/stride.md` e grava `relatorios/sast/resumo.json`. Cada fonte preserva a própria data. A triagem documenta **4 CVEs de dependências corrigidas** e **1 achado Bandit B104 corrigido**; os 4 B608 foram justificados, não contabilizados como correção de CVE. Neste snapshot, Bandit, Trivy de arquivos e de configuração têm zero achados; a varredura da imagem de 2026-10-13 ainda tem **44 HIGH** de pacotes Debian e não é apresentada como mitigada. A matriz marca 23 riscos mitigados e 31 com residual; isso é um estado de análise de ameaça, não número de CVEs corrigidas. O CI produz um resumo novo como artefato após os jobs SAST; a página usa o snapshot versionado até a próxima atualização do repositório.

O cartão de controles lista os cabeçalhos configurados em `app.py` e as cotas da aplicação. HSTS só é ativo com `COOKIE_SEGURO=1`. Falhas e bloqueios de login são registrados no log de auditoria, mas não há contador persistente; o painel indica **não medido**.

Validação: `python -m pytest -q tests/test_dashboard_impacto.py`, `python scripts/resumo_sast.py`, `/reconecta/dashboard/impacto`, `/reconecta/dashboard/seguranca`. Os testes cobrem conversão, entregas e retiradas, UF, médias, IA, SAST, STRIDE e privacidade da resposta.
