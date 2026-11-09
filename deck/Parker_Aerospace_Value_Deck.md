# Parker Aerospace: Installed-Base Reliability & Warranty Intelligence

Text export of `deck/Parker_Aerospace_Value_Deck.pptx` (11 slides), for the submission form's deck field. Slide text and tables are extracted verbatim from the .pptx.

---

## Slide 1. Parker Aerospace: Installed-Base Reliability & Warranty Intelligence

**Predict which Parker components will fail in service next quarter, and act before the operator calls an AOG**

- Prepared for: VP Aftermarket & Customer Support (economic buyer) and Director, Product Support Engineering (operational owner)
- Built on Databricks: Lakeflow pipelines, Unity Catalog, MLflow, Vector Search, Genie, Lakebase, Databricks Apps
- All figures are from a synthetic installed base modelled on Parker's aerospace portfolio

---

## Slide 2. Parker's position in the aerospace value chain

**Parker builds the part. The operator and its MRO maintain it. Parker pays when it fails early.**

| Party | Role | What it controls | What it costs Parker when it goes wrong |
| --- | --- | --- | --- |
| Parker Aerospace (Tier-1 OEM) | Designs/builds hydraulic actuators, fuel valves, pneumatic valves, ECS controllers, sensors | Design, CMMs, service bulletins, warranty terms | Warranty claims, AOG spares + field-service dispatch |
| Airframer | Integrates Parker systems into the aircraft | Supplier scorecard, reliability guarantees | Reliability-guarantee penalties, share of future platforms |
| 10 airline operators | Fly 328 aircraft carrying 1,640 Parker components | Flight hours, cycles, maintenance schedule | Unscheduled removals reported against Parker part numbers |
| MRO shops | Perform scheduled service and shop visits | Service quality and record accuracy | Missed or mis-recorded service turns into early failures and disputed claims |

The gap: Parker carries the warranty and AOG risk but sees operator service data late and in pieces. This platform puts operator service records and component telemetry in one governed view.

---

## Slide 3. Who owns these numbers

**Each KPI in this deck has a named executive owner (by role)**

| KPI | Owner (role) | Why they care |
| --- | --- | --- |
| Warranty cost and exposure ($) | VP Aftermarket & Customer Support | Owns the aftermarket P&L and the warranty reserve |
| Program funding, payback | VP Finance, Aerospace Group | Approves the investment and the reserve assumptions |
| Unscheduled removals, anomaly rate, MTBUR | Director, Product Support Engineering | Owns reliability, fault isolation and CMM content |
| AOG events, field-service dispatches | Director, Customer Support & Field Service | Owns response time and operator satisfaction |
| Operator service compliance | Director, Customer Support & Field Service | Negotiates service obligations with each operator |

---

## Slide 4. Today: reactive, late, and expensive

**Live from the governed gold tables**

| Current-state metric | Value | Owner |
| --- | --- | --- |
| Installed Parker components monitored | 1,640 on 328 aircraft, 10 operators | VP Aftermarket |
| Service records analysed (18 months) | 9,839 | Dir. Product Support Eng. |
| Service events with a maintenance anomaly | 9.8% | Dir. Product Support Eng. |
| Average days an anomaly goes undetected | 37 days | Dir. Customer Support & Field Service |
| Modelled warranty exposure on at-risk components | $8.53M | VP Aftermarket |
| HIGH/CRITICAL service events or warranty-risk events per quarter | 59 events, $995K unit value | VP Aftermarket |

Worst operators by anomaly rate: Atlas Pacific 11.2%, Continental Wings 11.0%, Summit Aviation 10.7%

---

## Slide 5. What we built

**One governed platform from operator data to an engineer's next action**

- Ingest: Lakeflow pipelines land operator flight telemetry and Parker service records (bronze -> silver -> gold) with data-quality expectations
- Govern: Unity Catalog comments, quality tags, owner properties, operator-level row filters and a warranty-$ column mask, so an airline only sees its own fleet
- Forecast: next-quarter failure model, point-in-time features, 5-fold CV, tracked in MLflow; ranks all 1,640 components
- Act: Databricks App with dashboard, Genie (ask in plain English), and Maintenance Manual search (Vector Search) that returns the fault-isolation steps, part numbers and torque values
- Serve: Lakebase for low-latency operational reads from the app

---

## Slide 6. How good is the forecast? (back-test, Jun-Aug 2026)

**Trained only on data before 1 Jun 2026, scored against what actually happened next**

