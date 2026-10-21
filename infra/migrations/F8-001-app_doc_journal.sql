-- ============================================================
-- F8-001 · app_doc_journal
--
-- Write-ahead intent journal for transactional web ERP documents.
-- MUST be the first write of every save (before numbering or any
-- legacy insert): PENDING → COMMITTED|FAILED|ANNULLED lifecycle.
--
-- Compatibilidad: MySQL 5.0+ (same rules as F5-001)
--   - utf8 instead of utf8mb4 (does not exist on 5.0)
--   - TIMESTAMP with DEFAULT CURRENT_TIMESTAMP (DATETIME default
--     requires MySQL 5.6.5+); updated_at is app-managed
--   - No CHECK constraints (validation lives in Pydantic/app code)
--
-- Uso:
--   motoshop-app\api\.venv\Scripts\python.exe -m infra.migrations.run_migrations
--   (from the repository root; needs a privileged MySQL user)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_doc_journal;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_doc_journal (
  id              INT UNSIGNED      AUTO_INCREMENT PRIMARY KEY,
  codclas         VARCHAR(4)        NOT NULL,
  pref            VARCHAR(8)        NOT NULL DEFAULT '',
  docnum          INT               NULL,
  status          ENUM('PENDING','COMMITTED','FAILED','ANNULLED') NOT NULL,
  doc_type        VARCHAR(32)       NOT NULL DEFAULT '',
  tenant          VARCHAR(32)       NOT NULL,
  empresa         VARCHAR(15)       NOT NULL DEFAULT '',
  actor           VARCHAR(64)       NOT NULL,
  request_id      VARCHAR(64)       NOT NULL DEFAULT '',
  idempotency_key VARCHAR(64)       NULL,
  error_msg       VARCHAR(500)      NULL,
  created_at      TIMESTAMP         NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP         NULL,

  INDEX idx_status_created (status, created_at),
  INDEX idx_tenant_status (tenant, status),
  INDEX idx_codclas_docnum (codclas, pref, docnum),
  INDEX idx_idempotency (idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F8-001' AS migration, 'app_doc_journal' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_doc_journal'
  AND INDEX_NAME != 'PRIMARY';
