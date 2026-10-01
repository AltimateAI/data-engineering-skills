# marketing-analytics

| DAG | Schedule | Notes |
|---|---|---|
| `weekly_campaign_report` | Mondays 06:00 UTC | Summarises the previous Mon-Sun week per campaign into `output/weekly/<week_start>.csv` and `output/manifests/<week_start>.json` |
| `campaign_sync` | hourly | Copies the campaign catalogue; only the latest copy matters |

## Re-running a season

When growth re-opens a campaign season we deploy the report with `start_date`
set to the season's first Monday, and the scheduler produces one run for every
week since then. The dashboard expects a report for every week.

## SLA

The weekly report must be finished by 09:00 UTC on Monday (3h after it
starts); `notify_growth_oncall` pages the on-call analyst when it is late.
