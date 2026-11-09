# Read-only script that produced evidence/execution_log.md.
# Run on Databricks (serverless or any UC cluster): it only reads tables, MLflow,
# and the Pipelines / Lakebase / Apps / Lakeview APIs. It writes nothing.
import datetime, json
from databricks.sdk import WorkspaceClient
import mlflow

w = WorkspaceClient()
C = "genie_zeroops_mfg_catalog.default"
out = []
P = out.append


def tbl(rows, cols):
    P("| " + " | ".join(cols) + " |")
    P("| " + " | ".join("---" for _ in cols) + " |")
    for r in rows:
        P("| " + " | ".join(str(x) for x in r) + " |")
    P("")


def sql(s):
    return spark.sql(s).collect()


P(f"Run at {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC as `{sql('SELECT current_user()')[0][0]}`\n")

P("## 1. Parker installed-base tables (row counts)\n")
names = ["bronze_customer_registry", "bronze_parker_aircraft_registry", "bronze_components_registry",
         "bronze_maintenance_records", "bronze_component_telemetry", "silver_enriched_maintenance",
         "gold_component_health", "gold_maintenance_compliance", "gold_maintenance_anomalies",
         "gold_customer_operations", "ml_component_failure_forecast"]
tbl([(n, f"{spark.table(f'{C}.{n}').count():,}") for n in names], ["table", "rows"])

P("## 2. Lakeflow pipeline runs\n")
rows = []
for p in w.pipelines.list_pipelines(max_results=100):
    if "Synced table" in (p.name or "") or not any(k in p.name.lower() for k in ["aircraft", "parker"]):
        continue
    for u in list(w.pipelines.list_updates(p.pipeline_id, max_results=3).updates or []):
        created = datetime.datetime.fromtimestamp(u.creation_time / 1000, datetime.timezone.utc)
        rows.append((p.name, p.pipeline_id, u.update_id, u.state.value if u.state else "", f"{created:%Y-%m-%d %H:%M:%S}"))
tbl(rows, ["pipeline", "pipeline_id", "update_id", "state", "created (UTC)"])

P("## 3. Unity Catalog governance\n")
tbl([tuple(r) for r in sql("SELECT table_name, filter_name FROM genie_zeroops_mfg_catalog.information_schema.row_filters WHERE table_schema='default'")], ["table", "row filter"])
tbl([tuple(r) for r in sql("SELECT table_name, column_name, mask_name FROM genie_zeroops_mfg_catalog.information_schema.column_masks WHERE table_schema='default'")], ["table", "column", "mask"])
ent = sql(f"SELECT * FROM {C}.operator_entitlements ORDER BY 1")
tbl([tuple(r) for r in ent], list(ent[0].__fields__))
in_list = ",".join(repr(n) for n in names)
tbl([tuple(r) for r in sql(f"SELECT table_name, tag_name, tag_value FROM genie_zeroops_mfg_catalog.information_schema.table_tags WHERE schema_name='default' AND table_name IN ({in_list}) ORDER BY 1,2")], ["table", "tag", "value"])
tbl([tuple(r) for r in sql(f"SHOW TBLPROPERTIES {C}.ml_component_failure_forecast") if r[0].startswith("parker.")], ["property (ml_component_failure_forecast)", "value"])

P("## 4. ML forecast (MLflow)\n")
run = mlflow.get_run("6b20bf8b32c84774807ed160317fa799")
P(f"Experiment `{run.info.experiment_id}`, run `{run.info.run_id}`, status {run.info.status}, run name `{run.info.run_name}`\n")
tbl(sorted((k, round(v, 4)) for k, v in run.data.metrics.items()), ["metric", "value"])
tbl(sorted(run.data.params.items()), ["param", "value"])
f = sql(f"""SELECT count(*) n, count_if(risk_decile=10) top_decile,
  count_if(recommended_action='PROACTIVE_FIELD_SERVICE_VISIT') visits,
  sum(n_future_events) events, sum(actual_next_quarter_event) components_with_event,
  sum(CASE WHEN risk_decile=10 THEN n_future_events END) events_in_top_decile,
  format_number(sum(expected_warranty_exposure_usd), 0) expected_exposure_usd,
  min(forecast_cutoff_date) cutoff
  FROM {C}.ml_component_failure_forecast""")[0]
