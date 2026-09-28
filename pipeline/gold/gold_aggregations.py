# Databricks notebook source
# Gold Aggregation Layer — Aircraft Maintenance Medallion Pipeline
# Produces four materialized views for predictive-maintenance analytics:
#   - gold_flight_summary      (one row per flight)
#   - gold_aircraft_health     (one row per tail number)
#   - gold_anomaly_events      (one row per anomaly occurrence)
#   - gold_airline_operations   (one row per airline)

from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ---------------------------------------------------------------------------
# Flight Summary
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="gold_flight_summary",
    comment="One row per flight with key operational and health metrics",
    cluster_by=["airline", "anomaly_type"],
)
def gold_flight_summary():
    df = spark.read.table("silver_enriched_telemetry")

    return df.groupBy(
        "flight_id",
        "airline",
        "aircraft_type",
        "tail_number",
        "origin",
        "destination",
        "departure_time",
        "arrival_time",
        "has_anomaly",
        "anomaly_type",
        "anomaly_severity",
    ).agg(
        (
            (
                F.unix_timestamp(F.max("timestamp"))
                - F.unix_timestamp(F.min("timestamp"))
            )
            / 3600
        ).alias("flight_duration_hours"),
        F.max("altitude").alias("max_altitude"),
        F.avg(
            F.when(F.col("flight_phase") == "CRUISE", F.col("indicated_airspeed"))
        ).alias("avg_cruise_speed"),
        F.sum("fuel_burn_rate").alias("total_fuel_burned"),
        F.max("egt_eng1").alias("max_egt_eng1"),
        F.max("egt_eng2").alias("max_egt_eng2"),
        F.greatest(
            F.max("vibration_n1_eng1"),
            F.max("vibration_n1_eng2"),
            F.max("vibration_n2_eng1"),
            F.max("vibration_n2_eng2"),
        ).alias("max_vibration"),
        F.avg("oil_pressure_eng1").alias("avg_oil_pressure_eng1"),
        F.avg("oil_pressure_eng2").alias("avg_oil_pressure_eng2"),
        F.min(
            F.least("hyd_press_sys1", "hyd_press_sys2", "hyd_press_sys3")
        ).alias("min_hydraulic_pressure"),
        F.count(F.when(F.col("anomaly_type").isNotNull(), 1)).alias(
            "anomaly_record_count"
        ),
    )


# ---------------------------------------------------------------------------
# Aircraft Health Scorecard
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="gold_aircraft_health",
    comment="Per-aircraft health scorecard for predictive maintenance prioritization",
    cluster_by=["airline"],
)
def gold_aircraft_health():
    flights = spark.read.table("gold_flight_summary")
    registry = spark.read.table("bronze_aircraft_registry")

    flight_stats = flights.groupBy("tail_number").agg(
        F.count("*").alias("total_flights"),
        F.sum(F.when(F.col("has_anomaly") == True, 1).otherwise(0)).alias(  # noqa: E712
            "anomaly_flight_count"
        ),
        F.greatest(
            F.avg("max_egt_eng1"), F.avg("max_egt_eng2")
        ).alias("avg_max_egt"),
        F.avg("max_vibration").alias("avg_max_vibration"),
        F.avg("min_hydraulic_pressure").alias("avg_min_hydraulic_pressure"),
        F.max("departure_time").alias("last_flight_date"),
    )

    health = flight_stats.join(registry, "tail_number", "left")

    return health.select(
        "tail_number",
        "airline",
        "aircraft_type",
        "aircraft_age_years",
        "total_flight_hours",
        "total_flights",
        "anomaly_flight_count",
        (F.col("anomaly_flight_count") / F.col("total_flights")).alias(
            "anomaly_rate"
        ),
        "avg_max_egt",
        "avg_max_vibration",
        "avg_min_hydraulic_pressure",
        "last_flight_date",
        F.datediff(F.current_date(), F.col("last_maintenance_date")).alias(
            "days_since_last_maintenance"
        ),
        F.datediff(F.col("next_scheduled_maintenance"), F.current_date()).alias(
            "days_until_next_maintenance"
        ),
        # Composite health risk score (0-100 scale):
        #   40% anomaly rate, 30% vibration severity, 30% hydraulic degradation
        (
            (F.col("anomaly_flight_count") / F.col("total_flights")) * 40
            + F.least(F.col("avg_max_vibration") / F.lit(4.0), F.lit(1.0)) * 30
            + (
                F.lit(1.0)
                - F.least(
                    F.col("avg_min_hydraulic_pressure") / F.lit(3200.0), F.lit(1.0)
                )
            )
            * 30
        ).alias("health_risk_score"),
    )


