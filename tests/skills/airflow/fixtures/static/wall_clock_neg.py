# targets: 3.3 2.11
# near-miss: wall-clock-in-task
import time
from datetime import datetime, timezone

from airflow.decorators import task


@task
def load(data_interval_start=None, data_interval_end=None):
    started = time.time()
    loaded_at = datetime.now(timezone.utc).isoformat()
    day = data_interval_start.date()
    elapsed = time.time() - started
    return {"day": str(day), "loaded_at": loaded_at, "elapsed": elapsed}
