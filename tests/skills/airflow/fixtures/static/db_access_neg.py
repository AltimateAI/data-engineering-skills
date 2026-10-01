# targets: 3.3
# near-miss: db-access-in-task
from datetime import datetime

from airflow.sdk import DAG, Variable, task
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from warehouse.models import Order


@task
def load_orders(**context):
    engine = create_engine("postgresql://warehouse")
    with Session(engine) as session:
        orders = session.query(Order).all()
    prev = context["dag_run"].run_after
    threshold = Variable.get("threshold")
    return len(orders), prev, threshold


with DAG("warehouse_session", schedule=None, start_date=datetime(2026, 1, 1), catchup=False):
    load_orders()
