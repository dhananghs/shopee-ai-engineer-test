# Shopee - AI Engineer test

Two parts: written answers, and five coding questions.

```
part1-engineering-knowledge/
└── ANSWERS.md                  the five written questions

part2-coding/
├── q1-q3-customer-csv/         analysing a 100k row and a 2M row CSV
├── q4-vector-db/               self-hosted vector DB + cosine similarity by hand
└── q5-receipts/                Django app, receipt photo -> structured expenses

.github/workflows/              CI: test then build the question 5 image
```

Each folder has its own README with the reasoning and how to run it. Start
there - this page is only the map.

## Getting set up

Python 3.11, and Docker for questions 4 and 5.

```bash
python3 -m venv venv && source venv/bin/activate
pip install pandas jupyter                                  # questions 1-3
pip install -r part2-coding/q5-receipts/requirements.txt    # questions 4 and 5
```

Question 4 needs `psycopg2`, which the question 5 requirements already pull in.

Two things are deliberately not in git, so a fresh clone needs them added:

| what | where it goes | why it is missing |
|---|---|---|
| the two customer CSVs | `part2-coding/q1-q3-customer-csv/data/` | ~367 mb together |
| `.env` | `part2-coding/q5-receipts/.env` | holds a real API key - copy `.env.example` |

## The questions

**[Questions 1-3](part2-coding/q1-q3-customer-csv/)** - the customer CSV. What
the data is, and what changes when the file stops fitting in memory. Two
notebooks, one that loads the file and one that streams it, measured against
each other.

**[Question 4](part2-coding/q4-vector-db/)** - postgres + pgvector in Docker,
with cosine similarity implemented from scratch, no numpy. The two are checked
against each other, which is the point of building both.

**[Question 5](part2-coding/q5-receipts/)** - Django app that reads a receipt
photo into structured expense rows and answers questions about them. Ships as a
container image, with a GitHub Actions pipeline that tests it before building.
Uses the same postgres container as question 4, on port 5433.

Run question 4's container before question 5, since question 5 connects to it -
and that container is also what creates question 5's database.
