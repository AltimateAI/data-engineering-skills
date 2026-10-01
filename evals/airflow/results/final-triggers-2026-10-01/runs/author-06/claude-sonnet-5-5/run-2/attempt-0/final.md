In `dags/orders_pipeline.py`, `load` now returns `len(rows)`, and `notify` takes it as `row_count` and prints `orders loaded: {row_count} orders came in`.

I changed `load(...) >> notify()` to `notify(load(...))`. Passing the value already makes `notify` run after `load`, so the explicit `>>` wasn't needed.

The module imports without errors, but I didn't run the DAG or `tests/test_dags.py`.