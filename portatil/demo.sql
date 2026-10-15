-- Banco de demonstração do Sentinela: uma pequena loja com clientes, produtos e
-- pedidos. Executado uma única vez, como superusuário do PostgreSQL portátil.

CREATE ROLE backup_user LOGIN PASSWORD 'demo123';
CREATE DATABASE loja_demo OWNER backup_user ENCODING 'UTF8' TEMPLATE template0;

\connect loja_demo
SET ROLE backup_user;

CREATE TABLE clientes (
    id         serial PRIMARY KEY,
    nome       text NOT NULL,
    cidade     text NOT NULL,
    email      text,
    criado_em  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE produtos (
    id       serial PRIMARY KEY,
    nome     text NOT NULL,
    preco    numeric(10,2) NOT NULL CHECK (preco >= 0),
    estoque  integer NOT NULL DEFAULT 0
);

CREATE TABLE pedidos (
    id          bigserial PRIMARY KEY,
    cliente_id  integer NOT NULL REFERENCES clientes(id),
    produto_id  integer NOT NULL REFERENCES produtos(id),
    quantidade  integer NOT NULL CHECK (quantidade > 0),
    feito_em    timestamptz NOT NULL
);
CREATE INDEX ix_pedidos_cliente ON pedidos(cliente_id);

INSERT INTO clientes (nome, cidade, email)
SELECT (ARRAY['Ana','João','Maria','José','Lúcia','Pedro','Fernanda','Carlos','Júlia','Tiago'])[1 + g % 10]
       || ' ' || (ARRAY['Souza','Silva','Oliveira','Pereira','Conceição','Lima','Gonçalves','Araújo'])[1 + g % 8],
       (ARRAY['São Lourenço do Oeste','Chapecó','Xanxerê','Florianópolis','Pato Branco','Concórdia'])[1 + g % 6],
       'cliente' || g || '@exemplo.com.br'
FROM generate_series(1, 500) g;

INSERT INTO produtos (nome, preco, estoque)
SELECT (ARRAY['Roteador','Cabo de rede','Switch','Câmera IP','Nobreak','Pendrive','Mouse','Teclado'])[1 + g % 8]
       || ' modelo ' || g,
       round((10 + random() * 990)::numeric, 2),
       (random() * 200)::int
FROM generate_series(1, 200) g;

INSERT INTO pedidos (cliente_id, produto_id, quantidade, feito_em)
SELECT 1 + (g % 500), 1 + (g % 200), 1 + (g % 5),
       now() - (g || ' minutes')::interval
FROM generate_series(1, 20000) g;

CREATE VIEW faturamento_por_cliente AS
SELECT c.id, c.nome, c.cidade, sum(p.quantidade * pr.preco) AS total
FROM clientes c
JOIN pedidos p ON p.cliente_id = c.id
JOIN produtos pr ON pr.id = p.produto_id
GROUP BY c.id, c.nome, c.cidade;

CREATE FUNCTION total_do_cliente(cid integer) RETURNS numeric
LANGUAGE sql STABLE AS $$
    SELECT coalesce(sum(p.quantidade * pr.preco), 0)
    FROM pedidos p JOIN produtos pr ON pr.id = p.produto_id
    WHERE p.cliente_id = cid
$$;
