# Aircraft Predictive Maintenance Intelligence

**Industry:** Aviation / MRO (Maintenance, Repair, Overhaul)  
**Problem:** Airlines lose ~$150K per hour of unplanned aircraft grounding. Reactive maintenance leads to safety risks, flight delays, and excessive costs.  
**Solution:** End-to-end predictive maintenance platform on Databricks that detects anomalies, scores aircraft health risk, and surfaces actionable intelligence to operations teams.

## Architecture

```
Synthetic Data → Lakeflow (Bronze/Silver/Gold) → Unity Catalog (Governed)
    ↓                                                    ↓
Lakebase (Low-Latency Serving)              ML Models (Anomaly Detection)
    ↓                                                    ↓
AI/BI Dashboard ←──── Databricks App ────→ Genie Agent (NL Queries)
```

## Components

### 1. Data Simulator (`notebooks/Aircraft_Data_Simulator.ipynb`)
Generates 1M+ telemetry rows across 10 airlines, 328 aircraft, 1,005 flights with 109 sensor parameters per reading. 103 anomalous flights (~10.3%) with 10 anomaly types.

### 2. Lakeflow Medallion Pipeline (`pipeline/`)
Spark Declarative Pipeline: Bronze (4 tables) → Silver (2 tables) → Gold (4 tables). Target: `genie_zeroops_mfg_catalog.default`.

| Layer | Tables | Description |
|-------|--------|-------------|
| Bronze | `bronze_raw_telemetry`, `bronze_staging_telemetry`, `bronze_flights_metadata`, `bronze_aircraft_registry` | Raw ingestion with schema enforcement |
| Silver | `silver_telemetry`, `silver_enriched_telemetry` | Cleaned, deduplicated, enriched |
| Gold | `gold_flight_summary`, `gold_aircraft_health`, `gold_anomaly_events`, `gold_airline_operations` | Aggregated business KPIs |

### 3. ML Anomaly Detection (`notebooks/Aircraft_Anomaly_Detection_Model.ipynb`)
- **Binary GBT Classifier**: Accuracy=0.945, F1=0.686, ROC-AUC=0.784
- **Multi-class Random Forest** + **Isolation Forest**
- **Output**: `ml_maintenance_predictions` — 310 aircraft (CRITICAL:10, HIGH:24, MEDIUM:82, LOW:194)
- Models in Unity Catalog: `aircraft_anomaly_binary_classifier` v2, `aircraft_anomaly_type_classifier` v2

### 4. Gold Metric Views (`notebooks/Gold_Layer_Metric_Views.ipynb`)
Three UC metric views: `fleet_operations_metrics`, `aircraft_health_metrics`, `anomaly_analysis_metrics`

### 5. Unity Catalog Governance
Catalog/schema/table tags, 11 table comments, column comments, governed tags (`domain=operations`, `industry=MFG`, quality tiers)

### 6. Lakebase (Operational Serving)
Instance `aircraft-maintenance-lakebase` (CU_1), 5 synced tables (SNAPSHOT mode) for low-latency dashboard queries

### 7. Genie Agent
"Aircraft Maintenance Intelligence" — 8 tables, domain instructions, 5 starter questions, knowledge snippets

### 8. AI/BI Dashboard
4 pages (Fleet Ops, Aircraft Health, Anomaly Analysis, Airline Ops), 5 datasets on Lakebase synced tables, published with embedded credentials

### 9. Databricks App (`app/`)
Flask app: embedded AI/BI dashboard + custom Genie chat with Chart.js visualizations (Bar/Donut/Line), query result polling, markdown-formatted responses. Aviation cockpit dark theme.

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
5. Deploy `app/` as a Databricks App
