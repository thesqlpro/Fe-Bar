-- =============================================================================
-- Unity Catalog access controls -- Parker Aerospace installed-base platform
-- Catalog: genie_zeroops_mfg_catalog   Schema: default
--
-- Complements notebooks/UC_Governance.ipynb (comments + quality tags) with:
--   1. Ownership / sensitivity tags (data_owner = accountable executive role)
--   2. Operator entitlement map  -> row-level security (each airline sees only its fleet)
--   3. Financial column mask      -> warranty $ visible only to finance / aftermarket leads
--   4. Least-privilege grants for the Databricks App service principal
--   5. Verification + lineage queries (evidence)
-- Idempotent: safe to re-run.
-- =============================================================================
USE CATALOG genie_zeroops_mfg_catalog;
USE SCHEMA default;

-- -----------------------------------------------------------------------------
-- 1. Ownership metadata + medallion tags
--    The workspace tag policy only allows the governed `quality` key
--    (bronze/silver/gold), so the accountable executive role and data
--    sensitivity are recorded as table properties that travel with the table.
-- -----------------------------------------------------------------------------
ALTER TABLE gold_component_health         SET TBLPROPERTIES ('parker.data_owner' = 'VP Aftermarket and Customer Support',  'parker.domain' = 'installed_base',         'parker.sensitive_columns' = 'estimated_warranty_exposure_usd,total_warranty_exposure_usd');
ALTER TABLE gold_customer_operations      SET TBLPROPERTIES ('parker.data_owner' = 'VP Aftermarket and Customer Support',  'parker.domain' = 'customer_operations',    'parker.sensitive_columns' = 'total_warranty_exposure_usd');
ALTER TABLE gold_maintenance_compliance   SET TBLPROPERTIES ('parker.data_owner' = 'Director Product Support Engineering', 'parker.domain' = 'compliance');
ALTER TABLE gold_maintenance_anomalies    SET TBLPROPERTIES ('parker.data_owner' = 'Director Product Support Engineering', 'parker.domain' = 'reliability');
ALTER TABLE ml_component_failure_forecast SET TBLPROPERTIES ('parker.data_owner' = 'VP Aftermarket and Customer Support',  'parker.domain' = 'reliability',            'parker.sensitive_columns' = 'expected_warranty_exposure_usd');
ALTER TABLE maintenance_manual_chunks     SET TBLPROPERTIES ('parker.data_owner' = 'Director Product Support Engineering', 'parker.domain' = 'technical_publications');
ALTER TABLE ml_component_failure_forecast SET TAGS ('quality' = 'gold');
ALTER TABLE maintenance_manual_chunks     SET TAGS ('quality' = 'gold');
ALTER TABLE maintenance_manual_parsed     SET TAGS ('quality' = 'silver');

-- -----------------------------------------------------------------------------
-- 2. Operator entitlement map + row filter
--    principal = user email or account group; airline = '*' means all operators.
--    Parker staff see every airline; an operator's maintenance planners only see
--    their own fleet when Parker shares the forecast with them.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operator_entitlements (
  principal          STRING  NOT NULL COMMENT 'User email or account group name',
  principal_type     STRING  NOT NULL COMMENT 'USER or GROUP',
  airline            STRING  NOT NULL COMMENT 'Operator the principal may see (* = all operators)',
  can_see_financials BOOLEAN NOT NULL COMMENT 'If true, warranty / cost columns are unmasked'
) COMMENT 'Entitlement map driving row filters and column masks on Parker installed-base tables. Owner: VP Aftermarket and Customer Support.';

MERGE INTO operator_entitlements t
USING (
  SELECT col1 AS principal, col2 AS principal_type, col3 AS airline, col4 AS can_see_financials FROM VALUES
    ('ayman.el-ghazali@databricks.com', 'USER',  '*',              true),   -- platform owner (demo)
    ('parker_aftermarket_leads',        'GROUP', '*',              true),   -- Parker aftermarket + finance
    ('parker_field_service',            'GROUP', '*',              false),  -- all operators, no $
    ('operator_skywest_global',         'GROUP', 'SkyWest Global', false),  -- operator planners: own fleet only
    ('operator_atlas_pacific',          'GROUP', 'Atlas Pacific',  false)
) s
ON t.principal = s.principal AND t.airline = s.airline
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;

