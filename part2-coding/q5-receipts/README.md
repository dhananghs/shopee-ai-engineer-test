# Question 5 - receipt photo to structured expenses

A Django app. Upload a photo of a food receipt, it comes back as rows in a
database, and then you can ask questions about your spending in plain language.

The AI is used for the two things only a model can do - reading a photo, and
understanding a question. Everything in between is ordinary Django code.

## Demo

https://github.com/user-attachments/assets/db868b49-e4d5-4824-9ec7-fdd629f9d0f7

## Running it

Question 4's postgres container is the database for this app too, so start it
first. Nothing else here needs Docker.

```bash
cd ../q4-vector-db && docker compose up -d   # postgres on 5433
cd ../q5-receipts

cp .env.example .env                         # then put your openrouter key in it
pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo                   # 4 example receipts to ask about
python manage.py runserver
```

Then <http://localhost:8000>. Upload a receipt, or go straight to "Ask a
question" and try *"how much did I spend on food last week"*.

Get a key from <https://openrouter.ai/keys>. The default model is
`google/gemini-2.5-flash-lite`, which reads receipts well enough and costs very
little. `OPENROUTER_MODEL` in `.env` swaps it without touching any code.

If your postgres volume is older than this repo, the `receipts` database will
not exist and `migrate` will stop with `FATAL: database "receipts" does not
exist`. `schema.sql` creates it, but postgres only runs that file on an empty
volume. Either `docker compose down -v` in `../q4-vector-db`, or create it once
by hand:

```bash
docker exec shopee-vectordb psql -U shopee -d postgres -c "CREATE DATABASE receipts OWNER shopee;"
```

## In a container

```bash
cd ../q4-vector-db && docker compose up -d   # still needed, it is the database
cd ../q5-receipts && docker compose up --build
```

Same address, <http://localhost:8000>. `docker compose logs -f web` to watch it.

There is no postgres service in this compose file, deliberately. Question 4
already runs one, and the reason that question chose pgvector over a dedicated
vector engine was so a single server could serve both. Starting a second
postgres here would throw that away. Instead the container joins question 4's
network and reaches it as `vectordb:5432`:

```yaml
environment:
  DB_HOST: vectordb        # the service name, not localhost
  DB_PORT: 5432            # the internal port, not the 5433 the host sees
networks:
  q4:
    external: true
    name: shopee-q4_default
```

The two ports are the part worth reading twice. `5433` is only how your laptop
reaches the container; between containers it is the ordinary `5432`.

Because the database lives in a different compose project, `depends_on` cannot
reach it, so `entrypoint.sh` waits for the port to open before it migrates.

## What happens to a receipt

```
photo  ->  extract.py   the model reads it, returns JSON to a fixed schema
       ->  insight.py   saved as a Receipt plus ReceiptItem rows
       ->  the photo is thrown away

question  ->  agent.py  the model picks a tool and its arguments
          ->  tools.py  our code queries the database and adds up
          ->  agent.py  the model writes the numbers into a sentence
```

| file | what it does |
|---|---|
| `receipts/extract.py` | prompt + JSON schema, sends the photo to the model |
| `receipts/insight.py` | saves the reading, works out the per-receipt summary |
| `receipts/models.py` | `Receipt` and `ReceiptItem` |
| `chat/tools.py` | **the two functions the model is allowed to call** |
| `chat/agent.py` | the tool-calling loop |
| `Dockerfile` / `docker-compose.yml` | the image, and running it against question 4's postgres |

## The photo is never stored

It is read into memory during the upload request, sent to the model, and gone
when the request ends. A receipt carries a name, a card's last digits and
sometimes an address, and none of that is worth keeping to answer "how much did
I spend on coffee".

Three things enforce it rather than one:

- there is no image field on the model - migration `0002_remove_receipt_image`
  took it out
- the extraction prompt says not to return the name, phone, address, card
  number or order ID, so those never even arrive
- a test asserts no field exists that could hold a picture

`KEEP_RECEIPT_IMAGE=1` overrides this and writes copies to `media/debug/`. It
is for checking that the reading works and it is off by default.

## The model never does arithmetic

Adding up prices is something a database does correctly every time and a
language model does approximately. So the model chooses *what* to add up and
our code does the adding.

It also never writes SQL. It picks one of two functions and fills in the
arguments:

```
find_purchases(item_terms, merchant, date_from, date_to)
sum_expenses(date_from, date_to, category, merchant, group_by)
```

`tools.py` turns those into Django queries. The model cannot reach the database
any other way, so a bad tool call returns nothing rather than doing something
unexpected.

`item_terms` is a list because receipts use brand names. Asked about hamburgers
the model sends `["hamburger", "burger", "cheeseburger", "whopper", "big mac"]`,
which is how the question finds a Whopper.

## What was paid vs what the food cost

The food lines never add up to what left your wallet. Tax, service charge and
delivery sit on top, and a discount comes off. `sum_expenses` returns both
numbers, and the system prompt tells the model to answer with `total_paid` and
mention the extra:

```
Rp113,220 including Rp11,220 tax
```

Grouping by day or by merchant lines up with whole receipts, so those get
`total_paid` too. **Grouping by category does not.** One receipt's tax covers
food and drinks at once and there is no honest way to split it, so that case
returns `food_total` alone and the prompt says not to pretend otherwise.

Every receipt page also shows `difference()` - the gap between the printed
total and what the lines add up to. It should be zero. When it is not, the
model missed something, and showing it beats hiding it.

## Three categories, not thirty

`food`, `beverage`, `other`. The first version had `burger`, `pizza` and the
rest, which left bakso, cah kangkung and cap jay with nowhere to go - they all
landed in `other` and the category stopped meaning anything. Anything can be
sorted into eaten, drunk, or neither.

The model also kept sending `"drinks"` where the database says `"beverage"`.
That matched nothing, so the user was told they had spent zero, which is worse
than an error because it looks like an answer. `clean_category()` handles the
plural, and the tool schema lists the allowed values.

## Tests

```bash
python manage.py test          # 25 tests
```

No test calls the API. Every one replaces the model with a fixed reading, so
they are fast, free, and they pass on a machine with no key. The interesting
ones are the tax cases - that the food total and the paid total stay different
numbers, that a missed charge is noticed, and that asking about one category
gets no `total_paid` at all.

## CI

`.github/workflows/q5-receipts.yml`, two jobs.

**test** runs the suite against a real postgres service container, with
`OPENROUTER_API_KEY` set to empty on purpose. If a test ever starts calling the
API for real it fails here instead of quietly costing money.

**image** builds the Dockerfile and pushes to ghcr.io. It runs only after the
tests pass, because an untested image is worse than no image - it looks ready.
Pull requests build without pushing, since a fork's token cannot write to the
registry.

Both are limited to `part2-coding/q5-receipts/**` so unrelated commits do not
trigger a build.

## Limits

- One user, no login. Every receipt belongs to everybody.
- `MAX_STEPS = 5` in `agent.py`. A question needing more tool calls than that
  gets "Sorry, I could not work that out" instead of looping forever.
- Receipts are read one at a time and synchronously, so the upload page waits
  for the model. A queue is the answer for more than a handful.
- `/admin/` renders unstyled in the container. `DEBUG=0` stops Django serving
  static files and nothing else replaces it. The app's own pages carry their
  CSS inline so they are unaffected; whitenoise or nginx would fix admin.
- The reading is only as good as the photo. A blurry total comes back as `0`
  rather than a guess, which is why `difference()` is on the page.
