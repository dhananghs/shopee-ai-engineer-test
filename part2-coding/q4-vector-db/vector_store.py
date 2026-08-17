# small wrapper around the postgres connection so the other scripts don't all
# repeat the same connection string and the same vector parsing.

import psycopg2

DSN = "host=localhost port=5433 dbname=vectors user=shopee password=shopee"


def connect():
    return psycopg2.connect(DSN)


def to_pgvector(vec):
    # pgvector doesn't take a python list, it wants the text form '[1,2,3]'
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def from_pgvector(text):
    # comes back out of the database as the same '[1,2,3]' string.
    # psycopg2 doesn't know the vector type so it hands us a plain str.
    return [float(x) for x in text.strip("[]").split(",")]


def insert_item(cur, name, category, merchant, price, vec):
    cur.execute(
        "INSERT INTO items (name, category, merchant, price, embedding) "
        "VALUES (%s, %s, %s, %s, %s)",
        (name, category, merchant, price, to_pgvector(vec)),
    )


def load_all(cur):
    # pulls every row into python so cosine.py can search them itself.
    # obviously this only works because the table is small - the whole point
    # of the database index is that you DON'T do this. it's here so the two
    # methods can be compared on the same data.
    cur.execute("SELECT id, name, embedding FROM items ORDER BY id")

    rows = []
    for item_id, name, embedding in cur.fetchall():
        rows.append((item_id, name, from_pgvector(embedding)))
    return rows


def count_items(cur):
    cur.execute("SELECT count(*) FROM items")
    return cur.fetchone()[0]
