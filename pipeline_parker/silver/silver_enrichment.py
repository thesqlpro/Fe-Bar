# Databricks notebook source
# DBTITLE 1,Silver Enrichment - Parker Component Compliance
# Silver Enrichment Layer — Parker Hannifin Component Maintenance Pipeline
# Enriches bronze maintenance records with component registry data,
# computes compliance scores, overdue flags, and anomaly risk signals.

from pyspark import pipelines as dp
from pyspark.sql import functions as F


# ── Enriched Maintenance Records (stream-static join) ───────────────────────
# Joins streaming maintenance records with static component and aircraft
# registry data, then derives compliance and risk signals.

@dp.table(
    name="silver_enriched_maintenance",
    comment=(
        "Maintenance records enriched with component specs and aircraft context. "
        "Adds overdue_days, compliance_score, and anomaly_risk_flag."
    ),
    cluster_by=["airline", "component_type"],
)
@dp.expect_all({
    "valid_record":       "record_id IS NOT NULL",
    "valid_component":    "component_id IS NOT NULL",
    "valid_health_pct":   "compliance_score BETWEEN 0.0 AND 1.0",
})
def silver_enriched_maintenance():
    records = spark.readStream.table("bronze_maintenance_records")

    components = spark.read.table("bronze_components_registry").select(
        "component_id", "component_type", "description", "parker_division",
        "maintenance_interval_days", "max_cycles", "unit_cost_usd", "criticality",
    )

    aircraft = spark.read.table("bronze_parker_aircraft_registry").select(
        "tail_number", "aircraft_type", "manufacture_year", "age_years",
        "total_flight_hours", "total_cycles",
    )

    enriched = (
        records
        .join(components, "component_id", "left")
        .join(aircraft,   "tail_number",   "left")
    )

    return enriched.withColumns({
        # How many days overdue is this service event?
        "overdue_days": F.greatest(
            F.col("days_since_last_service") - F.col("maintenance_interval_days"),
            F.lit(0),
        ),
        # Compliance score 0-1: penalises overdue events
        "compliance_score": F.when(
            F.col("compliance_status") == "COMPLIANT",
            F.lit(1.0) - F.least(
                F.col("days_since_last_service") / (F.col("maintenance_interval_days") * F.lit(1.5)),
                F.lit(1.0),
            ) * 0.2,
        ).otherwise(F.lit(0.0)),
        # Anomaly risk flag (true if this record carries a warranty-claim-level anomaly)
        "anomaly_risk_flag": (
            F.col("anomaly_flag") &
            F.col("anomaly_severity").isin("HIGH", "CRITICAL")
        ),
        # Estimated financial exposure for this record
        "record_warranty_exposure_usd": F.when(
            F.col("warranty_claim_risk"), F.col("unit_cost_usd")
        ).otherwise(F.lit(0)),
    })