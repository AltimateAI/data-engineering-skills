"""Datasets of the claims lake.

Claims land in one partition per service date. The intake attaches each
partition it touched to the ``claims-by-service-date`` alias, so consumers do
not need to know the partitions in advance.
"""

from __future__ import annotations

from airflow.datasets import Dataset, DatasetAlias

CLAIMS_BY_SERVICE_DATE = DatasetAlias("claims-by-service-date")
PROVIDERS = Dataset("lake://claims/providers")
PARTITION_PREFIX = "lake://claims/service_date="


def partition_dataset(service_date: str) -> Dataset:
    return Dataset(f"{PARTITION_PREFIX}{service_date}")


def partition_of(uri: str) -> str:
    """Service date of a partition dataset URI."""
    return uri[len(PARTITION_PREFIX):]
