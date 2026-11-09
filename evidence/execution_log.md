# Execution log (raw run output)

This file is the captured text output of `evidence/generate_execution_log.py`, a read-only script run against the live workspace `fevm-genie-zeroops-mfg.cloud.databricks.com`. Nothing below was typed by hand. The only edits were formatting: epoch timestamps converted to UTC, dollar amounts written with thousands separators, and the `|` inside vector-search chunk IDs escaped so the table renders. Re-running the committed script reproduces every table row. Section 9 is the captured output of two live Genie questions.

Run at 2026-11-09 19:04 UTC as `ayman.el-ghazali@databricks.com`

## 1. Parker installed-base tables (row counts)

| table | rows |
| --- | --- |
| bronze_customer_registry | 10 |
| bronze_parker_aircraft_registry | 328 |
| bronze_components_registry | 1,640 |
| bronze_maintenance_records | 9,839 |
| bronze_component_telemetry | 1,640 |
| silver_enriched_maintenance | 9,839 |
| gold_component_health | 1,640 |
| gold_maintenance_compliance | 50 |
| gold_maintenance_anomalies | 969 |
| gold_customer_operations | 10 |
| ml_component_failure_forecast | 1,640 |

## 2. Lakeflow pipeline runs

Added 2026-11-09 after the run above: the 10 tables in section 1 (all except `ml_component_failure_forecast`) are now materialized views owned by the Parker pipeline below. Their row counts are unchanged from section 1, re-checked live. An earlier Parker update, `4c52f614-4c03-44e6-9881-e02a976d5dbb`, also completed; the silver column order was fixed after it. Re-running `generate_execution_log.py` lists the Parker pipeline automatically.

| pipeline | pipeline_id | update_id | state | created (UTC) |
| --- | --- | --- | --- | --- |
| Parker Installed-Base Medallion Pipeline | ffb2c906-9499-4368-9468-42470e6048b7 | 524e3e3b-4d76-43e6-aea5-0de210e2d3a3 | COMPLETED | 2026-11-09 20:37:54 |
| Aircraft Maintenance Medallion Pipeline | 5bd5dac4-6cae-4af6-960d-056a266e7143 | e6e62197-7758-4651-84d0-23c0f90e9abd | COMPLETED | 2026-10-21 20:11:26 |
| Aircraft Maintenance Medallion Pipeline | 5bd5dac4-6cae-4af6-960d-056a266e7143 | a13ea315-8531-4328-adad-93a8453836bb | COMPLETED | 2026-10-21 20:03:28 |
| Aircraft Maintenance Medallion Pipeline | 5bd5dac4-6cae-4af6-960d-056a266e7143 | f28329ca-69ae-4055-b211-3a2f1240b08c | COMPLETED | 2026-10-21 19:50:05 |

## 3. Unity Catalog governance

| table | row filter |
| --- | --- |
| ml_component_failure_forecast | genie_zeroops_mfg_catalog.default.airline_row_filter |
| gold_customer_operations | genie_zeroops_mfg_catalog.default.airline_row_filter |

| table | column | mask |
| --- | --- | --- |
| ml_component_failure_forecast | expected_warranty_exposure_usd | genie_zeroops_mfg_catalog.default.financial_mask |

| principal | principal_type | airline | can_see_financials |
| --- | --- | --- | --- |
| ayman.el-ghazali@databricks.com | USER | * | True |
| operator_atlas_pacific | GROUP | Atlas Pacific | False |
| operator_skywest_global | GROUP | SkyWest Global | False |
| parker_aftermarket_leads | GROUP | * | True |
| parker_field_service | GROUP | * | False |

| table | tag | value |
| --- | --- | --- |
| bronze_component_telemetry | quality | bronze |
| bronze_components_registry | quality | bronze |
| bronze_customer_registry | medallion_layer | bronze |
| bronze_customer_registry | quality | bronze |
| bronze_maintenance_records | quality | bronze |
| bronze_parker_aircraft_registry | quality | bronze |
| gold_component_health | quality | gold |
| gold_customer_operations | quality | gold |
| gold_maintenance_anomalies | quality | gold |
| gold_maintenance_compliance | quality | gold |
| ml_component_failure_forecast | quality | gold |
| silver_enriched_maintenance | quality | silver |

| property (ml_component_failure_forecast) | value |
| --- | --- |
| parker.data_owner | VP Aftermarket and Customer Support |
| parker.domain | reliability |
| parker.sensitive_columns | expected_warranty_exposure_usd |

## 4. ML forecast (MLflow)

Experiment `2720399061900241`, run `6b20bf8b32c84774807ed160317fa799`, status FINISHED, run name `parker_next_quarter_forecast_logreg`

| metric | value |
| --- | --- |
| cv_pr_auc | 0.0543 |
| cv_roc_auc | 0.597 |
| cv_top_decile_capture | 0.2241 |
| rule_baseline_pr_auc | 0.0466 |
| rule_baseline_roc_auc | 0.5331 |
| rule_baseline_top_decile_capture | 0.1207 |

| param | value |
| --- | --- |
| cutoff | 2026-06-01 |
| cv | stratified 5-fold |
| label | HIGH/CRITICAL anomaly or warranty-claim-risk event in next quarter |
| model | logreg |
| n_features | 37 |

| n | top_decile | visits | events | components_with_event | events_in_top_decile | expected_exposure_usd | cutoff |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1640 | 164 | 164 | 59 | 58 | 14 | 10,164,136 | 2026-06-01 |

