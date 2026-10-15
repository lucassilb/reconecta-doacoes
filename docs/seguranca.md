# Segurança — rodada 18

Relatórios brutos em `relatorios/seguranca/`; o resumo agregado que alimenta o
dashboard fica em `relatorios/sast/resumo.json` (gerado por `scripts/resumo_sast.py`).
A triagem histórica do Bandit/Trivy continua em `docs/sast.md`.

## Frente A — SAST, SCA e segurança "enquanto coda" (Devin #2)

### Ferramentas e comandos

| Ferramenta | Versão | Comando (relatório) | Data |
|---|---|---|---|
| Bandit | 1.8.x | `bandit -r . -x ./tests -f json -o relatorios/seguranca/bandit.json` | 2026-10-14 |
| Semgrep OSS | 1.x | `semgrep --config p/python --config p/flask --config p/secrets --config p/owasp-top-ten --json -o relatorios/seguranca/semgrep.json --exclude tests --exclude .venv .` | 2026-10-14 |
| Semgrep (ruleset próprio) | — | `semgrep --config semgrep-local.yml --error --quiet .` | 2026-10-14 |
| pip-audit | 2.x | `pip-audit -r requirements.txt -r requirements-dev.txt -f json` | 2026-10-14 |
| Trivy | 0.76.0 | `trivy fs --scanners vuln,secret,misconfig -f json -o relatorios/seguranca/trivy-fs.json .` e `trivy config -f json -o relatorios/seguranca/trivy-config.json .` | 2026-10-14 |
| gitleaks | 8.28.0 | `gitleaks dir . -r ...gitleaks-dir.json` e `gitleaks git . -r ...gitleaks-git.json` | 2026-10-14 |
| CycloneDX (SBOM) | 7.x | `cyclonedx-py requirements <reqs> -o relatorios/seguranca/sbom-cyclonedx.json` | 2026-10-14 |

### Achados por severidade (varredura de 2026-10-14)

- **Bandit:** 0 HIGH/MEDIUM; 6 LOW (`B311` random em dados de demonstração/treino
  e `B404`/`B603` subprocess em `scripts/sast.py`, offline e de argumentos fixos) —
  falso positivo/baixo, documentados em `docs/sast.md`.
- **Semgrep (4 pacotes oficiais, 288 regras, 145 arquivos):** inicial 37 achados →
  final **0**:
  - 27 WARNING `github-actions-mutable-action-tag`: **corrigido** — todos os
    `uses:` do CI agora pinados por SHA (com comentário `# vX` legível).
  - 10 ERROR `avoid-sqlalchemy-text` em `migracoes.py`: **justificado** — os
    `text()` recebem apenas identificadores de tabela/coluna vindos de tuplas
    literais do próprio arquivo (nunca entrada de usuário); cada linha ganhou
    `# nosec B608; # nosemgrep` com a justificativa.
  - **Alteração em `migracoes.py`:** somente comentários de justificativa
    (`# nosemgrep` e `# nosec B608` onde faltavam) — nenhuma lógica mudou; a
    migração continua coberta pelos testes de idempotência (`test_lgpd.py`,
    `test_migracao_pedidos.py`, `test_migracao_doador.py`).
- **Ruleset próprio `semgrep-local.yml` (12 regras rápidas):** 0 achados após
  ajuste da regra de segredo literal (a expressão booleana
  `trocando_senha = "senha_atual" in corpo` era falso positivo do regex; agora a
  chave precisa bater a palavra inteira).
- **pip-audit:** **0 vulnerabilidades** nos 15 componentes fixados
  (`requirements.txt` + `requirements-dev.txt`); SBOM CycloneDX em
  `relatorios/seguranca/sbom-cyclonedx.json`.
- **Trivy fs (vuln+secret+misconfig) e config:** 0 achados.
- **gitleaks (diretório e histórico, 123 commits):** 3 achados, todos falsos
  positivos triados e registrados em `.gitleaksignore` por fingerprint (sem o
  valor do segredo):
  - `tests/test_nuvem.py` — literal de teste que prova que o token **não** sai
    no log de auditoria (não é credencial).
  - `relatorios/sast/trivy-image.json` — metadados públicos da imagem base
    `python:*` (variáveis `ENV`/`GPG_KEY` do Dockerfile oficial).
  - `.gitleaks.toml` exclui `relatorios/` das varreduras (artefatos gerados por
    scanners), evitando "vazamento em segunda mão": relatório de segredo
    contendo o próprio achado. Os relatórios versionados ainda foram
    **redigidos** (`Secret`/`Match` substituídos por `<redigido>`).
- **Histórico git:** nenhum segredo real; os 3 achados históricos são os mesmos
  FPs acima (commits `1e54802`, `ec38fe7` — não foi preciso reescrever história).

### "Enquanto coda" — pre-commit

`.pre-commit-config.yaml` roda em cada commit local:

1. `pre-commit-hooks` v5 (trailing whitespace, end-of-file, check-yaml,
   `check-added-large-files` >200 KB, `detect-private-key`, mixed-line-ending)
2. **Bandit** (só severidade alta, `-lll`)
3. **Semgrep** com `semgrep-local.yml` (rápido, offline — os pacotes do registro
   continuam no CI)
4. **pip-audit** `--strict` nos dois requirements
5. **gitleaks protect --staged**

Instalação:

```bash
pip install pre-commit semgrep pip-audit
# gitleaks: github.com/gitleaks/gitleaks/releases (ou choco/brew)
pre-commit install        # uma vez por clone
```

### Gates no CI (`.github/workflows/ci.yml`)

Novos jobs: `sast-semgrep` (relatório + gate ERROR + gate do ruleset local),
`sca-pip-audit` (relatório + SBOM + gate `--strict`), `segredos-gitleaks`
(relatórios dir+git + gate `dir`) e `guardas` (`pre-commit run --all-files` —
mesmos hooks do commit local). Todos entram nos `needs` do `sast-resumo` e do
`deploy`; `scripts/resumo_sast.py` reproduz os gates novos
(`semgrep-erro`, `sca-pip-audit`, `segredos-gitleaks`) para o dashboard —
8/8 portões `passou` no snapshot atual.

### Risco residual

- Secrets do registro Semgrep avaliam heurísticas genéricas; o ruleset local
  cobre o top do projeto, mas nenhum SAST garante cobertura total — a dupla
  revisão continua nos PRs.
- `check-added-large-files` tolera até 200 KB (fotos webp das categorias).
