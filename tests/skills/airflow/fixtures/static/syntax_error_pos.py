# targets: 3.3 2.11
from airflow import DAG

with DAG("broken_syntax", schedule=None:  # expect: syntax-error
    pass
