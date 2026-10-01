import sys
from pathlib import Path

# Airflow puts the DAGs folder on sys.path when it parses DAGs; do the same for tests.
DAGS_DIR = Path(__file__).resolve().parents[1] / "dags"
if str(DAGS_DIR) not in sys.path:
    sys.path.insert(0, str(DAGS_DIR))
