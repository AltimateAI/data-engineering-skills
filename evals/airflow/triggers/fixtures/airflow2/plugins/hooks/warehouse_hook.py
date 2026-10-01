from airflow.hooks.base import BaseHook


class WarehouseHook(BaseHook):
    """Thin wrapper around the warehouse connection."""

    def __init__(self, conn_id: str = "warehouse_default"):
        super().__init__()
        self.conn_id = conn_id

    def get_conn(self):
        conn = self.get_connection(self.conn_id)
        return {"host": conn.host, "schema": conn.schema, "login": conn.login}

    def run(self, sql: str) -> int:
        conn = self.get_conn()
        print(f"running on {conn['host']}: {sql}")
        return 0
