## Docker, CI/CD e implantação gratuita

Use `docker compose build app && docker compose up -d --wait` e confira `http://localhost:5000/reconecta/saude`. O Compose sobe Flask e PostgreSQL de desenvolvimento (`reconecta_dev`); `docker compose --profile ia up -d --wait` inclui Ollama opcional. Configure segredos locais em `.env`, usando `.env.example` como guia.

O GitHub Actions em `.github/workflows/ci.yml` testa em Python 3.12, gera JUnit, relatórios Bandit e Trivy, constrói a imagem e verifica o Compose. O Render usa `autoDeployTrigger: checksPass` para publicar `main` após os checks passarem. O Deploy Hook é opcional para acionamento manual; sem ele, o Blueprint segue publicando automaticamente pelos checks.

Para nuvem sem custo pago, o `render.yaml` prepara um Web Service Docker no plano gratuito conectado por login do GitHub ao repositório `lucassilb/reconecta-doacoes`; `DATABASE_URL` aponta para o Session pooler PostgreSQL do Supabase gratuito. `COOKIE_SEGURO=1` ativa cookie HTTPS; `SECRET_KEY` é gerada no Render. Novas fotos ficam no banco, evitando perda no disco efêmero. Há cabeçalhos de segurança, trilha JSON de auditoria e cota de 20 envios de doação por hora por usuário e por processo. Consulte [docs/implantacao.md](docs/implantacao.md) para criação do Supabase e Render, variáveis, verificação e limites do plano gratuito.