# ---------------------------------------------------------------------------
# Anomaly Events
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="gold_anomaly_events",
    comment="Detailed anomaly occurrence records for root-cause investigation",
    cluster_by=["anomaly_type", "anomaly_severity"],
)
def gold_anomaly_events():
    df = spark.read.table("silver_enriched_telemetry").filter(
        "anomaly_type IS NOT NULL"
    )

    # Identify the peak anomaly record per flight (highest EGT)
    w_peak = Window.partitionBy("flight_id", "anomaly_type").orderBy(
        F.col("engine_avg_egt").desc()
    )
    peaks = (
        df.withColumn("_rank", F.row_number().over(w_peak))
        .filter(F.col("_rank") == 1)
        .drop("_rank")
    )

    # Compute event boundaries per (flight, anomaly_type)
    event_bounds = df.groupBy("flight_id", "anomaly_type").agg(
        F.min("timestamp").alias("event_start_timestamp"),
        F.max("timestamp").alias("_event_end_timestamp"),
    )
    event_bounds = event_bounds.withColumn(
        "event_duration_seconds",
        (
            F.unix_timestamp("_event_end_timestamp")
            - F.unix_timestamp("event_start_timestamp")
        ).cast("double"),
    ).drop("_event_end_timestamp")

    return peaks.join(event_bounds, ["flight_id", "anomaly_type"]).select(
        "flight_id",
        "airline",
        "tail_number",
        "aircraft_type",
        "anomaly_type",
        "anomaly_severity",
        F.col("flight_phase").alias("flight_phase_at_peak"),
        F.col("engine_avg_egt").alias("peak_egt"),
        F.col("engine_avg_vibration").alias("peak_vibration"),
        F.least("oil_pressure_eng1", "oil_pressure_eng2").alias(
            "min_oil_pressure_during_event"
        ),
        "event_start_timestamp",
        "event_duration_seconds",
    )


# ---------------------------------------------------------------------------
# Airline Operations
# ---------------------------------------------------------------------------


@dp.materialized_view(
    name="gold_airline_operations",
    comment="Airline-level operational KPIs for fleet management",
    cluster_by=["airline"],
)
def gold_airline_operations():
    flights = spark.read.table("gold_flight_summary")
    registry = spark.read.table("bronze_aircraft_registry")

    # Average route duration for on-time proxy
    route_avg = flights.groupBy("origin", "destination").agg(
        F.avg("flight_duration_hours").alias("avg_route_duration")
    )
    flights_augmented = flights.join(route_avg, ["origin", "destination"], "left")
    flights_augmented = flights_augmented.withColumn(
        "is_on_time",
        F.when(
            F.abs(F.col("flight_duration_hours") - F.col("avg_route_duration"))
            <= F.col("avg_route_duration") * 0.10,
            1,
        ).otherwise(0),
    )

    ops = flights_augmented.groupBy("airline").agg(
        F.count("*").alias("total_flights"),
        F.sum("flight_duration_hours").alias("total_flight_hours"),
        F.sum(F.when(F.col("has_anomaly") == True, 1).otherwise(0)).alias(  # noqa: E712
            "anomaly_count"
        ),
        (
            F.sum(F.when(F.col("has_anomaly") == True, 1).otherwise(0))  # noqa: E712
            / F.count("*")
        ).alias("anomaly_rate"),
        (F.sum("is_on_time") / F.count("*")).alias("on_time_performance_proxy"),
    )

    fleet = registry.groupBy("airline").agg(
        F.countDistinct("tail_number").alias("fleet_size"),
        F.avg("aircraft_age_years").alias("avg_fleet_age"),
    )

    # Most frequent anomaly type per airline
    anomaly_counts = (
        flights.filter("anomaly_type IS NOT NULL")
        .groupBy("airline", "anomaly_type")
        .agg(F.count("*").alias("type_count"))
    )
    w_top = Window.partitionBy("airline").orderBy(F.col("type_count").desc())
    top_anomaly = (
        anomaly_counts.withColumn("_rank", F.row_number().over(w_top))
        .filter(F.col("_rank") == 1)
        .select("airline", F.col("anomaly_type").alias("top_anomaly_type"))
    )

    return (
        ops.join(fleet, "airline", "left")
        .join(top_anomaly, "airline", "left")
        .select(
            "airline",
            "total_flights",
            "total_flight_hours",
            "fleet_size",
            "anomaly_count",
            "anomaly_rate",
            "avg_fleet_age",
            "on_time_performance_proxy",
            "top_anomaly_type",
        )
    )
