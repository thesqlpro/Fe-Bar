# Databricks notebook source
# Silver Enrichment Layer — Aircraft Maintenance Medallion Pipeline
# Unions raw + staging telemetry into one stream, enriches with aircraft
# registry and flight metadata, and computes derived health metrics.

from pyspark import pipelines as dp
from pyspark.sql import functions as F

# ---------------------------------------------------------------------------
# Unified Telemetry Stream (append flows from both bronze sources)
# ---------------------------------------------------------------------------

dp.create_streaming_table(
    name="silver_telemetry",
    comment="Unified telemetry stream combining raw and API-staging sources",
    expect_all_or_drop={
        "no_null_flight_id": "flight_id IS NOT NULL",
        "no_null_timestamp": "timestamp IS NOT NULL",
    },
)


@dp.append_flow(target="silver_telemetry", name="raw_telemetry_flow")
def raw_telemetry_flow():
    return spark.readStream.table("bronze_raw_telemetry")


@dp.append_flow(target="silver_telemetry", name="staging_telemetry_flow")
def staging_telemetry_flow():
    return spark.readStream.table("bronze_staging_telemetry")


# ---------------------------------------------------------------------------
# Enriched Telemetry (stream-static joins + derived metrics)
# ---------------------------------------------------------------------------


@dp.table(
    name="silver_enriched_telemetry",
    comment=(
        "Enriched telemetry with aircraft registry, flight metadata, "
        "and derived engine/hydraulic health metrics"
    ),
    cluster_by=["airline", "tail_number", "flight_id"],
)
@dp.expect_all(
    {
        "enrichment_has_aircraft_age": "aircraft_age_years IS NOT NULL",
        "enrichment_has_departure": "departure_time IS NOT NULL",
        "valid_engine_avg_egt": "engine_avg_egt >= 0",
        "valid_fuel_burn_rate": "fuel_burn_rate >= 0",
    }
)
def silver_enriched_telemetry():
    telemetry = spark.readStream.table("silver_telemetry")

    registry = spark.read.table("bronze_aircraft_registry").select(
        "tail_number",
        "aircraft_age_years",
        "total_flight_hours",
        "last_maintenance_date",
        "next_scheduled_maintenance",
    )

    metadata = spark.read.table("bronze_flights_metadata").select(
        "flight_id",
        "has_anomaly",
        "departure_time",
        "arrival_time",
    )

    enriched = telemetry.join(registry, "tail_number", "left").join(
        metadata, "flight_id", "left"
    )

    return enriched.withColumns(
        {
            "engine_avg_egt": (F.col("egt_eng1") + F.col("egt_eng2")) / 2,
            "engine_avg_vibration": (
                F.col("vibration_n1_eng1")
                + F.col("vibration_n1_eng2")
                + F.col("vibration_n2_eng1")
                + F.col("vibration_n2_eng2")
            )
            / 4,
            "fuel_burn_rate": F.col("fuel_flow_eng1") + F.col("fuel_flow_eng2"),
            "hydraulic_health_index": (
                (
                    F.least(
                        F.col("hyd_press_sys1"),
                        F.col("hyd_press_sys2"),
                        F.col("hyd_press_sys3"),
                    )
                    - F.lit(2600.0)
                )
                / F.lit(600.0)
            ),
        }
    )
