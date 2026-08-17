# Question 4 - vector DB + cosine similarity by hand

Self-hosted vector database in Docker, and cosine similarity written from
scratch with no numpy / scipy / sklearn. The two are then checked against each
other, which is the point of doing both.

## Running it

```bash
docker compose up -d          # postgres + pgvector, waits until healthy
python seed.py                # 40 food items
python search.py "burger"     # my cosine vs postgres, side by side
python test_cosine.py         # the proof that my maths is right
python benchmark.py 20000     # why a real index matters
```

Only dependency is `psycopg2` (numpy is used in the tests only, never in the
implementation).

`benchmark.py` needs a lot more rows than 40 food items, so it reuses question
1's `customers-100000.csv`. That file is not in git either - put it in
`../q1-q3-customer-csv/data/` first, or skip that command.

## Files

| file | what it does |
|---|---|
| `docker-compose.yml` | postgres 16 + pgvector, port 5433, healthcheck, volume |
| `schema.sql` | `items` table, `VECTOR(256)` column, HNSW index |
| `cosine.py` | **the answer to the question** - similarity, stdlib only |
| `vectorizer.py` | text to vector, also from scratch (hashing trick) |
| `vector_store.py` | connection + vector parsing helpers |
| `seed.py` / `search.py` | load data, search it two ways |
| `test_cosine.py` | correctness checks |
| `benchmark.py` | brute force vs index as the table grows |

## Why pgvector and not Qdrant/Chroma

Question 5 needs ordinary SQL tables for receipts, and its questions are mostly
aggregates - *"total expenses for food on 20 June"* is `SUM()` with a
`WHERE`, not a semantic search. pgvector means one container does both, and I
can mix a date filter and a similarity search in a single query:

```sql
SELECT name FROM items
WHERE bought_at >= now() - interval '7 days'     -- structured filter
ORDER BY embedding <=> %s::vector                -- semantic ranking
LIMIT 5;
```

With a dedicated vector engine that becomes two stores to keep in sync.

## The implementation

```
cosine(a, b) = dot(a, b) / (norm(a) * norm(b))
```

It measures the **angle** between two vectors and ignores their length, which
is what you want for text - a long description and a short one about the same
food point the same direction.

The details that aren't in the formula:

- **Zero vectors.** No direction, so the angle is undefined. Returns `0.0`
  rather than raising `ZeroDivisionError` or emitting a `nan` that silently
  poisons every downstream comparison.
- **Clamping to [-1, 1].** Mathematically it can't go outside that range, but
  floating point rounding produces `1.0000000000000002` when you compare a
  vector with itself, and that makes `acos()` blow up.
- **Size mismatch raises.** Zipping to the shorter vector would "work" and
  return a plausible wrong number, which is the kind of bug you never find.
- **`math.fsum` not `sum`.** Adding hundreds of floats one at a time
  accumulates rounding error. `fsum` is exact and costs nothing here.
- **`normalize()`.** Store vectors at length 1 and cosine collapses to a plain
  dot product - no square roots per comparison. That's how real vector
  databases do it.

## Correctness

`test_cosine.py`, 14 checks, all passing. Three levels. Level 2 needs numpy and
level 3 needs the container seeded; both skip rather than fail if they can't
run, so level 1 on its own reports 11.

**1. Properties that must always hold** - identical → `1.0`, opposite → `-1.0`,
perpendicular → `0.0`, zero vector safe, mismatch raises, and 2000 random pairs
all land inside [-1, 1].

Including the property that makes cosine the right choice for text:

```
length doesn't matter (scale invariant) -> 0.974631846197076 vs 0.974631846197076
```

Multiplying a vector by 100 changes the similarity by exactly nothing.

**2. Against numpy** (float64, 5000 random pairs up to 512 dimensions):

```
biggest difference 3.331e-16
```

That is machine epsilon - there is no room left in a float64 for the two to
disagree.

**3. Against pgvector** (240 real comparisons through the `<=>` operator):

```
biggest difference 6.665e-08
```

Not zero. pgvector stores `VECTOR` as `float4` (4 bytes) but Python floats are
`float8` (8 bytes), so Postgres rounds the input before it ever does the
arithmetic. float4 carries ~7 significant digits, so a gap near 1e-8 is exactly
what it should be:

```
python  float8 : 0.12345678901234567737
same as float4: 0.12345679104328155518
lost to rounding: 2.031e-09
```

~2e-9 lost per value, accumulated across a 256-dimension dot product, lands at
1e-8. So the tolerance is `1e-6` against Postgres and `1e-12` against numpy -
the difference between the two is a storage format, not a mistake in the maths.

The last check compares the two orderings directly. My top 5 matches Postgres's
on all six queries, so the 1e-8 gap never reaches the part of the result a
search actually uses.

## Embeddings

`vectorizer.py`, also from scratch. Words plus 3-letter chunks, hashed into 256
buckets, normalized to length 1.

The chunks are what makes it work. On whole words alone "hamburger" and
"cheeseburger" share nothing:

```
hamburger vs cheeseburger    0.4767
hamburger vs burger          0.5976
hamburger vs hamburgers      0.7628
hamburger vs iced lemon tea  0.0000
```

Python's built-in `hash()` is randomised per process, so the same word lands in
a different bucket on the next run and every vector already in the database
becomes meaningless. `hashlib.md5` is stable, so that's what the bucketing uses.

It matches spelling, not meaning. It will never work out that "fries" and
"potato" are related, where a real embedding model would. Fine for question 4,
which is about the similarity maths - question 5 needs actual semantics and
should swap in a real model behind the same interface.

## Brute force vs an index

`benchmark.py`, 20,000 real vectors built from question 1's
`customers-100000.csv`:

| method | one search |
|---|---|
| my `cosine.py`, brute force | 954.51 ms |
| ...plus loading the rows into Python first | +848.49 ms |
| Postgres, full scan (exact) | 10.83 ms |
| Postgres, HNSW index (approximate) | **0.80 ms** |

Postgres beats my Python loop by 88x doing the identical exact comparison -
same algorithm, no index, just C and SIMD instead of interpreted loops. The
index then beats that by another 13x by changing the algorithm, 1187x in total.

Merely *transferring* the vectors into Python costs 848 ms, 78x the entire SQL
query on its own. Pulling data out to compute over it loses before the maths
even starts.

My implementation is exact and never misses a result. HNSW is approximate and
can. At 40 rows that trade is not worth making; at 20,000 it is 1187x; at 10
million the brute force is not an option at all. Understand the maths, then let
the database run it.
