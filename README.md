# Parker Aerospace: Installed-Base Reliability & Warranty Intelligence

**Customer:** Parker Hannifin, Aerospace Group (Tier-1 component OEM: hydraulic actuators, fuel control valves, pneumatic valves, ECS controllers, sensors)  
**Industry position:** Parker builds the part, the airline operator and its MRO maintain it, and Parker pays (warranty claims, AOG spares, field-service dispatch, airframer reliability penalties) when it fails early. Parker sees operator service data late and in pieces.  
**Problem:** 9.8% of service events on Parker components carry a maintenance anomaly (missed intervals, false compliance flags, undocumented replacements, premature wear), and an anomaly goes undetected for ~37 days on average. Modelled warranty exposure on at-risk components is $8.5M.  
**Solution:** One governed Databricks platform that joins operator flight telemetry with Parker component service records, forecasts which components will generate a high-severity event next quarter, and gives engineers the fix (manual search) and a plain-English question box (Genie).

> All data is synthetic, modelled on Parker's aerospace portfolio. The 10 airlines are fictional operator customers.

## Who owns the numbers

| KPI | Owner (role) |
|---|---|
| Warranty cost and exposure, aftermarket P&L | VP Aftermarket & Customer Support, Parker Aerospace (economic buyer) |
| Program funding, payback, warranty reserve | VP Finance, Aerospace Group (funding sponsor) |
| Unscheduled removals, anomaly rate, MTBUR, CMM content | Director, Product Support Engineering (operational owner) |
| AOG events, field-service dispatch, operator service compliance | Director, Customer Support & Field Service |

These roles are also recorded on the tables as `parker.data_owner` properties (see `governance/uc_access_controls.sql`).

## Outcome (back-tested on Jun-Aug 2026)

| KPI (owner) | Before | After | Change |
|---|---|---|---|
| Quarterly exposure from HIGH/CRITICAL + warranty-risk events (VP Aftermarket) | $995K | $797K | **-20%** (~$791K/year avoided) |
| High-severity events found before they happen (Dir. Product Support Eng.) | 0 of 59 | 14 of 59 | **24% caught** from a 164-component visit list |
| Events carrying HIGH/CRITICAL AOG risk (Dir. Customer Support) | 54 | 46 | **-14%** |
| Payback (VP Finance) | | | **~4 months** at an assumed $250K/year run cost |

Assumption: 60% of caught events are converted to a planned repair by a proactive field-service visit. Source: `notebooks/Parker_Component_Failure_Forecast.ipynb` and `notebooks/Parker_Aerospace_Value_Deck.ipynb`. The deck has a financial pass (VP Finance / VP Aftermarket) and an operational pass (Product Support Engineering) of the value section.

## How this was built (workflow and AI tools)

**Workflow.** Everything was built inside the Databricks workspace with **Databricks Assistant (Genie Code)** as the main build tool. Each step ran in the same loop:
1. Describe the goal in plain English, for example "forecast which Parker components will have a high-severity event next quarter, with no leakage"
2. The assistant drafts the code, SQL, pipeline file, Genie configuration or slide
3. Run it against live Unity Catalog data and check the output against an independent query, not just "it ran"
4. Commit to this Git folder and push to GitHub

Round 2 used the same loop on the reviewer's feedback: audit the repo against each gap, agree a plan, then fix and verify each item.

| Layer | What the AI drafted | What I checked or decided |
|---|---|---|
| Synthetic data simulator | Parker component catalog, 6 maintenance-anomaly types with severity, delay and warranty correlations, operator skew | Realism profile (last simulator cell); kept the known weakness visible (overdue status does not raise anomaly risk) |
| Lakeflow pipelines | Bronze/silver/gold SDP code with data-quality expectations | Join keys and null handling; renamed the Parker registry only after tracing every dependency |
| ML forecast | Point-in-time features, future-window label, 5-fold stratified CV, MLflow logging, back-test | Rejected the earlier 0.999 AUC as leakage; chose top-decile capture as the business metric |
| Unity Catalog governance | Entitlement table, row filter, column mask, owner properties, lineage query | Ran it live, then confirmed visible rows per principal before committing |
| Genie space | Table instructions, filters, example SQL, benchmarks | Benchmarks pass (18 actuators; 164 visit-list components) |
| Databricks App | Flask routes, Genie polling, Vector Search manual tab | Starter questions match values that exist in the data |
| Value deck | python-pptx generator with every number queried live | Set the 60% intervention-success and $250K/year run-cost assumptions and stated them on the slides |
| Docs | README, evidence log, this section | Every number re-checked against the tables before commit |

