# Execution Evidence

All components built and executed on Databricks workspace `fevm-genie-zeroops-mfg.cloud.databricks.com`.

## Data Simulator
- 1,000,000 telemetry rows, 1,005 flights, 328 aircraft, 10 airlines, 103 anomalous flights
- Cell outputs visible in notebook (9 of 10 cells)

## Lakeflow Pipeline
- Pipeline ID: `5bd5dac4-6cae-4af6-960d-056a266e7143`
- 10 datasets materialized:
  - bronze_raw_telemetry (1M+ rows)
  - bronze_staging_telemetry (16)
  - bronze_flights_metadata (1,000)
  - bronze_aircraft_registry (328)
  - silver_telemetry (16)
  - silver_enriched_telemetry (1M+)
  - gold_flight_summary (1,005)
  - gold_aircraft_health (310)
  - gold_anomaly_events (103)
  - gold_airline_operations (10)

## ML Models
- MLflow Experiment ID: 2720399061900241
- Binary GBT: Accuracy=0.945, F1=0.686, ROC-AUC=0.784, Precision=0.671, Recall=0.702
- Models: aircraft_anomaly_binary_classifier v2, aircraft_anomaly_type_classifier v2
- Predictions: 310 aircraft — CRITICAL:10, HIGH:24, MEDIUM:82, LOW:194

## Gold Metric Views
- fleet_operations_metrics: 1,005 rows (8 dims, 9 measures)
- aircraft_health_metrics: 310 rows (4 dims, 9 measures)
- anomaly_analysis_metrics: 103 rows (5 dims, 8 measures)

## Lakebase
- Instance: aircraft-maintenance-lakebase (CU_1, AVAILABLE)
- 5 synced tables ONLINE:
  - ml_maintenance_predictions_synced (310)
  - gold_flight_summary_synced (1,005)
  - gold_aircraft_health_synced (310)
  - gold_anomaly_events_synced (103)
  - gold_airline_operations_synced (10)

## Genie Agent
- Space: Aircraft Maintenance Intelligence (ID: 01f1a5f87b0b17719e85516055a09440)
- Tested: "How many aircraft are CRITICAL risk?" → 10 (correct)

## AI/BI Dashboard
- Dashboard ID: 01f1a5f8872c151b939582bfede572d6
- 4 pages, 5 datasets on Lakebase synced tables, published

## Databricks App
- URL: https://aircraft-maintenance-app-7474652206075893.aws.databricksapps.com
- Embedded dashboard + Genie chat with Chart.js visualizations

## Conversation ID
Thread ID: 617974576538052
