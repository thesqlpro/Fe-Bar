# Recreate prompt: Parker Aerospace installed-base reliability demo (FE Bar)

Paste everything below the line into Genie Code in the new workspace. Replace `<CATALOG>`, `<GITHUB_REPO_URL>` and `<HOME>` first. The expected values come from the original build (workspace `fevm-genie-zeroops-mfg`, 2026-11-09). With the same random seeds they should match exactly; otherwise treat them as targets and report differences.

---

## Goal

Build an end-to-end Databricks demo for **Parker Aerospace**, a Tier-1 aerospace OEM. Parker builds hydraulic actuators, fuel control valves, pneumatic valves, ECS controllers and avionics sensors. Airlines and their MRO shops maintain these parts, and Parker pays the warranty and AOG cost when a part fails early. The demo predicts which installed Parker components will have a high-severity event next quarter, so Field Service can visit them first.

It is an FE Bar submission. Requirements:
- **6 integrated stages:** Lakeflow pipelines, Unity Catalog governance, Lakebase, ML/GenAI, a Genie Agent, a Databricks App. Plus an AI/BI dashboard and metric views.
- **Execution evidence readable as text.** Committed notebook outputs, logged run output or query results in the repo. Source code alone fails the Build domain, and screenshots don't count.
- **Public GitHub repo.**
- **Deck as PDF, .txt or .md.**
- **Synthetic data only.** No real customer names, and no real MRO company names.

Store all artifacts under `<HOME>/FE Bar/`. The Git folder `<HOME>/FE Bar/FE-Bar-repo` (linked to `<GITHUB_REPO_URL>`, branch main) is the submission. Work in this loop for every component: draft the code, run it on live UC data, verify with an independent query, commit.

## 1. Synthetic data

**Parker installed base** (`notebooks/Aircraft_Data_Simulator.ipynb`, fixed `RANDOM_SEED`). Write it to a source schema `<CATALOG>.parker_source`:
- `bronze_customer_registry` (10 airlines with hub and fleet_size): SkyWest Global, Atlas Pacific, Northern Star Airways, Meridian Airlines, Falcon Jet Airways, TransOcean Air, Continental Wings, Horizon Express, Summit Aviation, Aurora Airlines
- `bronze_parker_aircraft_registry` (328 aircraft; tail_number, airline, aircraft_type, manufacture_year, age_years, total_flight_hours, total_cycles, base_hub)
- `bronze_components_registry` (1,640 components, 5 types; component_id, part_number, component_type, description, parker_division, tail_number, airline, aircraft_type, install_date, maintenance_interval_days, max_cycles, cycles_since_install, unit_cost_usd, criticality)
- `bronze_maintenance_records` (9,839 records, Mar 2025 to Aug 2026, about 9.8% anomalous). Columns: record_id, component_id, part_number, component_type, tail_number, airline, maintenance_date, maintenance_type, mro_shop, technician_cert, cycles_at_service, days_since_last_service, is_overdue, compliance_status, anomaly_flag, anomaly_type, anomaly_severity, days_undetected, flight_delay_risk, warranty_claim_risk. There are 6 anomaly types, including MISSED_MAINTENANCE_INTERVAL, premature wear and a false compliance flag. HIGH/CRITICAL anomalies carry warranty risk.
- `bronze_component_telemetry` (1 row per component). **health_index is on a 0-100 scale.** Other columns: days_to_predicted_failure (a simulated draw banded by health_index, not a model output), failure_risk_category (rule-based), has_active_anomaly, estimated_warranty_exposure_usd.
- **Fictional MRO shops only:** Parker Direct Service, Rhineland Aero Technik, EuroAtlantic MRO, Harbor Point Aero Services, Coastal Component Repair, Pinecrest Aviation Services, Third-Party Unlisted.

**Operator flight telemetry**, in schema `<CATALOG>.aircraft_maintenance`: raw_flight_telemetry (about 1.38M rows), staging_flight_telemetry_api, flights_metadata (1,380 flights), aircraft_registry (328). Add skew so there is a story: the anomaly rate runs from Summit Aviation 3.3% to SkyWest Global 20.9%, with Atlas Pacific about 18.9%, and it rises Jul-Oct 2026 for SkyWest and Atlas. Anomaly labels must be flight-wide.

