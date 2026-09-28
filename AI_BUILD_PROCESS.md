# AI Build Process — Parker Hannifin Aerospace Component Predictive Maintenance

## Overview

This document captures how AI tools were used throughout the build process, which decisions were AI-assisted, and where AI had the biggest impact on quality, speed, and architectural coherence.

**Project**: Parker Hannifin Aerospace Component Predictive Maintenance Platform  
**Builder**: Ayman El-Ghazali  
**AI Tools**: Databricks Assistant (Genie Code), GitHub Copilot  
**Duration**: ~2 weeks (design through deployment)

---

## Architecture Decisions Made with AI

| Decision | AI Contribution | Impact |
|----------|----------------|--------|
| Medallion layer design (Bronze→Silver→Gold) | AI suggested table granularity — one row per component vs. per aircraft | Enabled component-level failure prediction (1,640 predictions vs. 310) |
| 6 anomaly type taxonomy | AI proposed anomaly categories based on aerospace MRO domain research | Realistic anomaly distribution with correlated severity/delay risk |
| ML model selection (GBT + Isolation Forest) | AI recommended ensemble approach for both supervised + unsupervised detection | Binary AUC 0.999, Isolation Forest catches novel patterns |
| Metric view YAML design | AI authored YAML metric definitions with proper synonyms and formatting | 3 production-ready semantic views consumed by Genie Room |
| Genie Room domain instructions | AI wrote comprehensive domain context with table routing rules | Natural language queries correctly routed to appropriate gold tables |

## Where AI Had the Biggest Impact

### 1. Data Simulator Realism (HIGH IMPACT)
The AI-assisted data simulator generates correlated, realistic aerospace component maintenance data:
- 5 Parker component types with accurate maintenance intervals, max cycles, and cost data
- 6 anomaly types with calibrated severity distributions (9.8% anomaly rate)
- Maintenance records with realistic MRO shop assignments and technician certifications
- Component telemetry with health index degradation curves and warranty exposure calculations

**Before AI**: Manual CSV creation with flat, uncorrelated data  
**After AI**: 9,839 maintenance records with embedded anomaly patterns, correlated health metrics, and $8.5M warranty exposure model

### 2. Pipeline Transformation Logic (HIGH IMPACT)
AI generated Lakeflow Spark Declarative Pipeline notebooks with:
- Silver layer enrichment: compliance scoring formula, overdue day calculation, anomaly risk flags
- Gold layer aggregations: component health rollups, compliance scorecards, customer operations summaries
- Proper join strategies between maintenance records, component registry, and aircraft metadata

**Before AI**: ~4 hours of manual SQL writing and testing  
**After AI**: Complete pipeline generated and validated in ~30 minutes

### 3. ML Feature Engineering (MEDIUM IMPACT)
AI identified key features for part failure prediction:
- Removed leaking features (failure_risk_category derived from target)
- Applied SMOTE oversampling for imbalanced anomaly classes
- Suggested Isolation Forest as complementary unsupervised detector
- Generated recommended_action mapping based on failure probability thresholds

### 4. Unity Catalog Governance (MEDIUM IMPACT)
AI generated comprehensive governance across 11 tables:
- Catalog and schema comments
- 46 column-level descriptions with domain-specific terminology
- Quality tier tags aligned to medallion layers
- Table comments with row counts, source attribution, and usage guidance

### 5. Databricks App Integration (MEDIUM IMPACT)
AI designed the Flask app architecture:
- Dashboard iframe embedding with correct workspace URL construction
- Genie Room chat integration with async query polling
- Chart.js visualizations with auto-detection of chartable data
- Service principal permission setup (USE_CATALOG, SELECT, CAN_MANAGE, CAN_USE)

## Quantified Before/After Outcomes

| Metric | Before (Manual) | After (AI-Assisted) | Improvement |
|--------|-----------------|---------------------|-------------|
| Data generation time | ~6 hours | ~45 minutes | 8x faster |
| Pipeline dev time | ~4 hours | ~30 minutes | 8x faster |
| ML model iterations | 2-3 manual runs | 5 automated runs with comparison | More thorough |
| Governance coverage | 0 tables documented | 11 tables, 46 columns | Complete coverage |
| End-to-end build | ~3 weeks estimate | ~2 weeks actual | 33% faster |
| Component predictions | 310 (aircraft-level) | 1,640 (component-level) | 5x granularity |
| Warranty exposure model | Not quantified | $8.5M modeled | New capability |

## AI Tool Usage Breakdown

| Phase | Tool | Tasks |
|-------|------|-------|
| Design | Databricks Assistant | Architecture review, table design, Parker Hannifin domain research |
| Data Engineering | Databricks Assistant | Simulator code, pipeline transformations, schema design |
| ML Engineering | Databricks Assistant | Feature selection, model comparison, prediction output design |
| Governance | Databricks Assistant | Table/column comments, tag strategy, metric view YAML |
| App Development | Databricks Assistant | Flask app scaffolding, Genie integration, permission setup |
| Documentation | Databricks Assistant + GitHub Copilot | README, execution evidence, this document |

## Key Lessons Learned

1. **Start with the business story**: AI works best when given clear domain context. The Parker Hannifin reframe from "airline fleet ops" to "component OEM maintenance" required human judgment but AI accelerated the rewrite.

2. **Validate AI-generated SQL**: AI-generated pipeline transformations needed manual review for join correctness and null handling. Always test with real data before trusting aggregate numbers.

3. **Governance as code**: Having AI generate COMMENT ON and ALTER COLUMN statements means governance is repeatable, version-controlled, and auditable.

4. **Metric views are powerful**: AI-authored YAML metric views create a semantic layer that Genie Room uses for natural language query routing. This is the bridge between data engineering and business users.

5. **Tag policies matter**: Workspace tag policies constrained which tags could be applied. AI helped navigate the allowed values (quality=bronze/silver/gold) vs. custom keys.