"""Datasets of the claims lake.

Claims land in one partition per service date. The intake attaches each
partition it touched to the ``claims-by-service-date`` alias, so consumers do
not need to know the partitions in advance.
"""

from __future__ import annotations

from airflow.sdk import Asset, AssetAlias

CLAIMS_BY_SERVICE_DATE = AssetAlias("claims-by-service-date")
PROVIDERS = Asset("lake://claims/providers")
PARTITION_PREFIX = "lake://claims/service_date="


def partition_dataset(service_date: str) -> Asset:
    return Asset(f"{PARTITION_PREFIX}{service_date}")


def partition_of(uri: str) -> str:
    """Service date of a partition dataset URI."""
    return uri[len(PARTITION_PREFIX):]