**Where AI was the force multiplier**
- **Audit, fix and verify in one session.** The reviewer's six gaps were mapped to files, fixed and verified against live data in a single working session.
- **Catching its own mistake.** The assistant was asked to challenge the headline metric. It traced the 0.999 AUC to target leakage and rebuilt the model as an honest next-quarter forecast (AUC 0.60, 2.2x lift over random).
- **Governance as code.** Row filters, masks and grants were generated, run and verified in minutes, so access control is in the repo rather than described in prose.
- **Configuring and testing Genie.** The space's instructions, example SQL and benchmark questions were drafted and scored automatically.

**Where human judgment overrode the AI:** choosing Parker's real position in the value chain and the KPI owners by role; refusing to present the 0.999 AUC; setting the financial assumptions; approving renames and deletions only after a dependency check; deciding to report the simulator's weakness instead of hiding it.

The longer version, including the round-2 table, is in [`AI_BUILD_PROCESS.md`](AI_BUILD_PROCESS.md) and [`notebooks/00_Build_Process`](notebooks/).

## Architecture

```
Operator flight telemetry ─┐                                   ┌─> Next-quarter failure forecast (MLflow)
                           ├─> Lakeflow SDP (Bronze/Silver/Gold) ─> Unity Catalog ─┤
Parker service records  ───┘     + data-quality expectations    (comments, tags,  ├─> Lakebase synced tables ─> AI/BI Dashboard
                                                                 row filters,      ├─> Genie Agent (NL questions)
Manual PDFs (UC Volume) ─> ai_parse_document ─> chunks ─────────> column mask)     └─> Vector Search ─> Databricks App (Manual search)
```

## Build process and AI usage
See [`AI_BUILD_PROCESS.md`](AI_BUILD_PROCESS.md): the workflow, which AI tools were used at each step, where they made the biggest difference, and where human judgment overrode them (for example catching the 0.999-AUC leakage).

## Components

### 1. Data Simulator (`notebooks/Aircraft_Data_Simulator.ipynb`)
Two generators:
- **Parker installed base:** 1,640 Parker components on 328 aircraft at 10 operators, 9,839 service records over 18 months, 6 maintenance-anomaly types (`bronze_components_registry`, `bronze_maintenance_records`, `bronze_component_telemetry`, `bronze_parker_aircraft_registry`, `bronze_customer_registry`).
- **Operator flight telemetry:** 1.38M telemetry rows, 1,380 flights, 109 sensor parameters per reading, 10 flight-level anomaly types.

The final cell profiles realism: severity drives warranty and delay risk, each anomaly type has its own detection latency (false compliance flags ~62 days vs premature wear ~12), and edge cases (false compliance, undocumented replacement) are present. Known gap: overdue service does not yet raise anomaly risk, which caps the forecast's accuracy.

### 2. Lakeflow Medallion Pipeline (`pipeline/`)
Spark Declarative Pipeline: Bronze (4 tables) → Silver (2 tables) → Gold (4 tables). Target: `genie_zeroops_mfg_catalog.default`.

| Layer | Tables | Description |
|-------|--------|-------------|
| Bronze | `bronze_raw_telemetry`, `bronze_staging_telemetry`, `bronze_flights_metadata`, `bronze_aircraft_registry` | Raw ingestion with schema enforcement |
| Silver | `silver_telemetry`, `silver_enriched_telemetry` | Cleaned, deduplicated, enriched |
| Gold | `gold_flight_summary`, `gold_aircraft_health`, `gold_anomaly_events`, `gold_airline_operations` | Aggregated business KPIs |

Parker installed-base transformations (`pipeline_parker/`): `silver_enriched_maintenance` (compliance score, overdue days, warranty-risk flag, with expectations) -> `gold_component_health`, `gold_maintenance_compliance`, `gold_maintenance_anomalies`, `gold_customer_operations`.

**Parker pipeline status (2026-11-09).** The Parker medallion now runs in Lakeflow as "Parker Installed-Base Medallion Pipeline" (`ffb2c906-9499-4368-9468-42470e6048b7`, serverless), straight from the `pipeline_parker/` notebooks in this repo. Successful update: `524e3e3b-4d76-43e6-aea5-0de210e2d3a3`. It reads frozen simulator output from `genie_zeroops_mfg_catalog.parker_source` and publishes 10 materialized views to `genie_zeroops_mfg_catalog.default`: 5 bronze, `silver_enriched_maintenance`, and 4 gold. `gold_customer_operations` carries the `airline_row_filter` row filter, declared in the pipeline. These views replaced the earlier notebook-built tables, and each matches its predecessor exactly (same schema, same row count, 0 differing rows). The forecast, metric views, Lakebase synced tables, Genie and app were re-verified on them.

