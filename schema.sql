CREATE TABLE IF NOT EXISTS estabelecimentos (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(20) NOT NULL,
    endereco TEXT NOT NULL,
    natureza_juridica_codigo VARCHAR(4),
    sem_fins_lucrativos BOOLEAN NOT NULL DEFAULT FALSE,
    atividade_alimentar BOOLEAN NOT NULL DEFAULT TRUE,
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
    status VARCHAR(20) DEFAULT 'DISPONIVEL',
    CONSTRAINT fk_doacao_estabelecimento FOREIGN KEY (estabelecimento_id) REFERENCES estabelecimentos (id) ON DELETE RESTRICT,
    CONSTRAINT fk_doacao_doador FOREIGN KEY (doador_id) REFERENCES doadores (id) ON DELETE RESTRICT,
    CONSTRAINT ck_doacoes_uma_origem CHECK ((estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)),
    CONSTRAINT ck_doacoes_status CHECK (status IN ('DISPONIVEL', 'RESERVADA', 'RETIRADA'))
);

CREATE TABLE IF NOT EXISTS itens_doacao (
    id SERIAL PRIMARY KEY,
    doacao_id INT NOT NULL,
    nome VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    quantidade DECIMAL(10,2) NOT NULL,
    unidade_medida VARCHAR(20) NOT NULL,
    validade DATE,
    CONSTRAINT fk_item_doacao FOREIGN KEY (doacao_id) REFERENCES doacoes (id) ON DELETE CASCADE,
    CONSTRAINT ck_itens_doacao_quantidade CHECK (quantidade > 0),
    CONSTRAINT uq_itens_doacao_id_doacao_id UNIQUE (id, doacao_id)
);

CREATE TABLE IF NOT EXISTS reservas (
    id SERIAL PRIMARY KEY,
    doacao_id INT NOT NULL,
    instituicao_id INT NOT NULL,
    data_reserva TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_retirada TIMESTAMP,
    status VARCHAR(20) DEFAULT 'ATIVA',
    CONSTRAINT fk_reserva_doacao FOREIGN KEY (doacao_id) REFERENCES doacoes (id) ON DELETE RESTRICT,
    CONSTRAINT fk_reserva_instituicao FOREIGN KEY (instituicao_id) REFERENCES instituicoes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_reservas_status CHECK (status IN ('ATIVA', 'CANCELADA', 'CONCLUIDA'))
);

CREATE TABLE IF NOT EXISTS contribuicoes (
    id SERIAL PRIMARY KEY,
    doacao_id INT NOT NULL REFERENCES doacoes(id) ON DELETE RESTRICT,
    item_doacao_id INT NOT NULL,
    doador_id INT REFERENCES doadores(id) ON DELETE RESTRICT,
    estabelecimento_id INT REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
    alimento VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    quantidade NUMERIC(10,2) NOT NULL,
    unidade_medida VARCHAR(20) NOT NULL,
    validade DATE NOT NULL,
    respostas TEXT NOT NULL,
    foto_arquivo VARCHAR(80) NOT NULL,
    foto_dados BYTEA,
    status VARCHAR(20) NOT NULL DEFAULT 'ACEITA',
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_contribuicoes_uma_origem CHECK ((doador_id IS NOT NULL) <> (estabelecimento_id IS NOT NULL)),
    CONSTRAINT ck_contribuicoes_quantidade CHECK (quantidade > 0),
    CONSTRAINT ck_contribuicoes_status CHECK (status IN ('ACEITA', 'ENTREGUE', 'CANCELADA')),
    CONSTRAINT fk_contribuicoes_item_pedido FOREIGN KEY (item_doacao_id, doacao_id)
        REFERENCES itens_doacao (id, doacao_id) ON DELETE RESTRICT
);

ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS senha_hash VARCHAR(255);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS natureza_juridica_codigo VARCHAR(4);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS sem_fins_lucrativos BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS atividade_alimentar BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE doadores ADD COLUMN IF NOT EXISTS senha_hash VARCHAR(255);