tbl([tuple(f)], list(f.__fields__))
top = sql(f"""SELECT component_id, airline, component_type, round(forecast_probability,3) p, risk_decile, recommended_action
  FROM {C}.ml_component_failure_forecast ORDER BY forecast_probability DESC, component_id LIMIT 5""")
P("Top 5 components by forecast probability:\n")
tbl([tuple(r) for r in top], list(top[0].__fields__))

P("## 5. Metric views\n")
mv = sql(f"""SELECT 'component_health_metrics', 'Total Components', CAST(MEASURE(`Total Components`) AS STRING) FROM {C}.component_health_metrics
UNION ALL SELECT 'part_failure_metrics', 'Proactive-Visit Components', CAST(MEASURE(`Proactive-Visit Components`) AS STRING) FROM {C}.part_failure_metrics
UNION ALL SELECT 'part_failure_metrics', 'Expected Warranty Exposure', format_number(MEASURE(`Expected Warranty Exposure`), 0) FROM {C}.part_failure_metrics
UNION ALL SELECT 'maintenance_anomaly_metrics', 'Total Anomalies', CAST(MEASURE(`Total Anomalies`) AS STRING) FROM {C}.maintenance_anomaly_metrics""")
tbl([tuple(r) for r in mv], ["metric view", "measure", "value"])
src = json.loads(sql(f"DESCRIBE TABLE EXTENDED {C}.part_failure_metrics AS JSON")[0][0])
P(f"`part_failure_metrics` source line: `{[l for l in src.get('view_text', '').splitlines() if l.startswith('source:')][0]}`\n")

P("## 6. Lakebase synced tables\n")
rows = []
for t in ["gold_component_health", "gold_maintenance_compliance", "gold_flight_summary", "gold_airline_operations",
          "gold_aircraft_health", "gold_anomaly_events", "ml_maintenance_predictions"]:
    s = w.database.get_synced_database_table(f"{C}.{t}_synced").data_synchronization_status
    rows.append((f"{t}_synced", f"{spark.table(f'{C}.{t}').count():,}", f"{spark.table(f'{C}.{t}_synced').count():,}",
                 s.detailed_state.value if s and s.detailed_state else ""))
tbl(rows, ["synced table", "source rows", "synced rows", "state"])
inst = w.database.get_database_instance("aircraft-maintenance-lakebase")
P(f"Instance `{inst.name}`: {inst.state.value}, capacity {inst.capacity}\n")

P("## 7. Vector Search over maintenance manuals\n")
vs = sql(f"SELECT * FROM vector_search(index => '{C}.maintenance_manual_index', query => 'hydraulic actuator seal leak inspection', num_results => 3)")
cols = [c for c in vs[0].__fields__ if c not in ("chunk_text", "text", "content")][:5]
tbl([tuple(str(r[c])[:80] for c in cols) for r in vs], cols)

P("## 8. Databricks App and dashboard\n")
app = w.apps.get("aircraft-maintenance-app")
P(f"App `{app.name}`: {app.app_status.state.value}, compute {app.compute_status.state.value}, "
  f"deployment `{app.active_deployment.deployment_id}` ({app.active_deployment.status.state.value})\n")
d = w.lakeview.get_published("01f1a5f8872c151b939582bfede572d6")
pages = [pg["displayName"] for pg in json.loads(w.lakeview.get("01f1a5f8872c151b939582bfede572d6").serialized_dashboard)["pages"]]
P(f"Dashboard `{d.display_name}` published {d.revision_create_time}. Pages: {', '.join(pages)}\n")

print("\n".join(out))
