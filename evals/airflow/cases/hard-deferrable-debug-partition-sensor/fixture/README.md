# lake-pipelines

Airflow 3.3 DAGs that load data-lake partitions once the catalog marks them published.

- `dags/lake/` — `LakeCatalogHook`, `PartitionPublishedTrigger`, `PartitionPublishedSensor`.
- `dags/lake_ingest.py`, `dags/orders_diff.py` — the DAGs using the sensor.
- `tools/catalog_stub.py` — local stand-in for the catalog API (run it with `--help`).

## Catalog API

Connection `lake_default` (type `http`): `host`, `port`, `schema` = URL scheme,
`password` = bearer token.

`GET /v1/tables/<table>/partitions/<partition>` answers
`200 {"state": "PENDING"}` or `200 {"state": "PUBLISHED", "files": [...]}`.
Published partitions never change. Under load the API takes 1-2 s per call and
sometimes answers `503`.

## Local development

```bash
python tools/catalog_stub.py --publish orders/2026-09-29=0 &   # prints its port
export AIRFLOW_CONN_LAKE_DEFAULT='{"conn_type": "http", "host": "127.0.0.1", "port": <port>, "password": "eval-lake-token"}'
airflow dags test lake_ingest 2026-09-29
```
