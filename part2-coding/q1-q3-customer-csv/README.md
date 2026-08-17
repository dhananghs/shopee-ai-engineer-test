# Questions 1-3 - the customers CSV

What the data actually is, and what changes when the file stops fitting in
memory.

## The data files

The two CSVs are not in git - together they are ~367 mb. Put them in `data/`
before running anything:

```
data/customers-100000.csv     17 mb
data/customers-2000000.csv    350 mb
```

## Running it

```
jupyter lab analyze_small.ipynb     # 100k rows, loads the whole file with pandas
jupyter lab analyze_large.ipynb     # 2M rows, streams it one row at a time
```

Each notebook is self-contained and runs top to bottom. The `FILE` constant in
the first cell takes either CSV, so you can run either approach against either
file, which is how I got the comparison numbers below.

`analyze_large.ipynb` runs the duplicate-id check as part of its main pass, so
the memory it reports is the expensive version. That is deliberate - the point
of [Duplicate detection](#duplicate-detection) is what the check costs - but it
is why its headline figure is well above the table below.

## The data

12 columns, same in both files:

```
Index, Customer Id, First Name, Last Name, Company, City, Country,
Phone 1, Phone 2, Email, Subscription Date, Website
```

### Quality

No nulls, no blank strings, no short rows. All 2,000,000 rows have 12 fields.

`Customer Id` is unique in both files. `Email` is not: 5 duplicated addresses in
the 100k file, 1250 in the 2M file. The rows sharing an address have different
ids, names and countries, so they are different people.

```
5BcEBD82eBFf102  Charles Freeman   American Samoa   imitchell@church.com
DDdA80d1beD99b6  Joshua Gallegos   El Salvador      imitchell@church.com
```

Don't use email as a login key or a dedup key here.

### Countries

243 countries, split almost perfectly evenly. About 412 customers per country in
the 100k file, 8230 in the 2M file. The top 10 countries together are 5% of all
customers, where real customer data would normally put 60-80% there.

### Signups

Range is 2020-01-01 to 2022-05-30. 880 distinct days in the 100k file, 29 months
covered.

```
2020   831,045
2021   830,392
2022   338,563    (stops in May, so partial, not a decline)
```

Monthly volume sits at ~70k with no seasonality and no spikes. Every weekday
lands between 14.2% and 14.4%. Real signup data dips at weekends.

### Emails, companies, names

Email domain matches the `Website` column in 19 rows out of 100,000. The two
columns were generated independently, so an employer cannot be inferred from an
address.

Cardinality is high where you would expect a long tail: 38,322 distinct email
domains in 100k rows, 86.5% of them belonging to exactly one customer, plus
71,994 distinct companies.

Names go the other way. 690 first names and 1000 last names, for 2M people. In
the 100k file alone, 7056 people share a full name with someone else. Another
column not to dedup on.

TLDs are `.com`, `.net`, `.org`, `.biz`, `.info`, nothing else. No country TLDs
despite the 243 countries.

### Phones

60% of `Phone 1` values carry an `x` extension, 16% start with `+`, and digit
counts run from 10 to 18. The column needs normalising before it is usable.
`Phone 1` never equals `Phone 2`.

### Summary

Synthetic data. Flat country distribution, flat weekday distribution, no
seasonality, emails unrelated to websites. Fine for load testing and for
building a pipeline against, but any finding about who the biggest market is
would be a property of the generator, not of a business.

## Loading it vs streaming it

The 100k file fits in memory and the 2M file does not, so the same report needs
two different approaches.

Loading means reading the whole file into a DataFrame and then asking questions
about it - you can revisit any row as often as you like, and pandas does the
work in C. Streaming means asking the questions while you read, folding each row
into a running counter and throwing it away, never holding more than one row.

`analyze_small.ipynb` is the first, `analyze_large.ipynb` the second.

### Numbers

Both approaches, same 2M row file, same report:

| | pandas (`analyze_small`) | streaming (`analyze_large`) |
|---|---|---|
| peak RSS, 2M rows | 3041 mb | 154 mb |
| wall time, 2M rows | 34.4 s | 12.3 s |
| peak RSS, 100k rows | 270 mb | 33 mb |

Measured from a terminal, with the duplicate check off in both cases.

`analyze_large.ipynb` prints bigger numbers than that - 716 mb and 35.6 s - and
they are not a contradiction. It keeps the duplicate check in its main pass,
which is 662 mb of the total on its own, and it imports pandas to render tables,
which is most of the rest. [Duplicate detection](#duplicate-detection) is what
that trade costs.

`pd.read_csv()` on the 2M file with no analysis at all already costs 1539 mb RSS,
and the DataFrame reports 1506 mb from `memory_usage(deep=True)`. A 350 mb file
becomes ~1.5 gb in memory, roughly 4x, because pandas has no real string type
here: each of the ~22 million cells is a separate Python `str` with its own
object header, and the column holds pointers to them. The other ~1.5 gb is
temporary copies allocated by `.nunique()`, `.value_counts()` and the `.str`
operations while they run.

Streaming sidesteps all of that. Each row is collected as soon as the loop moves
on, and the 154 mb is mostly counter dictionaries.

### Speed

I expected pure Python to lose to the C parser in pandas. On raw loading it does:
`read_csv` gets through the file in 5.2 s against 12.2 s for my loop. The
analysis afterwards is where it turns around. `.nunique()` and `.value_counts()`
on 2M-element object columns rehash every string on every call, and I call them
on most of the columns. The streaming loop hashes each string once and pulls
every counter out of that single pass.

Numeric columns would flip it straight back. Sums, means and correlations are
vectorised in pandas and hopeless in pure Python. This file is 11 text columns
out of 12, close to the worst case for pandas.

### Limits of a single pass

The one-pass constraint matters more than the memory number. A DataFrame lets
you revisit any row as often as you like. Streaming gives you each row once, in
order, and then it is gone.

Fine in one pass: anything that folds into a running value. Counts, sums, min,
max, mean. Grouped counts too, as long as the group count stays small. Country
(243), year-month (29) and weekday (7) are a few kb each.

Not possible in one pass: median and percentiles, sorting, joins to another
file, exact distinct counts, top-N by revenue. Buffer everything, take a second
pass, or accept an approximation.

The awkward middle is grouped counts with a huge number of groups. `City`,
`Company` and email domain have millions of distinct values in the 2M file, so a
plain `Counter` for those grows nearly as large as the data and I end up holding
the file in RAM by accident. `prune()` handles it. Past 200,000 keys, keep the
popular half and drop the rest:

```python
def prune(counter):
    if len(counter) <= MAX_KEYS:
        return
    keep = dict(counter.most_common(MAX_KEYS // 2))
    counter.clear()
    counter.update(keep)
```

The top 10 survives this, since a genuinely popular value is never sitting in the
tail at the moment pruning happens. Rare counts and the distinct count do not.
That is why the streaming notebook says "cities kept in memory: 119928" instead
of reporting a distinct count, while the pandas one can print "total cities:
49154" and mean it.

### Duplicate detection

Finding duplicated ids means remembering every id seen so far. O(n) memory with
no way to fold it into a counter, so it is worth pricing separately rather than
leaving it buried in the cost of the main pass:

```
streaming pass, no duplicate check  ->  154 mb
    + the duplicate check           ->  662 mb
```

4x the memory for one extra question, and it keeps growing with the file. At 20M
rows the set alone stops fitting. The answer at that size is
`sort -t, -k2 file.csv | uniq -d` or a database, because sorting spills to disk
and a hash set cannot.

### When to use which

Under ~100 mb, use pandas. The memory is free at that size, you get the whole
library, and you can poke at the data in a notebook. Writing a streaming script
here is wasted effort.

100 mb to a few gb, stream it, or use `pd.read_csv(chunksize=...)` for the middle
ground: pandas within each chunk, aggregate across chunks. You keep the
vectorised operations while holding one chunk, and it is less code than a manual
loop. The one-pass constraint still applies and cross-chunk work is still yours
to handle.

Past that, or once one pass stops being enough, stop writing Python. DuckDB will
query this CSV in place with SQL, no loading step, spilling to disk when it needs
to, and it would give exact distinct counts where mine has to approximate.

Size on disk is not really the deciding factor. The question is whether the
answer folds one row at a time into something small - if it does, streaming
holds at any size, and if it does not, no amount of streaming helps and the work
belongs in a real engine.
