# Databricks notebook source
# DBTITLE 1,Gold Aggregations - Parker Component Health
# Gold Aggregation Layer — Parker Installed-Base Medallion Pipeline
# Four materialized views for Parker's maintenance intelligence platform:
#   - gold_component_health       (one row per component, PK component_id)
#   - gold_maintenance_compliance (one row per airline + component type + criticality)
#   - gold_maintenance_anomalies  (one row per anomalous service record)
#   - gold_customer_operations    (one row per airline customer, operator row filter)
# The operator pipeline owns gold_flight_summary / gold_aircraft_health /
# gold_anomaly_events / gold_airline_operations; nothing here defines them.

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

ROW_FILTER = "ROW FILTER genie_zeroops_mfg_catalog.default.airline_row_filter ON (airline)"


# ── Component Health Scorecard ─────────────────────────────────────────────

@dp.materialized_view(
    name="gold_component_health",
    comment="Component-level health scorecard combining telemetry with aggregated maintenance history. Key: health index, failure risk, warranty exposure, anomaly counts.",
    cluster_by=["airline", "failure_risk_category"],
)
@dp.expect_or_fail("unique_component_grain", "component_id IS NOT NULL")
def gold_component_health():
    tel = spark.read.table("bronze_component_telemetry")
    comp = spark.read.table("bronze_components_registry")
    maint = spark.read.table("silver_enriched_maintenance")

    history = maint.groupBy("component_id").agg(
        F.count("*").alias("total_service_events"),
        F.sum(F.when(F.col("compliance_status") == "COMPLIANT", 1).otherwise(0)).alias("compliant_events"),
        F.sum(F.when(F.col("anomaly_flag"), 1).otherwise(0)).alias("anomaly_event_count"),
        F.sum("record_warranty_exposure_usd").alias("total_warranty_exposure_usd"),
        F.max("maintenance_date").alias("last_service_date"),
    )

    return (
        tel.join(comp.select("component_id", "description", "parker_division", "unit_cost_usd", "criticality"), "component_id", "left")
           .join(history, "component_id", "left")
           .select(
               "component_id", "component_type", "tail_number", "airline", "aircraft_type",
               "description", "parker_division", "criticality", "unit_cost_usd",
               "health_index", "cycles_since_install", "days_since_last_service",
               "days_until_next_service", "days_to_predicted_failure",
               "maintenance_compliance_rate", "failure_risk_category",
               "has_active_anomaly", "latest_anomaly_type",
               "estimated_warranty_exposure_usd", "reading_date",
               "total_service_events", "compliant_events", "anomaly_event_count",
               "total_warranty_exposure_usd", "last_service_date",
           )
    )


# ── Maintenance Compliance Summary ────────────────────────────────────────

@dp.materialized_view(
    name="gold_maintenance_compliance",
    comment="Maintenance compliance scorecard by airline, component type and criticality. Compliance rates, anomaly counts, warranty risk, SLA breach risk.",
    cluster_by=["airline"],
)
def gold_maintenance_compliance():
    maint = spark.read.table("silver_enriched_maintenance")
    return (
        maint.groupBy("airline", "component_type", "criticality").agg(
            F.count("*").alias("total_records"),
            F.avg("compliance_score").alias("avg_compliance_score"),
            F.sum(F.when(F.col("compliance_status") == "COMPLIANT", 1).otherwise(0)).alias("compliant_count"),
            F.sum(F.when(F.col("anomaly_flag"), 1).otherwise(0)).alias("anomaly_count"),
            F.sum(F.when(F.col("warranty_claim_risk"), 1).otherwise(0)).alias("warranty_risk_count"),
            F.sum("record_warranty_exposure_usd").alias("total_warranty_exposure_usd"),
            F.avg("overdue_days").alias("avg_overdue_days"),
            F.max("overdue_days").alias("max_overdue_days"),
        )
        .withColumn("compliance_rate", F.col("compliant_count") / F.col("total_records"))
        .withColumn(
            "sla_breach_risk",
            F.when(F.col("avg_compliance_score") < 0.80, F.lit("HIGH"))
             .when(F.col("avg_compliance_score") < 0.90, F.lit("MEDIUM"))
             .otherwise(F.lit("LOW")),
        )
    )


# ── Maintenance Anomalies Detail ──────────────────────────────────────────

@dp.materialized_view(
    name="gold_maintenance_anomalies",
    comment="All confirmed maintenance anomaly events (969) with severity, delay risk and warranty impact. For anomaly trend analysis and MRO quality auditing. MRO shop names are fictional.",
    cluster_by=["anomaly_type", "flight_delay_risk"],
)
def gold_maintenance_anomalies():
    return (
        spark.read.table("silver_enriched_maintenance")
        .filter("anomaly_flag = true")
        .select(
            "record_id", "component_id", "component_type", "tail_number", "airline",
            "maintenance_date", "maintenance_type", "mro_shop", "technician_cert",
            "anomaly_type", "anomaly_severity", "flight_delay_risk",
            "days_undetected", "compliance_status", "is_overdue", "overdue_days",
            "warranty_claim_risk", "record_warranty_exposure_usd",
            "criticality", "parker_division",
        )
    )


# ── Customer (Airline) Operations ─────────────────────────────────────────

@dp.materialized_view(
    name="gold_customer_operations",
    comment="Per-airline customer operations summary: fleet size, compliance rate, anomaly counts, warranty exposure. Row filter airline_row_filter limits operators to their own airline.",
    cluster_by=["airline"],
    row_filter=ROW_FILTER,
)
def gold_customer_operations():
    maint = spark.read.table("silver_enriched_maintenance")
    tel = spark.read.table("bronze_component_telemetry")
    customers = spark.read.table("bronze_customer_registry")

    maint_stats = maint.groupBy("airline").agg(
        F.count("*").alias("total_maintenance_events"),
        F.avg("compliance_score").alias("compliance_rate"),
        F.sum(F.when(F.col("anomaly_flag"), 1).otherwise(0)).alias("total_anomalies"),
        F.sum(F.when(F.col("warranty_claim_risk"), 1).otherwise(0)).alias("warranty_risk_events"),
        F.sum("record_warranty_exposure_usd").alias("total_warranty_exposure_usd"),
        F.countDistinct("component_id").alias("components_serviced"),
    )

    critical = (
        tel.filter("failure_risk_category = 'CRITICAL'")
        .groupBy("airline").agg(F.count("*").alias("critical_components"))
    )

    # Most common anomaly type per airline (ties broken alphabetically)
    top_anom = (
        maint.filter("anomaly_flag = true")
        .groupBy("airline", "anomaly_type").agg(F.count("*").alias("cnt"))
        .withColumn("_rn", F.row_number().over(
            Window.partitionBy("airline").orderBy(F.col("cnt").desc(), F.col("anomaly_type"))))
        .filter("_rn = 1")
        .select("airline", F.col("anomaly_type").alias("top_anomaly_type"))
    )

    return (
        customers
        .join(maint_stats, "airline", "left")
        .join(critical, "airline", "left")
        .join(top_anom, "airline", "left")
        .withColumn("critical_components", F.coalesce(F.col("critical_components"), F.lit(0)))
        .select(
            "airline", "hub", "fleet_size", "total_maintenance_events", "compliance_rate",
            "total_anomalies", "warranty_risk_events", "total_warranty_exposure_usd",
            "components_serviced", "critical_components", "top_anomaly_type",
        )
    )
