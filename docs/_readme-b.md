## Segurança (STRIDE e SAST)

- **Matriz de riscos STRIDE:** `docs/stride.md` — diagrama de fluxo de dados com fronteiras
  de confiança (navegador, contêiner, banco, APIs de CNPJ, Ollama, CI/CD), ativos e atores,
  matriz com probabilidade × impacto e controles referenciados em `arquivo:linha`, estado
  de cada ameaça (resolvida/parcial/residual) e as 5 maiores lacunas restantes.
- **Relatórios SAST:** `relatorios/sast/` (versionados) — Bandit (`bandit.json`, `.txt`,
  `.html`), Trivy `fs` (`trivy-fs.*`), Trivy `config` do Dockerfile (`trivy-config.*`) e
  Trivy `image` da imagem local (`trivy-image.*`). A triagem e o antes/depois estão em
  `docs/sast.md`: hoje **0 achados** no código e nas dependências; a imagem carrega só
  CVEs da base Debian sem correção (aceito, gate de CRITICAL no CI passa).
- **Refazer os relatórios:** `python scripts/sast.py` na raiz do projeto (`--so-bandit`,
  `--sem-imagem`). Pré-requisitos: `uv pip install bandit` no venv, binário do Trivy no
  PATH ou `TRIVY=<caminho>`, e Docker ligado para o scan da imagem.
- **CI:** `.github/workflows/ci.yml` roda a suíte de testes, Bandit (falha em severidade
  alta), Trivy fs e imagem (falha em CRITICAL com correção) e a prova do Compose a cada
  push/PR na `main`; os relatórios viram artefatos do GitHub Actions.
