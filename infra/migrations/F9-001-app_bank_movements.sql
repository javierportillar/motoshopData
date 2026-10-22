-- ============================================================
-- F9-001 · app_bank_movements
--
-- Ingesta de los movimientos bancarios (transferencias leídas del portal
-- de Bancolombia). La idempotencia es de la tabla, no del código:
-- `UNIQUE KEY uq_tenant_id_externo (tenant, id_externo)` obliga a que la
-- reingesta actualice la fila existente (INSERT ... ON DUPLICATE KEY UPDATE)
-- en vez de crear un duplicado. La identidad (`id` = uuid5 del dominio)
-- nunca se reescribe.
--
-- Compatibilidad: MySQL 5.0+ (same rules as F5-001)
--   - utf8 instead of utf8mb4 (does not exist on 5.0)
--   - DATETIME sin DEFAULT CURRENT_TIMESTAMP (sólo TIMESTAMP admite el
--     default automático en 5.0): `scraped_at` lo escribe la aplicación
--   - No CHECK constraints (validation lives in Pydantic/app code)
--
-- Uso:
--   python -m infra.migrations.run_migrations --prefix F9
--   (from the repository root; needs a privileged MySQL user)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_bank_movements;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_bank_movements (
  id               VARCHAR(36)      NOT NULL,
  tenant           VARCHAR(32)      NOT NULL,
  empresa          VARCHAR(15)      NOT NULL DEFAULT '',
  id_externo       VARCHAR(64)      NOT NULL,
  fecha_movimiento DATE             NOT NULL,
  valor            DECIMAL(18,2)    NOT NULL DEFAULT 0.00,
  descripcion      VARCHAR(255)     NOT NULL DEFAULT '',
  referencia       VARCHAR(64)      NOT NULL DEFAULT '',
  referencia_norm  VARCHAR(64)      NOT NULL DEFAULT '',
  pagador_nombre   VARCHAR(128)     NOT NULL DEFAULT '',
  cuenta_origen    VARCHAR(64)      NOT NULL DEFAULT '',
  estado           ENUM('PENDIENTE','APLICADO','AMBIGUA','SIN_MATCH',
                         'SOBREPAGO','IGNORADO')
                                   NOT NULL DEFAULT 'PENDIENTE',
  recibo_numero    VARCHAR(32)      NULL,
  recibo_pref      VARCHAR(8)       NULL,
  confianza        INT              NULL,
  razones          VARCHAR(500)     NULL,
  scraped_at       DATETIME         NULL,

  PRIMARY KEY (id),
  UNIQUE KEY uq_tenant_id_externo (tenant, id_externo),
  INDEX idx_estado_fecha (tenant, estado, fecha_movimiento)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F9-001' AS migration, 'app_bank_movements' AS table_name,
       COUNT(*) AS index_count
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_bank_movements'
  AND INDEX_NAME != 'PRIMARY';