## 2. Lakeflow pipelines (serverless SDP, Python, publish to `<CATALOG>.default`)

**A. Operator pipeline** "Aircraft Maintenance Medallion Pipeline" (`pipeline/`):
- bronze_raw_telemetry, bronze_staging_telemetry, bronze_flights_metadata, bronze_aircraft_registry
- silver_telemetry, silver_enriched_telemetry
- gold_flight_summary (groups by anomaly_type), gold_aircraft_health, gold_anomaly_events (flight_phase_at_peak = phase of max engine_avg_egt), gold_airline_operations

**B. Parker pipeline** "Parker Installed-Base Medallion Pipeline" (`pipeline_parker/bronze|silver|gold`). All datasets are materialized views. Run it directly from the Git folder notebooks.
- **Bronze:** 5 MVs, one per `parker_source` table, same names, with expectations: not-null keys, cycles >= 0, health_index BETWEEN 0 AND 100, risk category in LOW/MEDIUM/HIGH/CRITICAL.
- **Silver `silver_enriched_maintenance`:** left-join records to the components registry (description, parker_division, maintenance_interval_days, max_cycles, unit_cost_usd, criticality) and to the aircraft registry (aircraft_type, manufacture_year, age_years, total_flight_hours). Then add:
  - overdue_days = greatest(days_since_last_service - maintenance_interval_days, 0)
  - compliance_score: use this SQL expression to get the DECIMAL type: `CASE WHEN compliance_status='COMPLIANT' THEN 1.0 - least(days_since_last_service/(maintenance_interval_days*1.5),1.0)*0.2 ELSE 0.0 END`
  - anomaly_risk_flag = anomaly_flag AND severity in HIGH/CRITICAL
  - record_warranty_exposure_usd = unit_cost_usd if warranty_claim_risk else 0

  Keep the source column order with an explicit final select, because USING joins move the key columns to the front.
- **Gold:**
  - gold_component_health: telemetry + registry + per-component history (total_service_events, compliant_events, anomaly_event_count, total_warranty_exposure_usd, last_service_date)
  - gold_maintenance_compliance, grouped by airline, component_type, criticality: total_records, avg_compliance_score, compliant_count, anomaly_count, warranty_risk_count, total_warranty_exposure_usd, avg/max overdue_days, compliance_rate = compliant/total, and sla_breach_risk (<0.80 HIGH, <0.90 MEDIUM)
  - gold_maintenance_anomalies: anomaly rows only
  - gold_customer_operations: per airline, with `row_filter="ROW FILTER <CATALOG>.default.airline_row_filter ON (airline)"`. Top anomaly type ties are broken alphabetically. **Name the averaged score `avg_compliance_score`, not `compliance_rate`.** In the original build both gold tables published `compliance_rate` with different meanings.
- **Do not** define alias views with the operator pipeline's gold names (gold_flight_summary etc.). Use `bronze_parker_aircraft_registry`, never `bronze_aircraft_registry`, on the Parker side.
- Expected counts: 10 / 328 / 1,640 / 9,839 / 1,640 / 9,839 / 1,640 / 50 / 969 / 10.

## 3. Unity Catalog governance (`governance/uc_access_controls.sql`, `notebooks/UC_Governance.ipynb`)

- Table `operator_entitlements` (principal, principal_type, airline, can_see_financials). Rows:
  - me: USER, *, true
  - operator_atlas_pacific: GROUP, Atlas Pacific, false
  - operator_skywest_global: GROUP, SkyWest Global, false
  - parker_aftermarket_leads: GROUP, *, true
  - parker_field_service: GROUP, *, false
- SQL UDF `airline_row_filter(airline)` and column mask `financial_mask`, both driven by that table.
- Row filter on gold_customer_operations and ml_component_failure_forecast. Mask on `ml_component_failure_forecast.expected_warranty_exposure_usd`.
- Tags `quality=bronze|silver|gold` on all medallion tables. On the forecast table, properties `parker.data_owner`, `parker.domain` and `parker.sensitive_columns`. Table and column comments everywhere.
- After every pipeline run, re-apply tags and GRANT SELECT to the app service principal. Grant USE CATALOG/SCHEMA and READ VOLUME too.

