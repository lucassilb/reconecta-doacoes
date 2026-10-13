## Segurança (STRIDE e SAST)

- **Matriz de riscos STRIDE:** `docs/stride.md` — diagrama de fluxo de dados com fronteiras
  de confiança, ativos e atores, matriz com probabilidade × impacto, controles existentes
  com referência `arquivo:linha` e a lista priorizada das 5 maiores lacunas.
- **Relatórios SAST:** `relatorios/sast/` (versionados) — Bandit (`bandit.json`, `.txt`,
  `.html`) e Trivy `fs` (`trivy-fs.txt`, `.json`; scanners `vuln,secret,misconfig`).
  A triagem achado a achado está em `docs/sast.md`.
- **Refazer os relatórios:** `python scripts/sast.py` na raiz do projeto. Pré-requisitos:
  `uv pip install bandit` no venv e o binário do Trivy no PATH ou em `TRIVY=<caminho>`.
- **CI:** o workflow `.github/workflows/ci.yml` repete Bandit e Trivy a cada push/PR na
  `main` e publica os relatórios como artefatos do GitHub Actions.
