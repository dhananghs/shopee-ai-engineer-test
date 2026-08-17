# search the items table two different ways and print them next to each other:
#   left  = my own cosine.py, python reads every row and compares it
#   right = postgres doing it itself with the <=> operator
#
# if the two columns don't match then my maths is wrong.
#
# usage: python search.py "burger"
#        python search.py "something sweet" 10

import sys
import time

import vector_store
from vectorizer import vectorize
from cosine import cosine_similarity, top_k


def search_mine(cur, query_vec, k):
    rows = vector_store.load_all(cur)

    # top_k wants (id, vector) so drop the name, then put it back afterwards
    names = {}
    pairs = []
    for item_id, name, vec in rows:
        names[item_id] = name
        pairs.append((item_id, vec))

    results = []
    for item_id, score in top_k(query_vec, pairs, k):
        results.append((names[item_id], score))
    return results


def search_postgres(cur, query_vec, k):
    # <=> is cosine DISTANCE, so similarity is 1 minus it.
    # the vector goes in as a string and has to be cast, otherwise postgres
    # complains it can't work out the type.
    cur.execute(
        "SELECT name, 1 - (embedding <=> %s::vector) AS similarity "
        "FROM items ORDER BY embedding <=> %s::vector LIMIT %s",
        (vector_store.to_pgvector(query_vec), vector_store.to_pgvector(query_vec), k),
    )
    return [(name, float(sim)) for name, sim in cur.fetchall()]


def main():
    if len(sys.argv) < 2:
        print('usage: python search.py "your search" [how many]')
        return

    query = sys.argv[1]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    conn = vector_store.connect()
    cur = conn.cursor()

    query_vec = vectorize(query)

    t = time.time()
    mine = search_mine(cur, query_vec, k)
    mine_ms = (time.time() - t) * 1000

    t = time.time()
    theirs = search_postgres(cur, query_vec, k)
    pg_ms = (time.time() - t) * 1000

    print()
    print('search: "%s"' % query)
    print()
    print("  %-28s %-10s   %-28s %-10s" % ("my cosine.py", "score", "postgres <=>", "score"))
    print("  " + "-" * 78)
    for i in range(max(len(mine), len(theirs))):
        left_name, left_score = mine[i] if i < len(mine) else ("", 0)
        right_name, right_score = theirs[i] if i < len(theirs) else ("", 0)
        print("  %-28s %-10.6f   %-28s %-10.6f" % (left_name, left_score, right_name, right_score))

    print()
    same = [a[0] for a in mine] == [b[0] for b in theirs]
    print("  same order :", "yes" if same else "NO - something is wrong")
    if same and mine:
        worst = max(abs(a[1] - b[1]) for a, b in zip(mine, theirs))
        print("  biggest score difference : %.2e" % worst)
    print("  time       : mine %.1f ms, postgres %.1f ms" % (mine_ms, pg_ms))
    print()

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
