import pendulum
from airflow.sdk import dag, task


@dag(
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    default_args={"retries": 2},
    tags=["orders"],
)
def orders_pipeline():
    @task
    def extract():
        return [{"order_id": 1, "amount": 10.0}, {"order_id": 2, "amount": 5.5}]

    @task
    def transform(rows):
        return [r for r in rows if r["amount"] > 0]

    @task
    def load(rows):
        print(f"loaded {len(rows)} rows")

    @task
    def notify():
        print("orders loaded")

    load(transform(extract())) >> notify()


orders_pipeline()