| Approach | Inspect 10% of fleet and catch... | Lift vs random |
| --- | --- | --- |
| Random inspection | 10% of next-quarter events | 1.0x |
| Rule: components with prior HIGH/CRITICAL history | 12% of events | 1.2x |
| Databricks forecast (top decile) | 24% of events (14 of 59) | 2.4x |

ROC-AUC 0.60. An earlier model reported 0.999 AUC; that was target leakage (the label was a threshold on one of its own inputs) and has been replaced. The signal is limited by the synthetic data. Real operator data is expected to carry stronger wear and overdue signals.

---

## Slide 7. Before and after: one quarter, back-tested

**Proactive field-service visits on the top-decile list**

| KPI (owner) | Before (today) | After | Change |
| --- | --- | --- | --- |
| Quarterly exposure from HIGH/CRITICAL + warranty-risk events (VP Aftermarket) | $995K | $797K | -20% |
| Events found before they happen (Dir. Product Support Eng.) | 0 | 14 of 59 | +24% caught |
| Events carrying HIGH/CRITICAL AOG risk (Dir. Customer Support) | 54 | 46 | -14% |
| Days undetected for flagged components (Dir. Customer Support) | 37 days | 0 days (found at visit) | -37 days |
| Components Field Service must visit (Dir. Customer Support) | unknown / blanket checks | 164 per quarter | targeted list |

Assumption: 60% of caught events are converted to a planned repair by the proactive visit. Exposure is unit replacement value of the affected component.

---

## Slide 8. For the VP Finance / VP Aftermarket: the financial case

**Warranty reserve, cash and payback**

- Avoided warranty exposure: $198K per quarter, about $791K per year, on today's 1,640-component synthetic installed base
- Quarterly exposure from high-severity events moves from $995K to $797K (-20%)
- Payback: about 4 months at an assumed $250K/year run cost (platform + part-time analyst)
- Reserve accuracy: per-component expected exposure (probability x unit cost) replaces a flat historical accrual, so the warranty reserve can be set bottom-up
- Scales linearly: the same pipeline and model cover every additional operator contract without new headcount
- Ask: fund a 90-day pilot with the two highest-anomaly operators, with the success gate defined on the next slide

---

## Slide 9. For the Director, Product Support Engineering: the operational case

**Fewer surprises, faster fault isolation, a short list to act on**

- A ranked list each quarter: 164 components to visit instead of blanket checks, and that list holds 24% of next quarter's high-severity events
- AOG-risk events drop from 54 to about 46 per quarter. Each one avoided is one fewer emergency spares shipment and field-service dispatch
- Anomalies on flagged components are found at the visit, not about 37 days later at failure
- Engineers search the Maintenance Manuals by symptom or part number and get the fault-isolation steps, limits and torque values in seconds
- Ask Genie in plain English: 'Which Atlas Pacific hydraulic actuators are in the top risk decile next quarter?' Answers come from the same governed tables
- Operators can be given read access to their own fleet only (row filters), so findings can be shared without exposing other customers

---

## Slide 10. Next step: 90-day pilot

**Owner: VP Aftermarket & Customer Support. Sponsor: VP Finance, Aerospace Group**

| Week | Milestone | Success gate |
| --- | --- | --- |
| 0-4 | Connect real service records for Atlas Pacific and Continental Wings | Data lands daily and passes quality checks |
| 4-8 | Retrain on real data and back-test on the last quarter | Top-decile list catches at least 2x the events random inspection does |
| 8-12 | Field Service works the list, engineers use manual search | At least 25% fewer high-severity events on visited components |
| 12 | Decision review with VP Finance | Annualised avoided exposure exceeds 3x run cost |

---

## Slide 11. Appendix: how we built it

**Workflow and AI tools: Databricks Assistant (Genie Code) inside the workspace**

- Loop for every component: describe the goal -> Genie Code drafts code/SQL/config -> run on live Unity Catalog data and verify with an independent query -> commit to Git
- Order: synthetic data -> Lakeflow pipelines -> Unity Catalog governance -> ML forecast -> metric views -> Lakebase -> Genie -> dashboard -> Databricks App -> this deck
- Force multiplier 1: reviewer feedback audited, fixed and re-verified in one session
- Force multiplier 2: challenged its own 0.999 AUC, traced it to target leakage, rebuilt an honest next-quarter forecast (AUC 0.60, 2.2x lift)
- Force multiplier 3: governance as code (row filter, column mask, grants) generated and verified live
- Human judgment: Parker's value-chain position and KPI owners, the financial assumptions, and approving renames only after dependency checks