### 3. ML
**Component failure forecast (`notebooks/Parker_Component_Failure_Forecast.ipynb`), the model behind the business case**
- Question: which Parker components will have a HIGH/CRITICAL service event or warranty-risk event next quarter?
- Point-in-time features from service history before 2026-06-01. Label from 2026-06-01 to 2026-08-31. Stratified 5-fold CV, balanced weights, MLflow-tracked.
- Result: ROC-AUC 0.60. The top-decile list catches 22-24% of next-quarter events (2.2-2.4x random, vs 1.2x for a prior-history rule).
- An earlier part-failure model reported AUC 0.999. Its label (`failure_risk_category`) was a threshold on `health_index`, which was also an input, so this was target leakage. It was replaced, not tuned.
- Output: `ml_component_failure_forecast` (1,640 rows: probability, risk decile, expected warranty exposure, recommended action).

**Flight anomaly detection (`notebooks/Aircraft_Anomaly_Detection_Model.ipynb`)**
- Binary GBT (leaking `anomaly_record_count` removed, balanced weights), multi-class Random Forest, Isolation Forest
- Output: `ml_maintenance_predictions`, 320 aircraft (CRITICAL 23, HIGH 63, MEDIUM 127, LOW 107)
- Models in Unity Catalog: `aircraft_anomaly_binary_classifier`, `aircraft_anomaly_type_classifier`

### 4. Gold Metric Views (`notebooks/Gold_Layer_Metric_Views.ipynb`)
Six UC metric views. Operator telemetry: `fleet_operations_metrics`, `aircraft_health_metrics`, `anomaly_analysis_metrics`. Parker installed base: `component_health_metrics` (`gold_component_health`), `part_failure_metrics` (`ml_component_failure_forecast`, the leakage-free next-quarter forecast) and `maintenance_anomaly_metrics` (`gold_maintenance_anomalies`). `part_failure_metrics` used to read the retired leaky model and was repointed in place with `ALTER VIEW`. No view, dashboard or Genie space reads `ml_part_failure_predictions` now; its table comment marks it RETIRED.

### 5. Unity Catalog Governance (code in repo)
- `notebooks/UC_Governance.ipynb`: catalog, schema, table and column comments, `quality` = bronze/silver/gold tags on every table.
- `governance/uc_access_controls.sql`:
  - `parker.data_owner` / `parker.domain` table properties naming the accountable executive role. The workspace tag policy only allows the governed `quality` key, so these are properties, not tags.
  - `operator_entitlements` map plus the `airline_row_filter` row filter on `gold_customer_operations` and `ml_component_failure_forecast`: an operator's planners see only their own fleet, Parker staff see all.
  - `financial_mask` column mask on `expected_warranty_exposure_usd`: dollar figures only for principals with `can_see_financials`.
  - Least-privilege grants for the app service principal (read-only on the manual index, chunks and volume).
  - Verification queries plus a `system.access.table_lineage` query showing source-to-gold lineage.
- Data-quality expectations in every pipeline layer.

### 6. Lakebase (Operational Serving)
Instance `aircraft-maintenance-lakebase` (CU_1), SNAPSHOT synced tables:
- Parker installed base: `gold_component_health_synced` (1,640 rows) and `gold_maintenance_compliance_synced` (50 rows), matching their source tables
- Operator telemetry serving layer (feeds the airline dashboard pages): `gold_flight_summary_synced`, `gold_aircraft_health_synced`, `gold_anomaly_events_synced`, `gold_airline_operations_synced`, `ml_maintenance_predictions_synced`

`ml_component_failure_forecast` and `gold_customer_operations` are not synced on purpose. They carry the airline row filter (and the forecast carries the warranty-dollar mask), and Lakebase rejects synced tables whose source has row or column security ("cannot have both row/column security and online materialized views"). Governance was kept, so these two are served from Unity Catalog instead.

