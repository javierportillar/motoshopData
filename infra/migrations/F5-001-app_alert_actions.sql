-- ============================================================
-- F5-001 · app_alert_actions
--
-- Tabla InnoDB para registrar acciones del usuario sobre alertas
-- de quiebre de stock desde la PWA.
--
-- Compatibilidad: MySQL 5.0+
--   - utf8 en lugar de utf8mb4 (no existe en 5.0)
--   - TIMESTAMP en lugar de DATETIME (DEFAULT CURRENT_TIMESTAMP
--     en DATETIME requiere MySQL 5.6.5+)
--   - Sin CHECK constraints (se parsean pero se ignoran en 5.0;
--     la validación va en la app con Pydantic)
--
-- Uso:
--   mysql -u root < infra/migrations/F5-001-app_alert_actions.sql
--
-- Rollback:
--   DROP TABLE IF EXISTS app_alert_actions;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_alert_actions (
  id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
  alert_id        VARCHAR(64)     NOT NULL,
  sku             VARCHAR(64)     NOT NULL,
  user_id         VARCHAR(64)     NOT NULL,
  action_type     ENUM('ordered','dismissed','postponed') NOT NULL,
  quantity        DECIMAL(10,2)   NULL,
  supplier        VARCHAR(255)    NULL,
  reason          VARCHAR(500)    NULL,
  postponed_to    DATE            NULL,
  notes           TEXT            NULL,
  idempotency_key VARCHAR(64)     NOT NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  request_id      VARCHAR(64)     NOT NULL,

  UNIQUE KEY uq_idempotency (idempotency_key),
  INDEX idx_user_created (user_id, created_at),
  INDEX idx_alert (alert_id),
  INDEX idx_sku_created (sku, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F5-001' AS migration, 'app_alert_actions' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.TABLES t
JOIN information_schema.TABLE_CONSTRAINTS c USING (TABLE_SCHEMA, TABLE_NAME)
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_NAME = 'app_alert_actions'
  AND c.CONSTRAINT_TYPE = 'UNIQUE';
