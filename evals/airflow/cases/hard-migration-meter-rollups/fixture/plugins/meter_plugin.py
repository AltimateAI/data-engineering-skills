"""Registers the metering template macros (``macros.meter.*``)."""

from airflow.plugins_manager import AirflowPlugin

from meter_lib.tariffs import invoice_batch, tariff_band


class MeterPlugin(AirflowPlugin):
    name = "meter"
    macros = [invoice_batch, tariff_band]
