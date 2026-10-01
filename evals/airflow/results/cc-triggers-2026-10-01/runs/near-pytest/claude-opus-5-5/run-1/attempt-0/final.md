I added `tests/test_totals.py` with 18 tests for `line_total` and `invoice_total`, and all 18 pass.

They only pass with `PYTHONPATH=src python -m pytest`, or after installing the package with `pip install -e .[dev]`. A plain `pytest` can't find `invoicer` and fails at collection. That was already true for the existing `tests/test_smoke.py`, so it's a project setup gap, not something the new tests introduced. If you want plain `pytest` to work, add `pythonpath = ["src"]` under `[tool.pytest.ini_options]` in `pyproject.toml`. I haven't made that change.

**`line_total`**
- **Basics:** no discount, quantity 0, a 15% discount, a fractional 12.5% discount, and a 100% discount (gives 0.00).
- **Rounding:** an exact half cent rounds up, not to the nearest even cent. For example, 0.125 becomes 0.13 and 0.145 becomes 0.15, including when the half cent comes from a discount (0.045 becomes 0.05). A value just under the half (0.1249) rounds down to 0.12.
- **Format:** the result always has exactly two decimal places (`"10.00"`, not `"10"`).

**`invoice_total`**
- **Basics:** an empty invoice gives `0.00`, a mixed invoice with 8.25% tax gives 26.52, and an invoice with zero tax.
- **Missing discount:** a line without a `discount_pct` key is treated the same as a 0% discount.
- **Per-line rounding:** each line is rounded before the lines are added up. Two lines of 0.005 total 0.02, not 0.01.
- **Tax rounding:** a half cent after tax rounds up (1.005 becomes 1.01).
- **Full discounts:** a line discounted 100% adds nothing to the total.

The run used Python 3.9.4, the default `python` on this machine, even though `pyproject.toml` asks for Python 3.10 or later.