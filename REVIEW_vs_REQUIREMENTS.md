# Build review against the FE Bar requirements

Reviewed 2026-11-09. Baseline: the last reviewed submission, commit `4d9f422` (2026-10-29). Current: commit `5136ff5` plus this file. Every number here was re-checked against the live workspace on 2026-11-09.

## 1. What was built

Customer problem: Parker Aerospace (a Tier-1 aerospace component OEM) carries warranty and AOG risk on 1,640 installed components across 10 airline operators, but sees operator service data late and in pieces. The build predicts which components will have a failure or warranty-risk event next quarter, so Field Service can visit before the operator calls an AOG. All data is synthetic.

| Stage | What exists | Live check (2026-11-09) |
| --- | --- | --- |
| Raw data | Synthetic installed base (`notebooks/Aircraft_Data_Simulator.ipynb`) and operator flight telemetry | 328 aircraft, 1,640 components, 9,839 service records, 10 operators. 1.38M telemetry rows |
| Lakeflow | Operator telemetry: SDP pipeline `5bd5dac4` (`pipeline/`). Parker: SDP code in `pipeline_parker/` | Operator pipeline last update COMPLETED. **The Parker tables are managed tables written by notebooks, not pipeline output** (see section 5) |
| Unity Catalog | `governance/uc_access_controls.sql`, `notebooks/UC_Governance.ipynb` | Row filter `airline_row_filter` on 2 tables, column mask `financial_mask` on `expected_warranty_exposure_usd`, 5-row `operator_entitlements` table |
| Lakebase | Instance `aircraft-maintenance-lakebase`, 7 synced tables | AVAILABLE. Parker: `gold_component_health_synced` 1,640, `gold_maintenance_compliance_synced` 50 (both match source) |
| ML | Point-in-time next-quarter forecast (`notebooks/Parker_Component_Failure_Forecast.ipynb`), MLflow run `6b20bf8b32c84774807ed160317fa799` | 1,640 rows, 164 top-decile / proactive-visit, $10.16M expected exposure. Back-test: 59 events on 58 components, of which 14 events on 13 components fell in the top decile |
| Gen AI | Vector Search over maintenance manuals | 100 chunks, index `maintenance_manual_index` |
| Metric views | `component_health_metrics`, `part_failure_metrics`, `maintenance_anomaly_metrics` | 1,640 / 1,640 (164 visit, 164 top-decile) / 969. All read current tables |
| Genie | "Aircraft Maintenance Intelligence" (13 tables, 2 Parker benchmarks, both passing when set up on 2026-10-29) | Parker-framed description confirmed live. Benchmarks not re-run today |
| App | `aircraft-maintenance-app`: dashboard, Genie chat, manual search | RUNNING, deployment `01f1d3d4` (2026-10-29) |
| Dashboard | "Aircraft Predictive Maintenance Dashboard", opens on "Parker Installed Base" | Published 2026-10-29, embedded credentials |
| Deck | `deck/Parker_Aerospace_Value_Deck.pptx`, 11 slides | Slide 11: "Appendix: how we built it" |

## 2. What changed since the last reviewed build

| Commit / action | Change |
| --- | --- |
| `92b2039` | README "How this was built" section. New `notebooks/00_Build_Process.ipynb` (workflow, AI by layer, force multipliers, human overrides). Deck slide 11. `execution_evidence.md` reconciled |
| Live, 2026-11-02 | `part_failure_metrics` repointed with `ALTER VIEW` (grants kept) from the leaky `ml_part_failure_predictions` to `ml_component_failure_forecast`. Old table commented RETIRED. Two Parker Lakebase synced tables created |
| `9584719` | Metric-view notebook uses `ALTER VIEW` with the live YAML, so re-running keeps grants |
| `2be766a` | `days_to_predicted_failure` labelled simulated (it is a random draw banded by `health_index`, not a model output). `failure_risk_category` labelled rule-based. `health_index` scale corrected to 0-100 |
| `f07530b` | Validation cell asserts expected values and fails on mismatch (tested with a wrong value). Warranty exposure formatted as USD in all three views |
| `2a2d0c7`, `08740e4` | Back-test measure labelled "Actual Events in Forecast Quarter (back-test only)". Governance note on the masked exposure measure |
| `5136ff5` | GitHub Copilot removed from `AI_BUILD_PROCESS.md`. Databricks Assistant (Genie Code) is the only AI tool named |
| Outside Git | `START_HERE.md` updated. Superseded `FE Bar/Gold Layer Metric Views` (still on the leaky table) deleted |

## 3. How the changes close the reviewer's gaps

