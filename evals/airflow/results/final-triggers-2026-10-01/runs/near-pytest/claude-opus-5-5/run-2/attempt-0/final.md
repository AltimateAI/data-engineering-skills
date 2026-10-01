I added `tests/test_totals.py` with 22 tests for `line_total` and `invoice_total`. They all pass, along with the existing smoke test (23 passed).

One thing to know first: as the repo is set up, plain `pytest` can't import `invoicer`, because the package isn't installed and `src/` isn't on the import path. This was already true for the smoke test. I ran the suite with `PYTHONPATH=src python -m pytest`. Running `pip install -e .` would also fix it, or I can add `pythonpath = ["src"]` under `[tool.pytest.ini_options]` in `pyproject.toml` if you want.

**`line_total`**
- **Basics:** no discount, zero quantity, and the result always has two decimal places (`"10.00"`, not `10`).
- **Discounts:** 10%, 25%, a fractional 12.5%, 100% (gives `0.00`), and an explicit 0%.
- **Rounding:** exact halves round up (`0.125 → 0.13`, where the default "round half to even" mode would give `0.12`), `0.005 → 0.01` after a discount, `0.0425 → 0.04`, and `0.1249 → 0.12`.

**`invoice_total`**
- Empty invoice, no tax, a simple tax rate, and lines with no `discount_pct` key (treated as 0%).
- Mixed discounts plus tax: subtotal 62.47 at 8% gives 67.4676, which rounds to `67.47`.
- **Each line is rounded before summing:** two lines of 0.005 total `0.02`, not `0.01`.
- **Tax rounding:** 10.00 at 8.25% is 10.825, which rounds up to `10.83`.
- Fully discounted lines with tax total `0.00`, and the result always has two decimal places.

The tests record what the code does now. In particular, the code rounds each line before summing, and the tests treat that as correct.