### 7. Genie Agent
"Aircraft Maintenance Intelligence": 13 tables.
- Parker installed base: `ml_component_failure_forecast`, `gold_component_health`, `gold_maintenance_compliance`, `gold_maintenance_anomalies`, `gold_customer_operations`
- Operator flight telemetry: `gold_flight_summary`, `gold_aircraft_health`, `gold_anomaly_events`, `gold_airline_operations`, `ml_maintenance_predictions`, plus 3 metric views
- Instructions say which table answers which kind of question (component forecast vs aircraft-level risk) and explain the airline row filter and warranty-$ mask
- Reusable filters (top risk decile, proactive visit list), an expected-exposure measure, joins and example SQL
- Starter questions include "Which Atlas Pacific hydraulic actuators are in the top risk decile next quarter?" and "Which components need a proactive field-service visit next quarter?"
- Benchmarks: both Parker benchmark questions pass (18 actuators; 164 visit-list components)

### 8. AI/BI Dashboard
First page **Parker Installed Base**, built on four local metric views over the Parker gold tables:
- counters: 1,640 components monitored, 164 components on the next-quarter proactive-visit list, and expected warranty exposure for the top risk decile
- expected warranty exposure by airline for the top risk decile (Atlas Pacific highest at about $558K)
- top-decile components by component type
- operator service compliance by airline and component type (compliance rate, average overdue days, SLA breach risk)
- service anomalies by type

Followed by the operator telemetry pages (Fleet Operations, Flight Phase Analysis, Aircraft Health & Maintenance, Anomaly Analysis, Airline Operations), mostly on Lakebase synced tables. Published with embedded credentials on 2026-10-29.

### 9. Databricks App (`app/`)
Flask app: embedded AI/BI dashboard + custom Genie chat with Chart.js visualizations (Bar/Donut/Line), query result polling, markdown-formatted responses. Aviation cockpit dark theme.
- **Maintenance Manuals tab**: engineers search the manual library by symptom, part name or part number (Vector Search, hybrid keyword + semantic), filter by aircraft type and system, and see the part, part number, limits, torque values and step-by-step corrective action. An "Ask Genie" button hands off to the Genie tab to find which aircraft currently have that fault.
- API routes: `/api/genie`, `/api/manuals/search`, `/api/manuals/facets`

### 10. Maintenance Manual Search (`notebooks/Maintenance_Manuals_Ingestion.ipynb`)
- 10 synthetic maintenance manuals (PDF), one per operator aircraft type. Each has a fault-isolation task for all 10 fleet fault codes, covering the systems where Parker supplies components: hydraulics (ATA 29), fuel (ATA 28), pneumatics/bleed (ATA 36) and wheels & brakes (ATA 32). Synthetic demo content, not OEM data.
- UC volume `default.maintenance_manuals` -> `ai_parse_document` (v2) -> `maintenance_manual_parsed` -> one chunk per task with part number, ATA chapter, system and fault code -> `maintenance_manual_chunks` (100 rows)
- Vector Search endpoint `aircraft-manuals-vs` + delta-sync index `maintenance_manual_index` (`databricks-gte-large-en`, triggered sync)

### 11. Fleet Data Skew Reprocessing (`notebooks/Fleet_Data_Skew_Reprocessing.ipynb`)
Backs up the raw sources, regenerates 1,380 flights with a realistic carrier story (SkyWest Global and Atlas Pacific worst and worsening Jul-Oct 2026, best-in-class carriers at ~3-4%), runs a full pipeline refresh, rebuilds `gold_anomaly_events_extended` and `ml_maintenance_predictions`, and re-syncs the Lakebase tables.

## Execution Evidence
See [`execution_evidence.md`](execution_evidence.md) for full run details, row counts, and model metrics.

## Catalog & Schema
- **Catalog**: `genie_zeroops_mfg_catalog`
- **Schema**: `default`

## How to Run
1. Run `notebooks/Aircraft_Data_Simulator.ipynb` to generate synthetic data
2. Create and run the Lakeflow pipeline using `pipeline/` notebooks
3. Run `notebooks/Aircraft_Anomaly_Detection_Model.ipynb` for ML training
4. Run `notebooks/Gold_Layer_Metric_Views.ipynb` to create metric views
5. Run `notebooks/Parker_Component_Failure_Forecast.ipynb`, then `notebooks/Parker_Aerospace_Value_Deck.ipynb` (writes the .pptx)
6. Run `notebooks/UC_Governance.ipynb` and `governance/uc_access_controls.sql`
7. Run `notebooks/Maintenance_Manuals_Ingestion.ipynb` to build the manual library and Vector Search index
8. (Optional) Run `notebooks/Fleet_Data_Skew_Reprocessing.ipynb` to apply the operator-telemetry demo story
9. Deploy `app/` as a Databricks App (the grants in step 6 give its service principal read access to the manual index)
