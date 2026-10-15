# Política de segurança

## Versão com suporte

A branch `main` recebe correções de segurança. Versões e branches antigas não têm suporte garantido.

## Como comunicar uma vulnerabilidade

Use **Report a vulnerability** na aba **Security** do repositório, se o recurso de comunicação privada estiver disponível. Informe a versão ou commit, o impacto, os passos mínimos para reproduzir e a correção sugerida, sem incluir credenciais, dados pessoais ou conteúdo de produção.

Se o formulário privado não estiver disponível, abra uma issue pedindo um canal privado ao mantenedor, **sem publicar payload, prova de exploração ou detalhes sensíveis**. O mantenedor avaliará o relato e combinará a divulgação depois da correção.

## Escopo dos testes

Reproduza testes ativos somente em um clone e em contêineres locais, com contas e dados fictícios. Não execute scanners ou provas de exploração contra o site público, o banco Supabase, as APIs externas ou as contas do projeto. Para um teste fora do ambiente local, peça antes um escopo e uma janela autorizados ao mantenedor.

Consulte [o guia de avaliação](docs/avaliacao-cyber-risk.md) para preparar o ambiente local e limpar contêineres e volumes ao final.