Top 5 components by forecast probability:

| component_id | airline | component_type | p | risk_decile | recommended_action |
| --- | --- | --- | --- | --- | --- |
| PH-AVS-N10046 | Atlas Pacific | AVIONICS_SENSOR | 0.993 | 10 | PROACTIVE_FIELD_SERVICE_VISIT |
| PH-AVS-N10265 | Continental Wings | AVIONICS_SENSOR | 0.971 | 10 | PROACTIVE_FIELD_SERVICE_VISIT |
| PH-AVS-N10017 | SkyWest Global | AVIONICS_SENSOR | 0.965 | 10 | PROACTIVE_FIELD_SERVICE_VISIT |
| PH-AVS-N10073 | Atlas Pacific | AVIONICS_SENSOR | 0.963 | 10 | PROACTIVE_FIELD_SERVICE_VISIT |
| PH-AVS-N10112 | Meridian Airlines | AVIONICS_SENSOR | 0.954 | 10 | PROACTIVE_FIELD_SERVICE_VISIT |

## 5. Metric views

| metric view | measure | value |
| --- | --- | --- |
| part_failure_metrics | Proactive-Visit Components | 164 |
| part_failure_metrics | Expected Warranty Exposure | 10,164,136 |
| component_health_metrics | Total Components | 1640 |
| maintenance_anomaly_metrics | Total Anomalies | 969 |

`part_failure_metrics` source line: `source: genie_zeroops_mfg_catalog.default.ml_component_failure_forecast`

## 6. Lakebase synced tables

| synced table | source rows | synced rows | state |
| --- | --- | --- | --- |
| gold_component_health_synced | 1,640 | 1,640 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| gold_maintenance_compliance_synced | 50 | 50 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| gold_flight_summary_synced | 1,384 | 1,384 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| gold_airline_operations_synced | 10 | 10 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| gold_aircraft_health_synced | 320 | 320 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| gold_anomaly_events_synced | 165 | 165 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |
| ml_maintenance_predictions_synced | 320 | 320 | SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE |

Instance `aircraft-maintenance-lakebase`: AVAILABLE, capacity CU_1

## 7. Vector Search over maintenance manuals

Query: `hydraulic actuator seal leak inspection`, top 3

| chunk_id | manual_name | source_path | aircraft_type | engine |
| --- | --- | --- | --- | --- |
| B767-300\|29-11-04 | B767-300_Maintenance_Manual.pdf | dbfs:/Volumes/genie_zeroops_mfg_catalog/default/maintenance_manuals/raw/B767-300 | B767-300 | GE CF6-80C2 |
| B787-9\|29-11-04 | B787-9_Maintenance_Manual.pdf | dbfs:/Volumes/genie_zeroops_mfg_catalog/default/maintenance_manuals/raw/B787-9_M | B787-9 | GEnx-1B |
| E190-E2\|29-11-04 | E190-E2_Maintenance_Manual.pdf | dbfs:/Volumes/genie_zeroops_mfg_catalog/default/maintenance_manuals/raw/E190-E2_ | E190-E2 | Pratt & Whitney PW1900G |

## 8. Databricks App and dashboard

App `aircraft-maintenance-app`: RUNNING, compute ACTIVE, deployment `01f1d3d49b30115483d12d0ee618b063` (SUCCEEDED)

Dashboard `Aircraft Predictive Maintenance Dashboard` published 2026-10-29T20:28:04Z. Pages: Parker Installed Base, Fleet Operations, Flight Phase Analysis, Aircraft Health & Maintenance, Global Filters, Anomaly Analysis, Airline Operations

## 9. Genie space benchmarks (live, 2026-11-09)

Space `Aircraft Maintenance Intelligence` (`01f1a5f87b0b17719e85516055a09440`)

**Q1.** "Which components need a proactive field-service visit next quarter? How many are there in total?" (conversation `01f1dc708b0d17a6b131792c50d75bf2`)

SQL Genie generated:

```sql
SELECT COUNT(DISTINCT component_id) AS total_components, COUNT(DISTINCT airline) AS airlines,
       ROUND(SUM(expected_warranty_exposure_usd), 0) AS total_expected_exposure_usd,
       MAX(forecast_cutoff_date) AS forecast_cutoff_date
FROM genie_zeroops_mfg_catalog.default.ml_component_failure_forecast
WHERE recommended_action = 'PROACTIVE_FIELD_SERVICE_VISIT'
```

| total_components | airlines | total_expected_exposure_usd | forecast_cutoff_date |
| --- | --- | --- | --- |
| 164 | 10 | 2,287,290 | 2026-06-01 |

Genie's answer: "164 components are flagged for a proactive field-service visit next quarter. They span 10 airlines and carry about $2.29M in expected warranty exposure. Atlas Pacific has the most, with 40 components. Continental Wings follows with 33, then TransOcean Air with 20 and SkyWest Global with 19." Expected 164: **pass**.

**Q2.** "How many Atlas Pacific actuators are in the top forecast risk decile?" (conversation `01f1dc708b10104e968740d682a11d8e`)

```sql
SELECT COUNT(DISTINCT component_id) AS n
FROM genie_zeroops_mfg_catalog.default.ml_component_failure_forecast
WHERE airline = 'Atlas Pacific' AND component_type = 'HYDRAULIC_ACTUATOR' AND risk_decile = 10
```

| n |
| --- |
| 18 |

Genie's answer: "18 Atlas Pacific hydraulic actuators are in the top forecast risk decile." Expected 18: **pass**.