## 4. ML and GenAI

**Parker forecast** (`notebooks/Parker_Component_Failure_Forecast.ipynb`, MLflow run name `parker_next_quarter_forecast_logreg`):
- Label: a HIGH/CRITICAL anomaly or warranty-risk event in the quarter after cutoff 2026-06-01.
- Point-in-time features only, 37 features.
- Logistic regression, stratified 5-fold CV. Compare against GBT and a "prior HIGH/CRITICAL history" rule.
- Target metrics: cv_roc_auc about 0.597, cv_pr_auc 0.054, cv_top_decile_capture 0.224. Rule baseline: 0.533 / 0.121.
- Output `ml_component_failure_forecast` (1,640 rows): forecast_probability, risk_decile, recommended_action (PROACTIVE_FIELD_SERVICE_VISIT for the top decile = 164), expected_warranty_exposure_usd (about $10.16M total), actual_next_quarter_event, n_future_events (59 events on 58 components, 14 in the top decile), forecast_cutoff_date.
- **Leakage rule:** never predict a health_index threshold label using health_index as a feature. The original first model had AUC 0.999 from exactly that. Retire it and document it.

**Operator model:** GBT anomaly classifiers on flight telemetry (aircraft_anomaly_binary_classifier, aircraft_anomaly_type_classifier). Output `ml_maintenance_predictions` (320 aircraft).

**Maintenance manuals RAG** (`notebooks/Maintenance_Manuals_Ingestion.ipynb`):
- 10 synthetic maintenance-manual PDFs in volume `maintenance_manuals/raw`
- `ai_parse_document` produces `maintenance_manual_parsed`, then `maintenance_manual_chunks` (100 chunks)
- Vector Search endpoint `aircraft-manuals-vs` with a delta-sync index `maintenance_manual_index` (databricks-gte-large-en, TRIGGERED)

## 5. Metric views (`notebooks/Gold_Layer_Metric_Views.ipynb`)

- **Parker:**
  - `component_health_metrics` on gold_component_health. Label days_to_predicted_failure as simulated, failure_risk_category as rule-based, and health_index as 0-100.
  - `part_failure_metrics` on ml_component_failure_forecast: Total Components, Proactive-Visit Components, Top-Decile, "Actual Events in Forecast Quarter (back-test only)", and Expected Warranty Exposure in USD with a comment noting the mask and row filter.
  - `maintenance_anomaly_metrics` on gold_maintenance_anomalies.
- **Operator:** fleet_operations_metrics, aircraft_health_metrics, anomaly_analysis_metrics.
- Re-runs use ALTER VIEW so grants are kept. **No semicolons in YAML comments**, because the cell runner splits statements on them.
- Final validation cell asserts the expected values (1,640 / 164 / 164 / 969) and fails with a named error if any differ.

## 6. Lakebase

- Instance `aircraft-maintenance-lakebase`, CU_1, logical database `databricks_postgres`.
- SNAPSHOT synced tables:
  - gold_component_health_synced (PK component_id)
  - gold_maintenance_compliance_synced (PK airline, component_type, criticality)
  - gold_flight_summary_synced, gold_aircraft_health_synced, gold_anomaly_events_synced, gold_airline_operations_synced, ml_maintenance_predictions_synced
- Tables with row filters or masks **cannot** be synced (forecast, customer_operations). Serve those from UC and document it.
- Deleting a synced table leaves its Postgres table behind. Drop that table before you re-create the sync.

## 7. Genie Agent "Aircraft Maintenance Intelligence"

Add the Parker gold tables, the forecast and the metric views, plus the operator gold tables. Benchmarks that must pass:
- "Which components need a proactive field-service visit next quarter? How many are there in total?" should return 164 (10 airlines, about $2.29M exposure; Atlas Pacific has 40)
- "How many Atlas Pacific actuators are in the top forecast risk decile?" should return 18

