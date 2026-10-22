-- ============================================================
-- F9-003 · app_bank_verification_jobs
--
-- Jobs de la verificación bancaria asíncrona. El scrape del portal tarda
-- 10–40 s, así que no cabe en un request HTTP: el verificador crea un job
-- (`POST /api/erp/bank/verificaciones` → 202) y el nodo local lo corre; el
-- front sondea `GET /api/erp/bank/verificaciones/{job_id}`.
--
-- Dos identidades, a propósito:
--   - `id`     = uuid5 del dominio (`tenant:factura_id:valor`): es la PK y
--                hace idempotente la creación (el mismo job no se duplica);
--   - `job_id` = uuid4 público: es el que viaja en la URL y el que sondea el
--                front (único por job, nunca adivinable).
--
-- El importe es `DECIMAL(18,2)` (nunca float). `estado` es el ENUM del
-- contrato: en_cola · ejecutando · esperando_otp · resuelto ·
-- sin_coincidencia · ambiguo · fallido · expirado.
--
-- Compatibilidad: MySQL 5.0+ (same rules as F5-001)
--   - utf8 instead of utf8mb4 (does not exist on 5.0)
--   - DATETIME sin DEFAULT CURRENT_TIMESTAMP (sólo TIMESTAMP admite el
--     default automático en 5.0): los tres instantes los escribe la
--     aplicación
--   - No CHECK constraints (validation lives in Pydantic/app code)
--
-- Uso:
--   python -m infra.migrations.run_migrations --prefix F9
--   (from the repository root; needs a privileged MySQL user)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_bank_verification_jobs;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_bank_verification_jobs (
  id              VARCHAR(36)      NOT NULL,
  job_id          VARCHAR(36)      NOT NULL,
  tenant          VARCHAR(32)      NOT NULL,
  factura_id      VARCHAR(64)      NOT NULL,
  valor           DECIMAL(18,2)    NOT NULL DEFAULT 0.00,
  estado          ENUM('en_cola','ejecutando','esperando_otp','resuelto',
                       'sin_coincidencia','ambiguo','fallido','expirado')
                                 NOT NULL DEFAULT 'en_cola',
  nodo            VARCHAR(64)      NULL,
  resultado_json  TEXT             NULL,
  error_codigo    VARCHAR(64)      NULL,
  creado_en       DATETIME         NOT NULL,
  actualizado_en  DATETIME         NOT NULL,
  expira_en       DATETIME         NOT NULL,

  PRIMARY KEY (id),
  UNIQUE KEY uq_job_id (job_id),
  KEY idx_tenant_estado_creado (tenant, estado, creado_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F9-003' AS migration, 'app_bank_verification_jobs' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_bank_verification_jobs'
  AND INDEX_NAME != 'PRIMARY';
