# treasury-reports

Airflow 3.3 project for the treasury desk reports.

| DAG | Output |
|---|---|
| `fx_pnl_report` | `reports/fx_pnl_<trade date>.csv`, per-desk trade count, notional and P&L |
| `desk_reference_refresh` | `reports/reference/desks.csv` |

`data/fx_trades.csv` is the nightly export of booked trades. `trade_date` is
the New York trading day the trade was booked on.
