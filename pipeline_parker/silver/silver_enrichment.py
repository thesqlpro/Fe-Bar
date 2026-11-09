# Databricks notebook source
# DBTITLE 1,Silver Enrichment - Parker Component Compliance
# Silver Enrichment Layer — Parker Installed-Base Medallion Pipeline
# Enriches bronze maintenance records with component registry and aircraft
# data, then derives compliance score, overdue days, anomaly risk flag and
# record-level warranty exposure.

from pyspark import pipelines as dp
from pyspark.sql import functions as F


@dp.materialized_view(
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
    records = spark.read.table("bronze_maintenance_records")

    components = spark.read.table("bronze_components_registry").select(
        "component_id", "description", "parker_division",
        "maintenance_interval_days", "max_cycles", "unit_cost_usd", "criticality",
    )

    aircraft = spark.read.table("bronze_parker_aircraft_registry").select(
        "tail_number", "aircraft_type", "manufacture_year", "age_years",
        "total_flight_hours",
    )

    # Keep the source record column order first (joins on a USING key move it to the front)
    column_order = (
        records.columns
        + [c for c in components.columns if c != "component_id"]
        + [c for c in aircraft.columns if c != "tail_number"]
        + ["overdue_days", "compliance_score", "anomaly_risk_flag", "record_warranty_exposure_usd"]
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
        # Compliance score 0-1: COMPLIANT events lose up to 0.2 as they approach
        # 1.5x the service interval; non-compliant events score 0.
        # SQL expression keeps the exact DECIMAL type used downstream.
        "compliance_score": F.expr(
            "CASE WHEN compliance_status = 'COMPLIANT' "
            "THEN 1.0 - least(days_since_last_service / (maintenance_interval_days * 1.5), 1.0) * 0.2 "
            "ELSE 0.0 END"
        ),
        # Anomaly risk flag (true if this record carries a warranty-claim-level anomaly)
        "anomaly_risk_flag": (
            F.col("anomaly_flag") &
            F.col("anomaly_severity").isin("HIGH", "CRITICAL")
        ),
        # Estimated financial exposure for this record
        "record_warranty_exposure_usd": F.when(
            F.col("warranty_claim_risk"), F.col("unit_cost_usd")
        ).otherwise(F.lit(0)),
    }).select(*column_order)