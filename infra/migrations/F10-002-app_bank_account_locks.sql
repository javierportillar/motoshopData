-- ============================================================
-- F10-002 · app_bank_account_locks
--
-- Candado por CUENTA (tenant), no por máquina. El banco permite dos cuentas
-- abiertas a la vez (son usuarios distintos) pero NO la misma cuenta en dos
-- dispositivos: cierra la anterior con "Tienes otra sesión abierta". Por eso
-- el candado es del tenant y lo sostiene un solo nodo a la vez.
--
-- PK `tenant`: una fila por cuenta. `vence_en` es el TTL (60 s); el nodo lo
-- renueva cada 20 s mientras raspa. Sin preempción: si el candado está vivo
-- nadie lo arrebata, aunque el dueño esté lento (se le rescata al vencer).
--
-- Adquisición atómica: INSERT ... ON DUPLICATE KEY UPDATE con la condición
-- (vence_en < now OR node_id = yo) en cada columna. Gana uno solo.
--
-- Compatibilidad: MySQL 5.0+ (mismas reglas que F9-003)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_bank_account_locks;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_bank_account_locks (
  tenant      VARCHAR(32)   NOT NULL,
  node_id     VARCHAR(64)   NOT NULL,
  latida_en   DATETIME      NOT NULL,
  vence_en    DATETIME      NOT NULL,

  PRIMARY KEY (tenant),
  KEY idx_vence (vence_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

SELECT 'F10-002' AS migration, 'app_bank_account_locks' AS table_name, COUNT(*) AS columnas
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'app_bank_account_locks';
