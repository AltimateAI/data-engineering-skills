import pendulum
from airflow.sdk import dag, get_current_context, task


@dag(schedule="@daily", start_date=pendulum.datetime(2025, 1, 1, tz="UTC"), catchup=False)
def daily_revenue():
    @task
    def aggregate():
        ctx = get_current_context()
        day = ctx["logical_date"].date()
        print(f"aggregating revenue for {day}")

    aggregate()


daily_revenue()
