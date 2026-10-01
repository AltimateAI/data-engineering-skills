from pathlib import Path


def test_dags_folder_not_empty():
    assert list((Path(__file__).parent.parent / "dags").glob("*.py"))
