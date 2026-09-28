# Databricks notebook source
# Bronze Ingestion Layer — Aircraft Maintenance Medallion Pipeline
# Ingests raw telemetry (streaming), API-staging telemetry (streaming),
# flights metadata (batch), and aircraft registry (batch) from the
# genie_zeroops_mfg_catalog.aircraft_maintenance source schema.

from pyspark import pipelines as dp
from pyspark.sql import functions as F

SOURCE_SCHEMA = "genie_zeroops_mfg_catalog.aircraft_maintenance"

# ---------------------------------------------------------------------------
# Streaming: Raw Flight Telemetry
# ---------------------------------------------------------------------------


@dp.table(
    name="bronze_raw_telemetry",
    comment="Raw flight telemetry streamed from the simulator",
)
@dp.expect_all_or_drop(
    {
        "valid_timestamp": "timestamp IS NOT NULL",
        "valid_flight_id": "flight_id IS NOT NULL",
        "valid_altitude": "altitude >= 0",
        "valid_oil_pressure_eng1": "oil_pressure_eng1 >= 0",
        "valid_oil_pressure_eng2": "oil_pressure_eng2 >= 0",
    }
)
def bronze_raw_telemetry():
    return spark.readStream.table(f"{SOURCE_SCHEMA}.raw_flight_telemetry")


# ---------------------------------------------------------------------------
# Streaming: API / Zerobus Staging Telemetry
# ---------------------------------------------------------------------------


@dp.table(
    name="bronze_staging_telemetry",
    comment="API/Zerobus-ingested telemetry records from staging",
)
@dp.expect_all_or_drop(
    {
        "valid_timestamp": "timestamp IS NOT NULL",
        "valid_flight_id": "flight_id IS NOT NULL",
        "valid_altitude": "altitude >= 0",
        "valid_oil_pressure_eng1": "oil_pressure_eng1 >= 0",
        "valid_oil_pressure_eng2": "oil_pressure_eng2 >= 0",
    }
)
def bronze_staging_telemetry():
    return (
        spark.readStream.table(f"{SOURCE_SCHEMA}.staging_flight_telemetry_api")
        .withColumn("anomaly_type", F.col("anomaly_type").cast("string"))
        .withColumn("anomaly_severity", F.col("anomaly_severity").cast("string"))
    )


# ---------------------------------------------------------------------------
# Batch: Flights Metadata
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="bronze_flights_metadata",
    comment="Flight-level metadata snapshot (one row per flight)",
)
@dp.expect("valid_flight_id", "flight_id IS NOT NULL")
def bronze_flights_metadata():
    return spark.read.table(f"{SOURCE_SCHEMA}.flights_metadata")


# ---------------------------------------------------------------------------
# Batch: Aircraft Registry
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="bronze_aircraft_registry",
    comment="Aircraft fleet registry snapshot (one row per tail number)",
)
@dp.expect("valid_tail_number", "tail_number IS NOT NULL")
def bronze_aircraft_registry():
    return spark.read.table(f"{SOURCE_SCHEMA}.aircraft_registry")
