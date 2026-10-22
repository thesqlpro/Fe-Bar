# Execution Evidence

All components built and executed on Databricks workspace `fevm-genie-zeroops-mfg.cloud.databricks.com`.

Last refreshed: 2026-10-22.

## Parker installed base (synthetic)
- 1,640 Parker components, 328 aircraft (`bronze_parker_aircraft_registry`), 10 operator customers, 9,839 service records (Mar 2025 to Aug 2026)
- 9.8% of service events anomalous, ~37 days average detection latency, $8.5M modelled warranty exposure, 280 components CRITICAL by health index
- Gold: `gold_component_health` (1,640), `gold_maintenance_compliance` (50), `gold_maintenance_anomalies` (969), `gold_customer_operations` (10)
- Realism profile (last cell of the simulator): HIGH/CRITICAL anomalies carry 100% warranty risk and ~80% high delay risk. Detection latency by type ranges from 12 days (premature wear) to 62 days (false compliance flag). Overdue vs on-time anomaly rate is 9.2% vs 10.0%, so there is no uplift (known limitation).

## Component failure forecast
- Notebook: `notebooks/Parker_Component_Failure_Forecast.ipynb`, MLflow experiment 2720399061900241, run `6b20bf8b32c84774807ed160317fa799` (logistic regression)
- Cutoff 2026-06-01. Next-quarter event rate 3.5% (58 components)
- Stratified 5-fold CV: logreg ROC-AUC 0.597, PR-AUC 0.054, top-decile capture 22.4% (2.24x). GBT 0.578 / 15.5%. Prior-history rule 0.533 / 12.1%. Seed robustness for logreg: AUC 0.59-0.64, capture 17-22%
- Back-test on the 59 events of Jun-Aug 2026: 14 caught by the 164-component top decile, $330K exposure caught, $198K avoided at 60% intervention success (~$791K/year), AOG-risk events 54 -> 46
- Output: `ml_component_failure_forecast` (1,640 rows)
- Leakage finding: the earlier `ml_part_failure_predictions` model (AUC 0.999) used `health_index` as a feature while its label `failure_risk_category` is a `health_index` threshold (LOW >= 70). It is kept only for the existing `part_failure_metrics` view and is not cited.

## Unity Catalog access controls (`governance/uc_access_controls.sql`)
- Row filter `airline_row_filter` on `gold_customer_operations` and `ml_component_failure_forecast`. Verified: the platform owner sees 10 of 10 operators and 1,640 of 1,640 forecast rows. Under the entitlement map, the `operator_skywest_global` group resolves to SkyWest Global only
- Column mask `financial_mask` on `ml_component_failure_forecast.expected_warranty_exposure_usd`
- Owner properties `parker.data_owner` on 6 tables. `quality` tags on all medallion tables
- Parker registry renamed `bronze_aircraft_registry_old_managed` -> `bronze_parker_aircraft_registry` to stop it clashing with the operator pipeline MV. All downstream Parker tables and metric views were re-verified

## Operator flight telemetry simulator
- 1,379,010 telemetry rows, 1,380 flights, 328 aircraft, 10 airlines
- Anomaly rate by operator ranges from 3.3% (Summit Aviation) to 20.9% (SkyWest Global), rising Jul-Oct 2026 for SkyWest and Atlas Pacific

## Lakeflow Pipeline
- Pipeline ID: `5bd5dac4-6cae-4af6-960d-056a266e7143`
- 10 datasets materialized:
  - bronze_raw_telemetry (1.38M rows)
  - bronze_staging_telemetry (16)
  - bronze_flights_metadata (1,380)
  - bronze_aircraft_registry (328, materialized view)
  - silver_enriched_telemetry (1.38M)
  - gold_flight_summary (1,384)
  - gold_aircraft_health (320)
  - gold_anomaly_events (165), plus gold_anomaly_events_extended (219, adds LANDING phase)
  - gold_airline_operations (10)

## ML Models
- MLflow Experiment ID: 2720399061900241
- Flight anomaly binary GBT (original run): Accuracy=0.945, F1=0.686, ROC-AUC=0.784, Precision=0.671, Recall=0.702
- Models: aircraft_anomaly_binary_classifier, aircraft_anomaly_type_classifier
- Predictions after reprocessing: 320 aircraft (CRITICAL 23, HIGH 63, MEDIUM 127, LOW 107)

## Gold Metric Views
- fleet_operations_metrics (8 dims, 9 measures), aircraft_health_metrics (4 dims, 9 measures), anomaly_analysis_metrics (5 dims, 8 measures), built over the operator gold tables (row counts above)
- component_health_metrics (1,640), part_failure_metrics (1,640), maintenance_anomaly_metrics (969), built over the Parker gold tables

## Lakebase
- Instance: aircraft-maintenance-lakebase (CU_1, AVAILABLE)
- 5 synced tables ONLINE:
  - ml_maintenance_predictions_synced (320)
  - gold_flight_summary_synced (1,384)
  - gold_aircraft_health_synced (320)
  - gold_anomaly_events_synced (165)
  - gold_airline_operations_synced (10)

## Maintenance manual search
- 10 PDFs in UC Volume `maintenance_manuals` -> `maintenance_manual_parsed` -> `maintenance_manual_chunks` (100 tasks)
- Vector Search endpoint `aircraft-manuals-vs`, delta-sync index `maintenance_manual_index` (`databricks-gte-large-en`)

## Genie Agent
- Space: Aircraft Maintenance Intelligence (ID: 01f1a5f87b0b17719e85516055a09440)
- Tested (original run): "How many aircraft are CRITICAL risk?" -> 10 (correct at the time of that run; the reprocessed `ml_maintenance_predictions` now holds 23 CRITICAL aircraft)

## AI/BI Dashboard
- Dashboard ID: 01f1a5f8872c151b939582bfede572d6
- 4 pages, 5 datasets on Lakebase synced tables, published

## Databricks App
- URL: https://aircraft-maintenance-app-7474652206075893.aws.databricksapps.com
- Parker-branded: embedded dashboard, Genie chat with Chart.js visualizations, Maintenance Manuals search tab (`/api/manuals/search`, `/api/manuals/facets`)

## Conversation ID
Thread ID: 617974576538052