CREATE OR REPLACE FUNCTION airline_row_filter(airline STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: true if the caller is entitled to see this operator (directly or via an account group).'
RETURN EXISTS (
  SELECT 1 FROM genie_zeroops_mfg_catalog.default.operator_entitlements e
  WHERE (e.airline = '*' OR e.airline = airline)
    AND ((e.principal_type = 'USER'  AND e.principal = current_user())
      OR (e.principal_type = 'GROUP' AND is_account_group_member(e.principal)))
);

CREATE OR REPLACE FUNCTION financial_mask(val DOUBLE)
RETURNS DOUBLE
COMMENT 'Column mask: returns warranty / cost values only to principals with can_see_financials.'
RETURN CASE WHEN EXISTS (
  SELECT 1 FROM genie_zeroops_mfg_catalog.default.operator_entitlements e
  WHERE e.can_see_financials
    AND ((e.principal_type = 'USER'  AND e.principal = current_user())
      OR (e.principal_type = 'GROUP' AND is_account_group_member(e.principal)))
) THEN val ELSE NULL END;

-- Apply to the tables Parker would share with operators
ALTER TABLE ml_component_failure_forecast SET ROW FILTER airline_row_filter ON (airline);
ALTER TABLE ml_component_failure_forecast ALTER COLUMN expected_warranty_exposure_usd SET MASK financial_mask;
ALTER TABLE gold_customer_operations      SET ROW FILTER airline_row_filter ON (airline);

-- -----------------------------------------------------------------------------
-- 3. Least-privilege grants for the Databricks App service principal
--    (aircraft-maintenance-app; application id below). Read-only, specific objects.
-- -----------------------------------------------------------------------------
GRANT USE CATALOG ON CATALOG genie_zeroops_mfg_catalog                     TO `a048a692-d417-4d9f-a196-84205b8314b3`;
GRANT USE SCHEMA  ON SCHEMA  genie_zeroops_mfg_catalog.default             TO `a048a692-d417-4d9f-a196-84205b8314b3`;
GRANT SELECT      ON TABLE   maintenance_manual_chunks                     TO `a048a692-d417-4d9f-a196-84205b8314b3`;
GRANT SELECT      ON TABLE   maintenance_manual_index                      TO `a048a692-d417-4d9f-a196-84205b8314b3`;
GRANT READ VOLUME ON VOLUME  maintenance_manuals                           TO `a048a692-d417-4d9f-a196-84205b8314b3`;

-- -----------------------------------------------------------------------------
-- 4. Verification (evidence)
-- -----------------------------------------------------------------------------
-- Row filters / masks in force
SELECT table_name, filter_name, target_columns FROM information_schema.row_filters  WHERE table_schema = 'default';
SELECT table_name, column_name, mask_name     FROM information_schema.column_masks WHERE table_schema = 'default';

-- Ownership tags
SHOW TBLPROPERTIES ml_component_failure_forecast ('parker.data_owner');
SELECT table_name, tag_name, tag_value FROM information_schema.table_tags
WHERE schema_name = 'default' AND tag_name = 'quality' ORDER BY table_name;

-- What the app identity can do
SHOW GRANTS `a048a692-d417-4d9f-a196-84205b8314b3` ON SCHEMA genie_zeroops_mfg_catalog.default;

-- -----------------------------------------------------------------------------
-- 5. Lineage: installed-base tables from source to forecast (system tables)
-- -----------------------------------------------------------------------------
SELECT source_table_full_name, target_table_full_name, entity_type, max(event_time) AS last_seen
FROM system.access.table_lineage
WHERE target_table_full_name LIKE 'genie_zeroops_mfg_catalog.default.%'
  AND (target_table_full_name RLIKE 'component|customer_operations|maintenance_(compliance|anomalies)|failure_forecast|manual'
       OR source_table_full_name RLIKE 'bronze_(components|maintenance|component_telemetry|customer|parker)')
  AND source_table_full_name IS NOT NULL
GROUP BY ALL
ORDER BY target_table_full_name, source_table_full_name;
