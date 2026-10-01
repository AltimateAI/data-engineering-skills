# partner-pipelines

Airflow 3.3 DAGs that ingest our partners' daily file drops.

- `dags/partners/` — `ManifestHook` and `PartnerManifestSensor`.
- `dags/partner_ingest.py` — the daily ingest DAG.
- `tools/manifest_stub.py` — local stand-in for the manifest API (run it with `--help`).

## Manifest API

Connection `manifests_default` (type `http`): `host`, `port`, `schema` = URL scheme,
`password` = bearer token.

`GET /v1/partners/<partner>/manifests/<ds>` answers `200 {"status": "PENDING"}` or
`200 {"status": "PUBLISHED", "files": [...]}`. A published manifest never changes.
The API takes about a second per call and has short outages (`503`) a few times a week.

## Local development

```bash
python tools/manifest_stub.py --publish-after 20 &   # prints its port
export AIRFLOW_CONN_MANIFESTS_DEFAULT='{"conn_type": "http", "host": "127.0.0.1", "port": <port>, "password": "eval-manifest-token"}'
```
