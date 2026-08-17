# cosine similarity written by hand, no numpy / scipy / sklearn.
# only thing imported is math.sqrt and math.fsum from the standard library.
#
#   cosine(a, b) = dot(a, b) / (norm(a) * norm(b))
#
# the idea is it measures the ANGLE between two vectors and ignores how long
# they are. that's what you want for text, because a long document and a short
# document about the same topic point the same direction, they're just
# different lengths.

import math


def dot(a, b):
    if len(a) != len(b):
        raise ValueError("vectors have different sizes: %d vs %d" % (len(a), len(b)))
    # fsum instead of sum() because adding a lot of floats one by one loses
    # precision. with 512 dimensions the error is small but it's free to fix.
    return math.fsum(a[i] * b[i] for i in range(len(a)))


def norm(a):
    # length of the vector, pythagoras but with more than 2 dimensions
    return math.sqrt(math.fsum(x * x for x in a))


def cosine_similarity(a, b):
    na = norm(a)
    nb = norm(b)

    # a vector of all zeros has no direction so the angle is undefined.
    # returning 0 means "not similar" which is the least surprising answer,
    # the alternative is a ZeroDivisionError or a nan that spreads everywhere.
    if na == 0.0 or nb == 0.0:
        return 0.0

    sim = dot(a, b) / (na * nb)

    # the maths says this is always between -1 and 1, but floating point
    # rounding can give something like 1.0000000000000002 when you compare a
    # vector with itself, and that breaks acos() later on. so clamp it.
    if sim > 1.0:
        return 1.0
    if sim < -1.0:
        return -1.0
    return sim


def cosine_distance(a, b):
    # pgvector's <=> operator returns distance, not similarity, so this is here
    # to compare the two directly. 0 = identical, 2 = opposite.
    return 1.0 - cosine_similarity(a, b)


def normalize(a):
    # divide a vector by its own length so it becomes length 1.
    # after doing this cosine_similarity() is just dot(), no division needed,
    # which is how the real vector databases store things.
    n = norm(a)
    if n == 0.0:
        return list(a)
    return [x / n for x in a]


def cosine_similarity_normalized(a, b):
    # only correct if BOTH vectors already went through normalize().
    # saves recalculating the two square roots on every single comparison.
    return dot(a, b)


def top_k(query, vectors, k=5):
    """brute force search. compares the query against every single vector.

    vectors is a list of (id, vector). returns the k closest as
    (id, score) sorted best first.

    this is exact but it's O(n) per search - fine for a demo, too slow once
    you have millions of rows, which is when you'd add an index (see README).
    """
    scored = []
    for item_id, vec in vectors:
        scored.append((item_id, cosine_similarity(query, vec)))

    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[:k]


def angle_degrees(a, b):
    # not needed for search, but it makes the demo easier to explain -
    # 0 degrees = same direction, 90 = unrelated, 180 = opposite
    return math.degrees(math.acos(cosine_similarity(a, b)))
