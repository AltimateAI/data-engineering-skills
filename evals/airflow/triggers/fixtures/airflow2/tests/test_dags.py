import os


def test_dag_files_exist():
    assert os.listdir(os.path.join(os.path.dirname(__file__), "..", "dags"))
