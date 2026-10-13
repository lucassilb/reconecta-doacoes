# Relatórios SAST — ReConecta

Data: 2026-10-13 · Base: `main` em `e652512` · Frente B (rodada 10)

## Ferramentas e comandos

| Ferramenta | Versão | Comando |
|---|---|---|
| Bandit | 1.9.4 (venv do projeto, Python 3.14) | `bandit -r . -x ./tests,./scripts -f json\|txt\|html -o relatorios/sast/bandit.*` |
| Trivy | 0.75.0 (binário fora do repositório, GitHub Releases) | `trivy fs --scanners vuln,secret,misconfig --skip-dirs .git,__pycache__,instance,relatorios,tests/fixtures --format table\|json .` |

Para refazer tudo: `python scripts/sast.py` (defina `TRIVY=<caminho-do-exe>` se o Trivy
não estiver no PATH). Artefatos versionados em `relatorios/sast/`:
`bandit.json`, `bandit.txt`, `bandit.html`, `trivy-fs.txt`, `trivy-fs.json`.

O scan do **Dockerfile/Compose e da imagem** (`trivy image` e `trivy config`) fica para
depois da integração da Frente A — ainda não existem esses arquivos nesta base.

## Resumo

| Origem | CRITICAL | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| Bandit (código, excluindo tests/scripts) | 0 | 0 | **5** | 0 |
| Trivy `fs` — vulnerabilidades (requirements.txt) | 0 | 0 | **4** | 0 |
| Trivy `fs` — segredos | — | — | **0** | — |
| Trivy `fs` — misconfiguração/IaC | — | — | **0** (sem Dockerfile/Compose nesta base) | — |

## Triagem — Bandit (5 achados)

### B104 — `app.py:133` — `app.run(host="0.0.0.0", ...)`
**Verdadeiro, impacto limitado.** O bind em todas as interfaces vale só para o servidor de
desenvolvimento (`if __name__ == "__main__"`); produção usará gunicorn (Frente A). Em
container, `0.0.0.0` é necessário. Não é exploitable por si, mas depende do ambiente.
**Sugestão (item para o Regente):** ler o host de variável, ex.
`host=os.getenv("FLASK_RUN_HOST", "127.0.0.1")`, mantendo `0.0.0.0` opcional para Docker.

### B608 ×4 — `migracoes.py:76,115,162,209` — SQL montado com f-string
**Falso positivo (confiança LOW, conforme o próprio Bandit).** As linhas interpolam nomes
de tabela/coluna que vêm de **constantes do código** (tuplas fixas como
`("arrecadacoes", "contribuicoes")` e listas `campos`), nunca de entrada do usuário. Não há
caminho de dados externo até esses `text()`/`exec_driver_sql`.
**Ressalva:** o padrão continua perigoso se um dia receber nome dinâmico; manter os
identificadores restritos a literais internos. Nenhuma correção exigida.

## Triagem — Trivy `fs` (4 vulnerabilidades MEDIUM em `requirements.txt`)

| Pacote | Instalado | CVE | Corrigido em | Triagem |
|---|---|---|---|---|
| Werkzeug | 3.1.8 | CVE-2026-102598 — DoS via `safe_join()` com device paths do Windows | 3.1.9 | **Verdadeiro, aplicável.** O app serve fotos com `send_from_directory` (usa `safe_join`) e o desenvolvimento roda em Windows. Produção (Linux) reduz o alcance, mas a atualização é trivial. **Item para o Regente** (Frente A possui `requirements.txt`). |
| requests | 2.32.5 | CVE-2026-25645 — bypass de segurança por arquivo temporário previsível | 2.33.0 | **Verdadeiro, aplicabilidade baixa.** O app só faz `GET`/`POST` JSON (`cnpj_service.py`, `llm_service.py`), sem escrita de arquivos pelo requests. Atualizar mesmo assim. |
| python-dotenv | 1.1.1 | CVE-2026-28684 — sobrescrita arbitrária seguindo symlink | 1.2.2 | **Verdadeiro, aplicabilidade baixa.** O app só lê `.env` (`load_dotenv`, `app.py:10`), não escreve. Atualizar. |
| pytest | 8.4.2 | CVE-2025-71176 — DoS/escalonamento por diretório temporário inseguro | 9.0.3 | **Verdadeiro.** Além da CVE, `pytest` está no `requirements.txt` de produção e não deveria ir para a imagem Docker. **Item para o Regente:** mover para `requirements-dev.txt` (a Frente A já cria esse arquivo) e fixar `pytest==9.0.3`. |

**Observação de supply chain:** `psycopg[binary]>=3.2`, `SQLAlchemy>=2.1` e
`tzdata>=2024.1` usam faixas abertas — builds distintos podem resolver versões diferentes.
Recomenda-se pinar (item para o Regente/Frente A; ver T6 em `docs/stride.md`).

**Segredos:** o scanner `secret` do Trivy não encontrou nenhum (`.env` e `instance/` estão
no `.gitignore`; `.env.example` só tem placeholders).

## Achados que exigem mudança de código/config (para o Regente)

| # | Arquivo | Regra/CVE | Correção sugerida |
|---|---|---|---|
| 1 | `app.py:133` | Bandit B104 | `host=os.getenv("FLASK_RUN_HOST", "0.0.0.0")` ou similar — arquivo da Frente A |
| 2 | `requirements.txt` | Trivy CVE-2026-102598 | `Werkzeug==3.1.9` |
| 3 | `requirements.txt` | Trivy CVE-2026-25645 | `requests==2.33.0` |
| 4 | `requirements.txt` | Trivy CVE-2026-28684 | `python-dotenv==1.2.2` |
| 5 | `requirements.txt` | Trivy CVE-2025-71176 | mover `pytest` para `requirements-dev.txt` e usar `pytest==9.0.3` |
| 6 | `requirements.txt` | supply chain | pinar `psycopg[binary]`, `SQLAlchemy`, `tzdata` |
| 7 | `migracoes.py` | Bandit B608 (falso positivo) | nenhuma; manter identificadores internos |

Nenhum achado HIGH ou CRITICAL. Nenhuma correção feita pela Frente B — a posse de
`requirements.txt` e `app.py` é da Frente A.
