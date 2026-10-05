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
    estabelecimento_id INT,
    doador_id INT,
    retirada_endereco VARCHAR(200),
    retirada_municipio VARCHAR(80),
    retirada_uf CHAR(2),
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_limite_retirada TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'DISPONIVEL' CHECK (status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA')),
    CONSTRAINT fk_doacao_estabelecimento FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos (id) ON DELETE RESTRICT,
    CONSTRAINT fk_doacao_doador FOREIGN KEY (doador_id) REFERENCES doadores (id) ON DELETE RESTRICT,
    CONSTRAINT ck_doacoes_uma_origem CHECK ((estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL))
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

CREATE TABLE IF NOT EXISTS arrecadacoes (
    id SERIAL PRIMARY KEY,
    estabelecimento_id INT NOT NULL REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
    titulo VARCHAR(80) NOT NULL,
    descricao VARCHAR(500) NOT NULL,
    categorias VARCHAR(300) NOT NULL,
    meta_descricao VARCHAR(120),
    entrega_endereco VARCHAR(200) NOT NULL,
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ATIVA' CHECK (status IN ('ATIVA', 'ENCERRADA')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contribuicoes (
    id SERIAL PRIMARY KEY,
    arrecadacao_id INT NOT NULL REFERENCES arrecadacoes(id) ON DELETE RESTRICT,
    doador_id INT REFERENCES doadores(id) ON DELETE RESTRICT,
    estabelecimento_id INT REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
    alimento VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    quantidade NUMERIC(10,2) NOT NULL CHECK (quantidade > 0),
    unidade_medida VARCHAR(20) NOT NULL,
    validade DATE NOT NULL,
    respostas TEXT NOT NULL,
    foto_arquivo VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACEITA' CHECK (status IN ('ACEITA', 'ENTREGUE', 'CANCELADA')),
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_contribuicoes_uma_origem CHECK ((doador_id IS NOT NULL) <> (estabelecimento_id IS NOT NULL))
);

ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS senha_hash VARCHAR(255);
ALTER TABLE doadores ADD COLUMN IF NOT EXISTS senha_hash VARCHAR(255);
