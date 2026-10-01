"""Per-carrier shipment report for one ship_date, read from the vendor_shipments table."""

import argparse
import csv
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", required=True)
    ap.add_argument("--day", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with duckdb.connect(args.warehouse, read_only=True) as con:
        rows = con.execute(
            "SELECT carrier, count(*) AS shipments, "
            "round(sum(CAST(weight_kg AS DOUBLE)), 2) AS total_weight_kg "
            "FROM vendor_shipments WHERE CAST(ship_date AS DATE) = CAST(? AS DATE) "
            "GROUP BY carrier ORDER BY carrier",
            [args.day],
        ).fetchall()
    if not rows:
        raise SystemExit(f"no vendor_shipments rows for {args.day}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["carrier", "shipments", "total_weight_kg"])
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} carriers)")


if __name__ == "__main__":
    main()
