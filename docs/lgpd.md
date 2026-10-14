# LGPD — mapa de dados e direitos do titular

Estado em 2026-10-14 (rodada 17). Política publicada em `/privacidade`
(`static/privacidade.html`), versão `2026-10-14-r17` declarada em
`privacidade.py:POLITICA_VERSAO`.

## Mapa de dados pessoais

| Dado | Onde vive | Finalidade | Base legal | Retenção |
|---|---|---|---|---|
| Nome, CPF (doador) | `doadores.nome`, `.cpf` | identificar quem doa; impedir cadastro duplicado; CPF nunca é exibido (máscara `***.XXX.XXX-**`) | consentimento, art. 7º I | até a exclusão da conta |
| E-mail, telefone | `doadores`/`estabelecimentos` | login e combinação da retirada | consentimento, art. 7º I | até a exclusão |
| Senha | `*.senha_hash` | autenticação; só hash Werkzeug | consentimento, art. 7º I | até a exclusão |
| CNPJ, razão social, endereço | `estabelecimentos` | verificar aptidão na Receita; informar local de retirada à ONG que reservou | consentimento, art. 7º I; CNPJ/endereço já são públicos na Receita | até a exclusão |
| Endereço da organização → geocodificação | `geolocalizacoes` (chave SHA-256 + lat/lon; nunca o texto nem o dono) | localizar pedidos no mapa e na rota de coleta; endereço enviado ao Nominatim (OpenStreetMap) | consentimento, art. 7º I | cache permanente, sem vínculo com a conta |
| CEP opcional do doador | passa só na requisição de `sugerir-destino`; consultado na BrasilAPI; cache igual por hash | ordenar sugestões por distância | consentimento, art. 7º I | não é gravado no cadastro; cache sem vínculo |
| Consentimento | `*.consentimento_versao`, `.consentimento_em` | comprovar qual versão da política foi aceita e quando | obrigação legal, art. 7º II | enquanto a conta existir |
| Pedidos, doações, excedentes, reservas | `doacoes`, `itens_doacao`, `contribuicoes`, `reservas`, `excedentes` | operar a rede e agregar impacto | execução do serviço, art. 7º V; legítimo interesse, art. 7º IX | persistem anonimizados após exclusão |
| Foto da doação | `contribuicoes.foto_dados` | evidência para quem participa da doação | consentimento, art. 7º I | apagada na exclusão da conta |
| Log de auditoria | stdout (`reconecta.auditoria`) | segurança da conta; data, evento, IP, id do ator — sem payload | legítimo interesse, art. 7º IX | retenção do coletor de logs da plataforma |

## O que é público (minimização)

- Listagens públicas de pedidos e excedentes expõem **nome da organização e
  cidade/UF** — nunca e-mail, telefone, CPF ou endereço completo
  (`Publico.py:serializar_doacao`, `Excedentes.py:_serializar`).
- O endereço de retirada do excedente aparece só para a ONG que reservou
  (`Excedentes.py`, chave `retirada` no detalhe autenticado).
- O dashboard agrega tudo sem identificar pessoas; `instituicoes` (legado CP1)
  não tem autenticação própria e não recebe consentimento.
- O resumo com IA lê só números agregados. O texto livre de pedidos passa pela
  remoção de padrões comuns de e-mail, documento e telefone em `llm_service.py`
  antes da chamada à LLM; essa remoção não cobre todos os formatos.

## Compartilhamento com terceiros

- **Groq Free (operador de LLM, quando `GROQ_API_KEY` está configurada)**:
  recebe o texto livre do pedido após a remoção de padrões comuns de contato e
  documento, ou apenas agregados do dashboard. Não recebe cadastro, sessão,
  endereço ou foto. Sem chave, esse envio não ocorre; entram Ollama local ou
  classificador/regras. O usuário revisa os itens antes de publicar. Como a
  remoção é heurística, a política orienta a não incluir dados pessoais no texto.
- CNPJ → BrasilAPI / OpenCNPJ / CNPJ.ws (só o número, na verificação).
- **Endereço da organização → Nominatim (OpenStreetMap)** e **CEP do doador →
  BrasilAPI**, para georreferenciar pedidos e montar a rota de coleta
  (`geo.py:localizar`, `localizar_cep`). O cache `geolocalizacoes` guarda só
  `sha256(texto) + latitude/longitude + precisão + fonte` — sem id de conta e
  sem o texto original — então não identifica o titular e **não há o que
  apagar por conta na exclusão**.

## Consentimento

Cadastro de doador e de organização exige `aceite_privacidade: true`
(`Cadastro.py:_aceite_faltando`); o servidor grava `consentimento_versao` e
`consentimento_em` no mesmo commit da conta. Cadastros anteriores à política
ficam com os campos nulos (`migracoes.py:_migrar_consentimento`, idempotente) —
a política vale para eles também, mas o aceite gravado prova a versão vista.

## Direitos do titular (art. 18)

| Direito | Onde |
|---|---|
| Confirmação e acesso | `GET /reconecta/auth/me/dados` — cópia JSON da conta e dos registros |
| Correção | `PUT /reconecta/auth/me` (painel, “Seus dados”) |
| Eliminação | `DELETE /reconecta/auth/me` — anonimização imediata |
| Revogação do consentimento | mesma exclusão encerra o tratamento futuro |
| Informação | página `/privacidade`, link no rodapé de todas as páginas e no painel |

## Exclusão por anonimização

`DELETE /reconecta/auth/me` (`Auth.py:Me.delete` → `privacidade.anonimizar_conta`):

- `nome` → "Conta removida"; `email` → `removido-<tipo>-<id>@removido.invalid`;
  `telefone` → `"0"`; `senha_hash` → `NULL`; `cpf` → `REM<id>`; `cnpj` →
  `REMOVIDO-<id>` (os marcadores com letras não colidem com documentos válidos).
- `doacoes.retirada_*` e `contribuicoes.foto_dados` do titular são apagados por
  precaução (endereço de retirada e foto podem identificar).
- Pedidos, doações e excedentes mantêm a referência ao registro anonimizado:
  a estatística agregada (kg, refeições, contagens) não muda — LGPD art. 16
  permite a conservação anonimizada.
- A sessão morre no ato e `Auth.usuario_atual` recusa contas marcadas como
  removidas em qualquer navegador ainda logado.

## Pontos fora do escopo desta rodada

- Verificação de posse de e-mail/documento no cadastro (lacuna S2/S3 do STRIDE).
- Pedido formal por canal de contato: hoje os direitos são autoatendimento no
  painel; o contato do controlador é o grupo do projeto via repositório.
