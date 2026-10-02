# ReConecta

Plataforma de Redistribuição de Excedentes Alimentares.

Projeto acadêmico desenvolvido para o CP1 da disciplina **Computational Thinking with Python**, com o objetivo de construir a primeira versão funcional do backend de uma plataforma que conecta estabelecimentos doadores a instituições receptoras.

## Sobre o projeto

O desperdício de alimentos é um problema econômico, social e ambiental. Estabelecimentos alimentícios frequentemente possuem produtos excedentes que continuam adequados para consumo, enquanto instituições sociais necessitam de doações para atender pessoas em situação de vulnerabilidade.

O **ReConecta** centraliza esse processo em uma plataforma digital. Por meio de uma API REST, estabelecimentos podem cadastrar doações e seus respectivos alimentos, enquanto instituições podem consultar as ofertas disponíveis, reservar doações e registrar as retiradas.

## Público-alvo

- **Estabelecimentos doadores:** padarias, restaurantes, mercados, hortifrutis e outros estabelecimentos com excedentes adequados para doação.
- **Instituições receptoras:** ONGs, associações, projetos sociais e organizações aptas a receber e distribuir alimentos.

## Objetivo

Conectar estabelecimentos que possuem excedentes alimentares a instituições interessadas em recebê-los, contribuindo para reduzir o desperdício e tornar o processo de doação mais organizado, eficiente e rastreável.

## Escopo do CP1

O CP1 contempla:

- estruturação do backend;
- criação da API REST;
- persistência em banco de dados;
- implementação das entidades principais;
- operações CRUD;
- regras fundamentais do processo de doação;
- documentação Swagger/OpenAPI.

Interfaces gráficas, recursos inteligentes e outras evoluções estão fora do escopo desta primeira versão.

## Principais funcionalidades

- CRUD de estabelecimentos doadores;
- CRUD de instituições receptoras;
- cadastro e gerenciamento de doações;
- cadastro dos itens de cada doação;
- consulta de doações disponíveis;
- reserva de uma doação por uma instituição;
- cancelamento de reservas;
- atualização do status das doações;
- confirmação da retirada;
- consulta do histórico de doações e reservas.

## Regras de negócio

| Código | Regra |
|---|---|
| RN01 | Todo item disponibilizado deverá possuir quantidade maior que zero. |
| RN02 | Alimentos com a data limite para consumo expirada não poderão ser disponibilizados para retirada. |
| RN03 | Somente doações com status `DISPONIVEL` poderão ser reservadas. |
| RN04 | Uma doação não poderá possuir mais de uma reserva ativa simultaneamente. |
| RN05 | Ao registrar uma reserva, o status da doação deverá mudar de `DISPONIVEL` para `RESERVADA`. |
| RN06 | Somente uma doação previamente reservada poderá ter sua retirada confirmada. |
| RN07 | Após a confirmação da retirada, o status da doação deverá mudar para `RETIRADA`. |
| RN08 | Uma reserva poderá ser cancelada antes da retirada. Se a doação continuar válida, poderá retornar ao status `DISPONIVEL`. |
| RN09 | Toda reserva deverá estar associada a uma instituição e a uma doação existentes. |
| RN10 | Reservas e retiradas deverão permanecer registradas para garantir rastreabilidade. |

## Entidades

### Estabelecimento

Representa o estabelecimento doador. Possui, inicialmente: ID, nome, CNPJ, e-mail, telefone e endereço.

### Instituição

Representa a organização receptora. Possui, inicialmente: ID, nome, CNPJ, e-mail, telefone e endereço.

### Doação

Representa uma oferta criada por um estabelecimento. Possui: ID, data de cadastro, data limite para retirada, status e ID do estabelecimento.

Estados previstos: `DISPONIVEL`, `RESERVADA` e `RETIRADA`.

### Item da Doação

Representa um alimento pertencente a uma doação. Possui: ID, nome, categoria, quantidade, unidade de medida, validade e ID da doação.

### Reserva

Representa a reserva feita por uma instituição. Possui: ID, data da reserva, data da retirada, status, ID da doação e ID da instituição.

Estados previstos: `ATIVA`, `CANCELADA` e `CONCLUIDA`.

## Relacionamentos

| Origem | Relação | Destino |
|---|---:|---|
| Estabelecimento | 1:N | Doação |
| Doação | 1:N | Item da Doação |
| Instituição | 1:N | Reserva |
| Doação | 1:N | Reserva (histórico) |

## Fluxo principal

1. Um estabelecimento cadastra uma doação e informa os alimentos disponíveis.
2. Após a validação, a doação recebe o status `DISPONIVEL`.
3. Uma instituição consulta as doações e realiza uma reserva.
4. A reserva fica `ATIVA` e a doação passa para `RESERVADA`.
5. Após a retirada, a reserva passa para `CONCLUIDA` e a doação para `RETIRADA`.
6. Se houver cancelamento antes da retirada e dentro do prazo, a reserva passa para `CANCELADA` e a doação pode voltar a `DISPONIVEL`.

