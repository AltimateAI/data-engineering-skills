import pendulum
from airflow.sdk import dag, task


@dag(schedule="@hourly", start_date=pendulum.datetime(2025, 1, 1, tz="UTC"), catchup=False)
def events_load():
    @task
    def append_events():
        # INSERT INTO analytics.events SELECT * FROM raw.events WHERE loaded = false
        print("appending new events")

    append_events()


events_load()
