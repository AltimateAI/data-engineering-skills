import importlib.util
import os
from pathlib import Path

import pytest
from airflow.models import DagBag

DAG_FOLDER = Path(__file__).parent.parent / "dags"
DAG_FILES = sorted(DAG_FOLDER.glob("*.py"))

os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
BAG = DagBag(dag_folder=str(DAG_FOLDER))


@pytest.mark.parametrize("path", DAG_FILES, ids=lambda p: p.name)
def test_file_imports(path):
    spec = importlib.util.spec_from_file_location(f"dagfile_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def test_dagbag_has_no_errors():
    assert not BAG.import_errors, BAG.import_errors
    assert len(BAG.dags) == 3


@pytest.mark.parametrize("dag_id", sorted(BAG.dag_ids))
class TestPolicy:
    def test_tags(self, dag_id):
        assert BAG.dags[dag_id].tags

    def test_catchup_off(self, dag_id):
        assert BAG.dags[dag_id].catchup is False

    def test_owner(self, dag_id):
        for t in BAG.dags[dag_id].tasks:
            assert t.owner not in (None, "", "airflow"), t.task_id

    def test_retries(self, dag_id):
        for t in BAG.dags[dag_id].tasks:
            assert t.retries >= 2, f"{t.task_id} has retries={t.retries}"


def test_orders_ingest_dependencies():
    dag = BAG.dags["orders_ingest"]
    edges = {(u.task_id, d.task_id) for u in dag.tasks for d in u.downstream_list}
    assert edges == {
        ("extract_orders", "validate_orders"),
        ("validate_orders", "load_orders"),
        ("load_orders", "publish_summary"),
    }