## 8. AI/BI dashboard "Aircraft Predictive Maintenance Dashboard"

7 pages, published with embedded credentials:
1. Parker Installed Base: first page, on local metric-view datasets over the Parker gold tables and forecast
2. Fleet Operations
3. Flight Phase Analysis
4. Aircraft Health & Maintenance
5. Global Filters
6. Anomaly Analysis
7. Airline Operations

The operator pages read the Lakebase synced tables.

## 9. Databricks App `aircraft-maintenance-app` (Flask; `app/main.py`, `app.yaml`, `requirements.txt`)

Parker-branded, with:
- the embedded dashboard
- Genie chat with Chart.js charts, starter question "Which components need a proactive field-service visit next quarter?"
- a Maintenance Manuals tab using Vector Search (`/api/manuals/search`, `/api/manuals/facets`)

Grant the app service principal its UC privileges.

## 10. Customer deck (`deck/Parker_Aerospace_Value_Deck.pptx`, built by `notebooks/Parker_Aerospace_Value_Deck.ipynb` from live tables)

11 slides:
1. Title, with buyers: VP Aftermarket & Customer Support, Director Product Support Engineering
2. Parker's value-chain position
3. KPI owners by role
4. Current state: 1,640 components, 9,839 records, 9.8% anomalous, 37 days undetected, $8.53M exposure, 59 events/$995K per quarter
5. What we built
6. Back-test lift: random 1.0x, rule 1.2x, forecast 2.4x (14 of 59), AUC 0.60, plus the leakage disclosure
7. Before/after: $995K becomes $797K (-20%), AOG-risk events 54 become 46, 164 visits per quarter. Assumes 60% intervention success
8. Financial case: $198K/quarter, about $791K/year, payback about 4 months at $250K/year run cost
9. Operational case
10. 90-day pilot with success gates
11. Appendix: how it was built with Genie Code

Also export `deck/Parker_Aerospace_Value_Deck.md` (all slide text and tables) and a PDF (LibreOffice headless), stored in a UC volume.

## 11. Documentation and evidence in the repo

- `README.md`: customer, problem, KPI owners, outcome, a "How this was built" section, architecture, Parker pipeline status
- `AI_BUILD_PROCESS.md` and `notebooks/00_Build_Process.ipynb`: workflow, where AI was used, force multipliers, where human judgment overrode the AI. Name only Databricks Assistant (Genie Code).
- `evidence/generate_execution_log.py` (read-only script) and `evidence/execution_log.md` (its captured output). The log covers: table counts, pipeline update IDs and states, row filters, masks, entitlements, tags, properties, MLflow metrics and params, forecast summary and top 5, metric-view measures, Lakebase sync states and counts, a vector-search result, app and dashboard status, plus the two Genie benchmarks with their SQL and answers.
- `execution_evidence.md`: summary of the above
- `REVIEW_vs_REQUIREMENTS.md`: self-review against the brief
- `<HOME>/FE Bar/START_HERE.md`: reading order and the final commit hash

## Final verification (report every item)

1. Both pipelines' latest updates are COMPLETED, and the 10 Parker tables are MATERIALIZED_VIEW with the counts above.
2. No real MRO names in any table or file (grep the repo).
3. Row filter, mask, tags and app SP grants are present.
4. The metric-view validation cell passes, and the forecast has 1,640 rows with 164 in the top decile.
5. All Lakebase synced tables are ONLINE, with Postgres counts equal to the source.
6. Both Genie benchmarks pass, and the dashboard's Parker datasets query without errors.
7. The app is RUNNING.
8. The Git folder is clean and GitHub main equals the local head.

## Known follow-ups from code review (fix while rebuilding)

- Use warn or fail expectations in bronze instead of drop, so record counts can't change silently.
- Add a "component matched" expectation after silver's left joins.
- Rename the gold `unique_component_grain` check, or add a real uniqueness check.
- Reconcile `is_overdue` with `overdue_days`. In the original data, 560 records disagree.
- Fix the source health_index column comment to say 0-100 (it says 0.0-1.0).
