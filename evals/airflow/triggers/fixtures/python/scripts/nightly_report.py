"""Emails yesterday's invoice summary. Run once a day."""
import datetime as dt


def report_day(now: dt.datetime | None = None) -> dt.date:
    now = now or dt.datetime.now()
    return (now - dt.timedelta(hours=24)).date()


if __name__ == "__main__":
    print(f"sending report for {report_day()}")
