# checks that my cosine.py is actually correct.
#
# three levels of checking:
#   1. the maths properties that must always hold (no dependencies)
#   2. compare against numpy, which i trust
#   3. compare against postgres/pgvector, which is real production code
#
# numpy is imported HERE ONLY, as something to check against. it is not used
# anywhere in cosine.py - that's the whole point of the question.
#
# usage: python test_cosine.py

import math
import random

from cosine import (
    cosine_similarity, cosine_distance, dot, norm, normalize, angle_degrees, top_k
)

passed = 0
failed = 0


def check(name, condition, extra=""):
    global passed, failed
    if condition:
        passed += 1
        print("  ok    %s %s" % (name, extra))
    else:
        failed += 1
        print("  FAIL  %s %s" % (name, extra))


def close(a, b, tol=1e-12):
    return abs(a - b) <= tol


print()
print("1. maths properties")
print("-" * 70)

# a vector compared with itself points exactly the same way = 1
v = [1.0, 2.0, 3.0, 4.0]
check("identical vectors give 1.0", close(cosine_similarity(v, v), 1.0),
      "-> %.15f" % cosine_similarity(v, v))

# exact opposite direction = -1
check("opposite vectors give -1.0", close(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0))

# 90 degrees apart, nothing in common = 0
check("perpendicular vectors give 0.0", close(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0))

# THE property that makes cosine right for text: making a vector 100x longer
# doesn't change the angle at all. a long review and a short review about the
# same food still match.
a = [1.0, 2.0, 3.0]
b = [4.0, 5.0, 6.0]
check("length doesn't matter (scale invariant)",
      close(cosine_similarity(a, b), cosine_similarity([x * 100 for x in a], b)),
      "-> %.15f vs %.15f" % (cosine_similarity(a, b), cosine_similarity([x * 100 for x in a], b)))

# all zeros has no direction, must not crash or return nan
z = cosine_similarity([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])
check("zero vector returns 0.0 and not nan/crash", z == 0.0 and not math.isnan(z))

# different sizes is a bug in the caller, don't silently compare the overlap
try:
    cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
    check("mismatched sizes raise ValueError", False)
except ValueError:
    check("mismatched sizes raise ValueError", True)

# never outside -1..1, even with rounding
random.seed(42)
worst = 0.0
for _ in range(2000):
    n = random.randint(2, 300)
    x = [random.uniform(-50, 50) for _ in range(n)]
    y = [random.uniform(-50, 50) for _ in range(n)]
    s = cosine_similarity(x, y)
    if s > 1.0 or s < -1.0:
        worst = 99
check("2000 random pairs all stay inside -1..1", worst == 0.0)

# distance and similarity are two views of the same number
check("distance == 1 - similarity", close(cosine_distance(a, b), 1 - cosine_similarity(a, b)))

# normalizing makes the length 1, and then cosine is just the dot product
na, nb = normalize(a), normalize(b)
check("normalize() gives length 1.0", close(norm(na), 1.0))
check("dot of normalized == cosine", close(dot(na, nb), cosine_similarity(a, b)))

check("perpendicular is 90 degrees", close(angle_degrees([1.0, 0.0], [0.0, 1.0]), 90.0))


print()
print("2. compared against numpy (float64)")
print("-" * 70)

try:
    import numpy as np

    random.seed(7)
    biggest = 0.0
    for _ in range(5000):
        n = random.randint(2, 512)
        x = [random.uniform(-10, 10) for _ in range(n)]
        y = [random.uniform(-10, 10) for _ in range(n)]

        mine = cosine_similarity(x, y)

        ax, ay = np.array(x), np.array(y)
        theirs = float(np.dot(ax, ay) / (np.linalg.norm(ax) * np.linalg.norm(ay)))

        biggest = max(biggest, abs(mine - theirs))

    check("5000 random pairs match numpy", biggest < 1e-12,
          "-> biggest difference %.3e" % biggest)
except ImportError:
    print("  skipped, numpy not installed")


print()
print("3. compared against postgres / pgvector")
print("-" * 70)

try:
    import vector_store
    from vectorizer import vectorize

    conn = vector_store.connect()
    cur = conn.cursor()

    rows = vector_store.load_all(cur)
    if not rows:
        print("  skipped, no rows - run seed.py first")
    else:
        queries = ["burger", "fried chicken", "cold drink", "pizza", "ice cream", "nasi goreng"]

        biggest = 0.0
        order_ok = True

        # compare against postgres doing the exact thing i do. the hnsw index
        # is approximate and allowed to disagree, so it would be testing the
        # wrong thing here - benchmark.py is where that trade gets measured.
        cur.execute("SET LOCAL enable_indexscan = off")

        for q in queries:
            qv = vectorize(q)

            # ask postgres
            cur.execute(
                "SELECT id, 1 - (embedding <=> %s::vector) FROM items ORDER BY id",
                (vector_store.to_pgvector(qv),),
            )
            pg = dict(cur.fetchall())

            # work it out myself
            for item_id, name, vec in rows:
                mine = cosine_similarity(qv, vec)
                biggest = max(biggest, abs(mine - float(pg[item_id])))

            # the scores disagree in the 8th decimal, but a search only cares
            # which rows come back and in what order. that has to be identical
            # or the rounding above would actually matter.
            cur.execute(
                "SELECT id FROM items ORDER BY embedding <=> %s::vector LIMIT 5",
                (vector_store.to_pgvector(qv),),
            )
            pg_order = [item_id for (item_id,) in cur.fetchall()]
            my_order = [item_id for item_id, score
                        in top_k(qv, [(i, v) for i, _, v in rows], 5)]
            if pg_order != my_order:
                order_ok = False

        check("every score matches pgvector", biggest < 1e-6,
              "-> biggest difference %.3e over %d comparisons" % (biggest, len(queries) * len(rows)))

        check("top 5 comes back in the same order as pgvector", order_ok,
              "-> %d queries" % len(queries))

        # why it isn't exactly zero:
        # pgvector's vector type stores 4 byte floats, python uses 8 byte.
        # so postgres is comparing slightly rounded numbers. float4 keeps about
        # 7 decimal digits, which is exactly the size of gap we see.
        print()
        print("  note: the leftover ~1e-8 is not a bug in cosine.py.")
        print("  pgvector stores VECTOR as float4 (4 bytes) but python floats")
        print("  are float8 (8 bytes), so postgres rounds the input first.")
        print("  float4 holds ~7 significant digits -> a gap around 1e-8 is")
        print("  exactly what you should expect. proof:")

        import struct
        x = 0.1234567890123456789
        rounded = struct.unpack("f", struct.pack("f", x))[0]
        print("    python float8 : %.20f" % x)
        print("    same as float4: %.20f" % rounded)
        print("    lost to rounding: %.3e" % abs(x - rounded))

    cur.close()
    conn.close()

except ImportError:
    print("  skipped, psycopg2 not installed")
except Exception as e:
    print("  skipped, could not reach the database:", e)


print()
print("-" * 70)
print("passed %d, failed %d" % (passed, failed))
print()
