# Databricks notebook source
# DBTITLE 1,Bronze Ingestion - Parker Installed Base
# Bronze Ingestion Layer — Parker Installed-Base Medallion Pipeline
#
# Pipeline: "Parker Installed-Base Medallion Pipeline" (ffb2c906-9499-4368-9468-42470e6048b7)
# Publishes to genie_zeroops_mfg_catalog.default.
#
# Source: genie_zeroops_mfg_catalog.parker_source, the frozen output of the
# Aircraft_Data_Simulator (fictional MRO shop names, 2026-11-09). Bronze lands
# each source table with data-quality expectations.
#
# Five source tables:
#   - bronze_customer_registry   : Parker’s 10 airline customers
#   - bronze_parker_aircraft_registry : 328 aircraft across all customer fleets
#   - bronze_components_registry : 1,640 Parker components installed on aircraft
#   - bronze_maintenance_records : 9,839 historical maintenance logs
#   - bronze_component_telemetry : 1,640 current component health readings

from pyspark import pipelines as dp

SOURCE = "genie_zeroops_mfg_catalog.parker_source"


# ── Customer Registry ──────────────────────────────────────────────────────

@dp.materialized_view(
    name="bronze_customer_registry",
    comment="Parker airline customer master: 10 operators with hub and fleet size. Lakeflow output of the Parker Installed-Base Medallion Pipeline.",
)
@dp.expect_or_drop("valid_airline", "airline IS NOT NULL")
def bronze_customer_registry():
    return spark.read.table(f"{SOURCE}.bronze_customer_registry")


# ── Aircraft Registry ───────────────────────────────────────────────────────

@dp.materialized_view(
    name="bronze_parker_aircraft_registry",
    comment="Parker installed-base view of the 328 operator aircraft carrying Parker components (airframe age, flight hours, cycles). Distinct from the operator pipeline's bronze_aircraft_registry.",
)
@dp.expect_all_or_drop({
    "valid_tail": "tail_number IS NOT NULL",
    "valid_airline": "airline IS NOT NULL",
})
def bronze_parker_aircraft_registry():
    return spark.read.table(f"{SOURCE}.bronze_parker_aircraft_registry")


# ── Components Registry ───────────────────────────────────────────────────

@dp.materialized_view(
    name="bronze_components_registry",
    comment="1,640 Parker components (5 types) installed across the fleet. PK: component_id.",
)
@dp.expect_all_or_drop({
    "valid_component": "component_id IS NOT NULL",
    "valid_type":      "component_type IS NOT NULL",
    "valid_cycles":    "cycles_since_install >= 0",
})
def bronze_components_registry():
    return spark.read.table(f"{SOURCE}.bronze_components_registry")


# ── Maintenance Records ──────────────────────────────────────────────────

@dp.materialized_view(
    name="bronze_maintenance_records",
    comment="Component service history from MRO shops: 9,839 records over 18 months, 9.8 pct anomalous. PK: record_id.",
)
@dp.expect_all_or_drop({
    "valid_record":    "record_id IS NOT NULL",
    "valid_component": "component_id IS NOT NULL",
    "valid_date":      "maintenance_date IS NOT NULL",
})
def bronze_maintenance_records():
    return spark.read.table(f"{SOURCE}.bronze_maintenance_records")


# ── Component Telemetry (latest health snapshot) ────────────────────────

@dp.materialized_view(
    name="bronze_component_telemetry",
    comment="Current health reading per component: health_index, risk category, warranty exposure.",
)
@dp.expect_all_or_drop({
    "valid_component":  "component_id IS NOT NULL",
    "valid_health":     "health_index BETWEEN 0 AND 100",
    "valid_risk":       "failure_risk_category IN ('LOW','MEDIUM','HIGH','CRITICAL')",
})
def bronze_component_telemetry():
    return spark.read.table(f"{SOURCE}.bronze_component_telemetry")
