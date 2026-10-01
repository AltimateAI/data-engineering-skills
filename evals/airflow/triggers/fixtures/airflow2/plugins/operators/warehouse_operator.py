from airflow.models import BaseOperator

from hooks.warehouse_hook import WarehouseHook


class WarehouseSqlOperator(BaseOperator):
    template_fields = ("sql",)

    def __init__(self, sql: str, conn_id: str = "warehouse_default", **kwargs):
        super().__init__(**kwargs)
        self.sql = sql
        self.conn_id = conn_id

    def execute(self, context):
        return WarehouseHook(self.conn_id).run(self.sql)
