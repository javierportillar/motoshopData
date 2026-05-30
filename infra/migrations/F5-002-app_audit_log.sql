-- ============================================================
-- F5-002 · app_audit_log
--
-- Registro de auditoría para TODAS las escrituras de F5+.
-- Cada acción sobre app_* genera una entry aquí.
--
-- Compatibilidad: MySQL 5.0+
--   - payload como TEXT (JSON no existe en 5.0; la app serializa
--     JSON a string antes de insertar)
--   - utf8 en lugar de utf8mb4
--   - TIMESTAMP en lugar de DATETIME (ver F5-001)
--
-- Uso:
--   mysql -u root < infra/migrations/F5-002-app_audit_log.sql
--
-- Rollback:
--   DROP TABLE IF EXISTS app_audit_log;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_audit_log (
  id          BIGINT          AUTO_INCREMENT PRIMARY KEY,
  user_id     VARCHAR(64)     NOT NULL,
  user_role   VARCHAR(32)     NOT NULL,
  action      VARCHAR(64)     NOT NULL,
  target_type VARCHAR(64)     NOT NULL,
  target_id   VARCHAR(64)     NOT NULL,
  request_id  VARCHAR(64)     NOT NULL,
  ip_address  VARCHAR(45)     NULL,
  user_agent  VARCHAR(500)    NULL,
  payload     TEXT            NULL,
  status      ENUM('success','failure') NOT NULL,
  error_msg   VARCHAR(500)    NULL,
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

  INDEX idx_user_created (user_id, created_at),
  INDEX idx_target (target_type, target_id),
  INDEX idx_action_created (action, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F5-002' AS migration, 'app_audit_log' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.TABLES t
JOIN information_schema.TABLE_CONSTRAINTS c USING (TABLE_SCHEMA, TABLE_NAME)
WHERE t.TABLE_SCHEMA = DATABASE()
  AND t.TABLE_NAME = 'app_audit_log'
  AND c.CONSTRAINT_TYPE = 'PRIMARY';
