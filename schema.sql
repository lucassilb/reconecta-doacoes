CREATE TABLE IF NOT EXISTS estabelecimentos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(20) NOT NULL,
    endereco TEXT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS instituicoes (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(20) NOT NULL,
    endereco TEXT NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doadores (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cpf VARCHAR(11) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(20) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS doacoes (
    id SERIAL PRIMARY KEY,
    estabelecimento_id INT NOT NULL,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_limite_retirada TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'DISPONIVEL' CHECK (status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA')),
    CONSTRAINT fk_doacao_estabelecimento FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos (id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS itens_doacao (
    id SERIAL PRIMARY KEY,
    doacao_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    quantidade DECIMAL(10,2) NOT NULL CHECK (quantidade > 0),
    unidade_medida VARCHAR(20) NOT NULL,
    validade DATE NOT NULL,
    CONSTRAINT fk_item_doacao FOREIGN KEY (doacao_id) REFERENCES doacoes (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservas (
    id SERIAL PRIMARY KEY,
    doacao_id INT NOT NULL,
    instituicao_id INT NOT NULL,
    data_reserva TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_retirada TIMESTAMP,
    status VARCHAR(20) DEFAULT 'ATIVA' CHECK (status IN ('ATIVA', 'CANCELADA', 'CONCLUIDA')),
    CONSTRAINT fk_reserva_doacao FOREIGN KEY (doacao_id) REFERENCES doacoes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reserva_instituicao FOREIGN KEY (instituicao_id) REFERENCES instituicoes (id) ON DELETE RESTRICT
);
