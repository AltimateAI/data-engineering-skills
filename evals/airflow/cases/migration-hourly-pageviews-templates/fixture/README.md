# product-analytics

`dags/hourly_pageviews.py` rolls up raw pageview events (`data/pageviews.jsonl`,
UTC timestamps) once per clock hour.

| Path | Contents | Consumer |
|---|---|---|
| `output/hourly/<YYYYMMDDTHH>.csv` | views, unique sessions and change vs the previous hour, per page, for the hour starting at `HH:00` | analytics dashboard |
| `output/markers/<YYYYMMDDTHH0000>.done` | `hour=... staged=<events>`; the dashboard loader waits for it | dashboard loader |
| `output/staging/<YYYYMMDDTHH>.csv` | staged raw events for the hour; kept for about a day | debugging / replays |

The run at 10:00 UTC processes 09:00-10:00 and writes `20260305T09.csv` and
`20260305T090000.done`.
