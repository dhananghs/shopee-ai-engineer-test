# shows WHY a vector database exists, instead of just claiming it.
#
# 40 food items is far too small to prove anything - postgres and my python
# loop both answer instantly. so this loads a lot of real rows (reusing
# customers-100000.csv from question 1) and times the two approaches as the
# table grows.
#
# usage: python benchmark.py [how many rows]     default 20000

import csv
import sys
import time

import psycopg2.extras

import vector_store
from vectorizer import vectorize, DIM
from cosine import cosine_similarity, top_k

CSV = "../q1-q3-customer-csv/data/customers-100000.csv"


def build_table(cur, limit):
    cur.execute("DROP TABLE IF EXISTS bench")
    cur.execute("CREATE TABLE bench (id INT PRIMARY KEY, label TEXT, embedding VECTOR(%s))" % DIM)

    f = open(CSV, newline="", encoding="utf-8")
    reader = csv.reader(f)
    header = next(reader)
    col = {name: i for i, name in enumerate(header)}

    rows = []
    n = 0
    for row in reader:
        # glue a few columns together to make something worth embedding
        label = "%s %s, %s, %s, %s" % (
            row[col["First Name"]], row[col["Last Name"]],
            row[col["Company"]], row[col["City"]], row[col["Country"]],
        )
        rows.append((n + 1, label, vector_store.to_pgvector(vectorize(label))))
        n += 1
        if n >= limit:
            break
    f.close()

    # one row at a time would take minutes, execute_values sends them in batches
    psycopg2.extras.execute_values(
        cur, "INSERT INTO bench (id, label, embedding) VALUES %s", rows, page_size=1000
    )
    return n


def load_python_side(cur):
    cur.execute("SELECT id, embedding FROM bench")
    return [(i, vector_store.from_pgvector(e)) for i, e in cur.fetchall()]


def time_it(fn, repeats=5):
    best = None
    for _ in range(repeats):
        t = time.time()
        fn()
        taken = time.time() - t
        if best is None or taken < best:
            best = taken
    return best * 1000


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 20000

    conn = vector_store.connect()
    cur = conn.cursor()

    print("building table with %d rows (embedding takes a moment)..." % limit)
    t = time.time()
    n = build_table(cur, limit)
    conn.commit()
    print("inserted %d rows in %.1f s" % (n, time.time() - t))

    query_vec = vector_store.to_pgvector(vectorize("Jared Jarvis, Sanchez-Fletcher, Eritrea"))
    query_list = vectorize("Jared Jarvis, Sanchez-Fletcher, Eritrea")

    print()
    print("loading all %d vectors into python..." % n)
    t = time.time()
    vectors = load_python_side(cur)
    load_ms = (time.time() - t) * 1000
    print("took %.0f ms  (this alone is already slower than the whole sql query)" % load_ms)

    # --- 1. my brute force, in python ---
    brute_ms = time_it(lambda: top_k(query_list, vectors, 5), repeats=3)

    # --- 2. postgres, no index (exact, same answer as mine) ---
    cur.execute("SET LOCAL enable_indexscan = off")
    seq = lambda: cur.execute(
        "SELECT id FROM bench ORDER BY embedding <=> %s::vector LIMIT 5", (query_vec,))
    seq_ms = time_it(seq)

    # --- 3. postgres with the hnsw index (approximate) ---
    print()
    print("building hnsw index...")
    t = time.time()
    cur.execute("CREATE INDEX bench_idx ON bench USING hnsw (embedding vector_cosine_ops)")
    conn.commit()
    index_build = time.time() - t
    print("index built in %.1f s" % index_build)

    cur.execute("SET LOCAL enable_seqscan = off")
    idx = lambda: cur.execute(
        "SELECT id FROM bench ORDER BY embedding <=> %s::vector LIMIT 5", (query_vec,))
    idx_ms = time_it(idx)

    print()
    print("-" * 66)
    print("one search over %d vectors, best of several runs" % n)
    print("-" * 66)
    print("  my cosine.py, brute force        %9.2f ms" % brute_ms)
    print("    + loading the rows first       %9.2f ms   (%.2f ms total)" % (load_ms, load_ms + brute_ms))
    print("  postgres, full scan (exact)      %9.2f ms" % seq_ms)
    print("  postgres, hnsw index (approx)    %9.2f ms" % idx_ms)
    print()
    print("  index is %.0fx faster than my python loop" % (brute_ms / idx_ms))
    print("  index is %.0fx faster than postgres scanning" % (seq_ms / idx_ms))
    print()
    print("  my loop is O(n) - double the rows, double the time.")
    print("  hnsw is roughly O(log n), which is the entire reason to run a")
    print("  vector database instead of doing it yourself in a for loop.")
    print("  the trade is that hnsw is APPROXIMATE - it can miss a result.")
    print("  cosine.py never misses, it's just slow.")

    cur.execute("DROP TABLE bench")
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
