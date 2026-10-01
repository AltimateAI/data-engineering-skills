In `dags/orders_pipeline.py`, `load` now returns `len(rows)`, and `notify` takes that count and prints `"{row_count} orders loaded"`. I didn't run the DAG or the tests.

I replaced `load(...) >> notify()` with `notify(load(transform(extract())))`. Passing the value already makes `notify` depend on `load`, so the explicit `>>` was redundant.