CREATE TABLE IF NOT EXISTS excedentes (
    id SERIAL PRIMARY KEY,
    estabelecimento_id INT REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
    doador_id INT REFERENCES doadores(id) ON DELETE RESTRICT,
    retirada_endereco VARCHAR(200),
    retirar_ate TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DISPONIVEL',
    reservado_por_id INT REFERENCES estabelecimentos(id) ON DELETE RESTRICT,
    reservado_em TIMESTAMP,
    retirado_em TIMESTAMP,
    observacao VARCHAR(200),
    foto_tipo VARCHAR(4),
    foto_dados BYTEA,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_excedentes_status CHECK (status IN ('DISPONIVEL', 'RESERVADO', 'RETIRADO', 'CANCELADO', 'EXPIRADO')),
    CONSTRAINT ck_excedentes_observacao CHECK (length(observacao) <= 200),
    CONSTRAINT ck_excedentes_reservante CHECK (
        (status IN ('RESERVADO', 'RETIRADO') AND reservado_por_id IS NOT NULL) OR
        (status IN ('DISPONIVEL', 'CANCELADO', 'EXPIRADO') AND reservado_por_id IS NULL)),
    -- quem publica: organização (CNPJ) ou pessoa física, que informa onde retirar
    CONSTRAINT ck_excedentes_origem CHECK ((estabelecimento_id IS NOT NULL) <> (doador_id IS NOT NULL)),
    CONSTRAINT ck_excedentes_retirada_pf CHECK (doador_id IS NULL OR retirada_endereco IS NOT NULL)
);
-- bancos criados antes da publicação por pessoa física
ALTER TABLE excedentes ALTER COLUMN estabelecimento_id DROP NOT NULL;
ALTER TABLE excedentes ADD COLUMN IF NOT EXISTS doador_id INT REFERENCES doadores(id) ON DELETE RESTRICT;
ALTER TABLE excedentes ADD COLUMN IF NOT EXISTS retirada_endereco VARCHAR(200);
-- foto do alimento mostrando a validade (rodada 19), nula nas ofertas anteriores
ALTER TABLE excedentes ADD COLUMN IF NOT EXISTS foto_tipo VARCHAR(4);
ALTER TABLE excedentes ADD COLUMN IF NOT EXISTS foto_dados BYTEA;

CREATE TABLE IF NOT EXISTS itens_excedente (
    id SERIAL PRIMARY KEY,
    excedente_id INT NOT NULL REFERENCES excedentes(id) ON DELETE CASCADE,
    nome VARCHAR(100) NOT NULL,
    categoria VARCHAR(50) NOT NULL,
    quantidade NUMERIC(10,2) NOT NULL,
    unidade_medida VARCHAR(20) NOT NULL,
    validade DATE NOT NULL,
    CONSTRAINT ck_itens_excedente_quantidade CHECK (quantidade > 0)
);
CREATE INDEX IF NOT EXISTS ix_excedentes_status_prazo ON excedentes(status, retirar_ate);
CREATE INDEX IF NOT EXISTS ix_excedentes_estabelecimento ON excedentes(estabelecimento_id);
CREATE INDEX IF NOT EXISTS ix_excedentes_doador ON excedentes(doador_id);
CREATE INDEX IF NOT EXISTS ix_excedentes_reservado_por ON excedentes(reservado_por_id);
CREATE INDEX IF NOT EXISTS ix_itens_excedente_excedente ON itens_excedente(excedente_id);
CREATE INDEX IF NOT EXISTS ix_itens_excedente_categoria ON itens_excedente(categoria);

CREATE INDEX IF NOT EXISTS ix_doacoes_estabelecimento_id ON doacoes (estabelecimento_id);
CREATE INDEX IF NOT EXISTS ix_doacoes_doador_id ON doacoes (doador_id);
CREATE INDEX IF NOT EXISTS ix_doacoes_status_prazo ON doacoes (status, data_limite_retirada);
CREATE INDEX IF NOT EXISTS ix_itens_doacao_doacao_id ON itens_doacao (doacao_id);
CREATE INDEX IF NOT EXISTS ix_contribuicoes_doacao_status ON contribuicoes (doacao_id, status);
CREATE INDEX IF NOT EXISTS ix_contribuicoes_item_doacao_id ON contribuicoes (item_doacao_id);
CREATE INDEX IF NOT EXISTS ix_contribuicoes_doador_id ON contribuicoes (doador_id);
CREATE INDEX IF NOT EXISTS ix_contribuicoes_estabelecimento_id ON contribuicoes (estabelecimento_id);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS consentimento_versao VARCHAR(20);
ALTER TABLE estabelecimentos ADD COLUMN IF NOT EXISTS consentimento_em TIMESTAMP;
ALTER TABLE doadores ADD COLUMN IF NOT EXISTS consentimento_versao VARCHAR(20);
ALTER TABLE doadores ADD COLUMN IF NOT EXISTS consentimento_em TIMESTAMP;