| Reviewer gap | Status | Evidence |
| --- | --- | --- |
| **Must-have:** no account of the build workflow or the AI tools used as a force multiplier | Closed | README "How this was built", `notebooks/00_Build_Process.ipynb`, deck slide 11, `AI_BUILD_PROCESS.md` (one tool named consistently) |
| A metric view still on the leakage-flagged model | Closed | `part_failure_metrics` source is `ml_component_failure_forecast`. The old table is RETIRED and nothing reads it. Validation cell asserts 1,640 / 164 / 164 |
| Lakebase counts from the earlier pipeline | Closed, with one limitation | Parker gold tables synced (1,640 and 50, matching source). The forecast and customer-operations tables cannot be synced, because the sync API rejects tables with a row filter or mask. They are served from UC with governance intact, and this is documented |
| Level-up: action brief for Field Service from `recommended_action` + manuals | Not done | |
| Level-up: drift-triggered retrain job | Not done | |
| Level-up: entitlement-based row security in Genie | Partly in place, not demonstrated | Genie runs queries as the asking user, so the existing row filter should apply to the 2 filtered tables in the space. No test result is committed |

## 4. Scoring against the requirements

| Requirement | Status | Note |
| --- | --- | --- |
| Specific industry problem | Met | Reviewer: Industry **Exceeds** |
| Raw dataset, synthetic or public | Met | Synthetic, with deliberate operator-level skew |
| Lakeflow ingestion | **At risk** | The pipeline that ran ingests the operator telemetry. The Parker data the story is about was never run through Lakeflow (section 5) |
| Unity Catalog governance | Met | Row filter, column mask, entitlement table, tags, owners, lineage |
| Lakebase operational serving | Met | 7 synced tables, all sync pipelines' latest update COMPLETED. Parker counts match source |
| ML or Gen AI | Met | Leakage-free forecast with back-test, plus Vector Search |
| Genie Agent | Met | Parker benchmarks passed on 2026-10-29. The pass is not logged in `execution_evidence.md` |
| Databricks App | Met | Running, with dashboard, Genie and manual search |
| Integrated, not siloed | Mostly met | Weakest link is the Parker ingestion step |
| **Execution evidence readable as text** | **At risk** | 0 of 67 code cells in the 9 committed notebooks have outputs. Evidence rests on `execution_evidence.md` (a written summary) and markdown result cells. The brief says source code alone will not pass the Build domain |
| Public, readable GitHub repo | Met | `private: false`. Files readable without signing in |
| No real customer data | Met, one judgement risk | All records are synthetic, but 5 real MRO companies are named in the simulator and get synthetic anomalies and false-compliance flags |
| Deck: business outcome, buyer KPIs, sponsor and domain owner | Met | Reviewer: Customer Skills **Exceeds** |
| **Deck attached as PDF / .txt / .md** | **Not ready** | Only the `.pptx` exists |
| Conversation ID (optional) | Present | `execution_evidence.md`: thread `617974576538052` |

Expected ratings (judgement, not a guarantee):

| Area | Last | Expected now | Why |
| --- | --- | --- | --- |
| Industry | Exceeds | Exceeds | Unchanged |
| Customer Skills | Exceeds | Exceeds | Unchanged, if the deck is attached as PDF |
| Product | Meets | Meets, possibly Exceeds | Serving layer reconciled as asked. No level-up extensions built. The Lakeflow finding could pull it down if noticed |
| Build + AI Mindset | Below | Meets | The blocking must-have is now covered in three places |

## 5. Open risks, in priority order

1. **Notebook outputs not committed.** This is the most likely way to fail the Build domain. Fix: commit outputs for the forecast, governance, metric-view, simulator and manuals notebooks (Git folders can include outputs on commit), or add raw query and run output to the repo as text.
2. **Deck not exported.** The form needs PDF, .txt or .md. Export the 11-slide `.pptx` and attach it.
3. **Parker data never went through Lakeflow.** All 11 Parker tables are managed tables created by notebooks (the 10 medallion tables on 2026-09-28, the forecast on 2026-10-22). `pipeline_parker/` holds SDP code but was never deployed. Fix: deploy `pipeline_parker/` as a pipeline, run it, and log its update ID and counts. Or say plainly in the README which pipeline ran and which code is reference only.
4. **`execution_evidence.md` is partly out of date.** It says "Last refreshed 2026-10-22" and describes the dashboard as 4 pages and 5 datasets. Its only Genie test is an operator question, not the passing Parker benchmarks.
5. **Real MRO company names** (Lufthansa Technik, Air France KLM E&M, ST Engineering, Chromalloy, Evergreen Aviation) are attached to synthetic quality failures. Safer to replace them with fictional names.
