-- ============================================================
-- F8-002 · app_idempotency
--
-- Idempotency convention store for transactional document saves
-- (F5-001 pattern: table keyed by a UUIDv4 Idempotency-Key with a
-- UNIQUE constraint). φ0 precheck replays the stored response and
-- short-circuits before numbering, so contadores never advances twice.
--
-- Compatibilidad: MySQL 5.0+ (same rules as F5-001)
--   - utf8 instead of utf8mb4
--   - TIMESTAMP instead of DATETIME defaults
--
-- Uso:
--   motoshop-app\api\.venv\Scripts\python.exe -m infra.migrations.run_migrations
--   (from the repository root; needs a privileged MySQL user)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_idempotency;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_idempotency (
  id             INT UNSIGNED      AUTO_INCREMENT PRIMARY KEY,
  idempotency_key VARCHAR(64)      NOT NULL,
  doc_type       VARCHAR(32)       NOT NULL DEFAULT '',
  tenant         VARCHAR(32)       NOT NULL,
  actor          VARCHAR(64)       NOT NULL DEFAULT '',
  request_id     VARCHAR(64)       NOT NULL DEFAULT '',
  response_json  TEXT              NULL,
  created_at     TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP,

  UNIQUE KEY uq_idempotency_key (idempotency_key),
  INDEX idx_tenant_created (tenant, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F8-002' AS migration, 'app_idempotency' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_idempotency'
  AND INDEX_NAME = 'uq_idempotency_key';