## Restrições

- campos obrigatórios não podem ser enviados vazios;
- quantidades devem ser maiores que zero;
- itens só podem ser associados a doações existentes;
- reservas só podem ser associadas a instituições e doações existentes;
- doações expiradas ou já retiradas não podem ser reservadas;
- identificadores inexistentes devem gerar respostas de erro apropriadas;
- os dados devem ser validados antes da persistência;
- senhas, tokens e credenciais não podem ser armazenados no código-fonte;
- configurações sensíveis devem ser definidas por variáveis de ambiente.

## Tecnologias

- Python
- Flask
- Flask-RESTX
- SQLAlchemy
- PostgreSQL
- Swagger/OpenAPI
- Python-dotenv
- Git e GitHub
- Trello

## Arquitetura inicial

O backend segue uma separação de responsabilidades entre configuração, modelos, rotas, regras de negócio e acesso ao banco de dados.

```text
ReConecta/
├── app/
│   ├── models/       # Entidades do banco de dados
│   ├── routes/       # Endpoints da API
│   ├── services/     # Regras de negócio
│   └── extensions.py # Banco e demais extensões
├── app.py            # Inicialização da aplicação
├── requirements.txt  # Dependências do projeto
├── .env.example      # Exemplo de configuração
├── .gitignore
└── README.md
```

> A estrutura acima deve ser ajustada caso os nomes das pastas e do arquivo principal sejam diferentes no código final.

## Instalação

### Pré-requisitos

- Python 3.10 ou superior;
- PostgreSQL;
- Git.

### Passos

```bash
git clone <URL_DO_REPOSITORIO>
cd ReConecta

python -m venv .venv
```

Ative o ambiente virtual:

```bash
# Windows
.venv\Scripts\activate

# Linux ou macOS
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

## Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto a partir do `.env.example`:

```env
DATABASE_URL=postgresql://USUARIO:SENHA@localhost:5432/reconecta
FLASK_APP=app.py
FLASK_DEBUG=1
```

Não publique o arquivo `.env` no GitHub.

## Execução

Com o banco configurado e o ambiente virtual ativado, execute:

```bash
flask run
```

Por padrão, a aplicação estará disponível em:

```text
http://localhost:5000
```

## Principais endpoints previstos

Os caminhos abaixo representam os recursos definidos para o CP1 e devem ser atualizados para coincidir exatamente com a implementação final.

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/estabelecimentos` | Lista os estabelecimentos. |
| GET | `/estabelecimentos/{id}` | Busca um estabelecimento. |
| POST | `/estabelecimentos` | Cadastra um estabelecimento. |
| PUT | `/estabelecimentos/{id}` | Atualiza um estabelecimento. |
| DELETE | `/estabelecimentos/{id}` | Exclui um estabelecimento. |
| GET/POST | `/instituicoes` | Lista ou cadastra instituições. |
| GET/PUT/DELETE | `/instituicoes/{id}` | Consulta, atualiza ou exclui uma instituição. |
| GET/POST | `/doacoes` | Lista ou cadastra doações. |
| GET/PUT/DELETE | `/doacoes/{id}` | Consulta, atualiza ou exclui uma doação. |
| GET/POST | `/doacoes/{id}/itens` | Lista ou adiciona itens a uma doação. |
| POST | `/doacoes/{id}/reservas` | Reserva uma doação. |
| PATCH | `/reservas/{id}/cancelamento` | Cancela uma reserva ativa. |
| PATCH | `/reservas/{id}/retirada` | Confirma a retirada. |
| GET | `/reservas` | Consulta o histórico de reservas. |

## Documentação Swagger

A documentação interativa da API está disponível em:

**[Acessar Swagger/OpenAPI do ReConecta](https://reconecta.onrender.com/swagger)**

Por meio dessa página, é possível consultar os endpoints, parâmetros, corpos das
requisições, respostas e códigos HTTP documentados pelo projeto.

## Organização no Trello

O grupo utiliza o Trello para distribuir responsabilidades e acompanhar o andamento do CP1:

[Quadro ReConecta no Trello](https://trello.com/invite/b/6a96cdf34f25b339652662c3/ATTI4b7785042036ae55024963ac1546279b355F294D/reconecta)

## Integrantes

| Integrante | RM |
|---|---|
| Aline Delphino Chiaramonte | RM569860 |
| Brian Barreto Brasil | RM570384 |
| Enzo Gabriel Lima Miranda | RM573094 |
| Victor Deggerone Gomes | RM569518 |

## Status

Projeto em desenvolvimento para a entrega do CP1 - 2026.
