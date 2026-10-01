import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[2] / "evals" / "harness"
sys.path.insert(0, str(HARNESS))


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: real agent runs (network, subscription); opt in with EVAL_RUN_SLOW=1")
