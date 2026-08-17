-- runs automatically the first time the container starts, because
-- docker-compose mounts it into /docker-entrypoint-initdb.d/
--
-- careful: postgres only runs this on an EMPTY data directory. if you change
-- this file you need "docker compose down -v" to wipe the volume, otherwise
-- your changes are silently ignored.

-- question 5 keeps its receipts in the same postgres server but in its own
-- database, so django's migrations cannot collide with the vector table here.
-- it has to be created before django can connect, and this file is the only
-- thing that runs before anything else exists.
CREATE DATABASE receipts OWNER shopee;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS items (
    id        SERIAL PRIMARY KEY,
    name      TEXT NOT NULL,
    category  TEXT,
    merchant  TEXT,
    price     NUMERIC(10, 2),
    embedding VECTOR(256) NOT NULL       -- must match DIM in vectorizer.py
);

-- index for approximate search. it does NOT change any of the numbers in this
-- question, postgres ignores it on a table this small and does a full scan,
-- but it's here to show where the real speed up comes from once the table is
-- big (see the note about brute force in README.md).
--
-- vector_cosine_ops is the important part - it tells the index to use the
-- cosine operator <=> and not l2 distance, otherwise the results don't match
-- what cosine.py calculates.
CREATE INDEX IF NOT EXISTS items_embedding_idx
    ON items USING hnsw (embedding vector_cosine_ops);
