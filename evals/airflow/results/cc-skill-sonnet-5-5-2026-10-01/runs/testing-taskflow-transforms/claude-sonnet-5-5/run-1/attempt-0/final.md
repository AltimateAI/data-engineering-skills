I wrote the suite in `tests/` (`conftest.py` and `test_orders_enrichment.py`). `pytest tests/ -q` gives 22 passed in about 7 s in this venv (Airflow 3.3.2), with no scheduler or webserver. The DAG is unchanged and `git status` shows only `tests/` as new.

**Rules covered**
- **Latest version kept:** a unit test where the older row comes later in the file, plus the end-to-end run, where `S-102` ends up at 120.00.
- **`amount_usd` rounded half-up:** parametrized cases at exact ties (0.025 → 0.03, 51.435 → 51.44) and just either side of a tie. Banker's rounding and float arithmetic would both fail them.
- **Missing FX rate fails the run:** a unit test on `convert_to_usd`, plus an end-to-end run with a JPY order that ends `failed` with no output file.
- **Nothing written unless `validate_totals` passed:**
  - A structure test checks that `load_enriched`'s only upstream task is `validate_totals`.
  - An end-to-end run with a customer-less order fails at `validate_totals` and writes no file.
  - Validation is also unit-tested for negative USD and a missing customer.
- **06:00 UTC daily:** the next 10 runs from the timetable are consecutive days, all at 06:00 UTC.
- **End to end on `data/` for 2026-03-02:**
  - The run succeeds.
  - Only the four 03-02 orders appear, one row each.
  - Every row matches the conversion rule.
  - `S-102` (130.20), `S-103` (51.44) and `S-105` (0.38) are checked by hand.

**Mutation check**
I planted 11 bugs in the DAG file, and the suite caught all 11. They covered:
- reversed or removed dedupe
- half-even rounding
- float arithmetic
- a division in place of the multiplication
- a default rate for unknown currencies
- bypassing `validate_totals`
- a loosened negative check
- a wrong hour
- weekdays only
- date filters that were too wide

The tool restored the DAG file each time.

**Things to know**
- **Isolated runs:** the end-to-end tests redirect input and output to `tmp_path`, so nothing is written to the real `output/`. They also set task `retries` to 0 in memory only. Otherwise the failing-run tests wait out the DAG's 2 retries with a 10-minute delay.
- **Not asserted:** I added no rule about catchup, tags or owner, since you didn't ask for one.
- **Manual runs (not tested):** the DAG derives its date from `ds`. On Airflow 3, a manually triggered run can have no `logical_date`, so `ds` may be missing. The DAG has this latent issue today. It doesn't affect the 06:00 scheduled runs.
- **Not verified:** real scheduler behaviour, other Airflow versions, and the real contents of `output/`.