-- ============================================================
-- F10-001 · app_bank_nodes
--
-- Registro de los nodos que sirven verificaciones bancarias. Cada nodo late
-- cada 30 s (heartbeat) con los tenants que atiende y sus slots. El plano de
-- control (la API) lo usa para decidir a quién entregarle un job y para
-- saber si el nodo primario de un tenant está caído (>90 s sin latir).
--
-- El nodo NO raspa desde la API: raspa un proceso aparte en la PC del
-- cliente. Esta tabla es sólo el estado de contacto.
--
-- Compatibilidad: MySQL 5.0+ (mismas reglas que F9-003)
--   - utf8 (utf8mb4 no existe en 5.0)
--   - DATETIME sin DEFAULT CURRENT_TIMESTAMP: los instantes los escribe la
--     aplicación, siempre en UTC naive (misma convención que los jobs)
--   - Sin CHECK constraints (la validación vive en el código)
--
-- Rollback:
--   DROP TABLE IF EXISTS app_bank_nodes;
-- ============================================================

CREATE TABLE IF NOT EXISTS app_bank_nodes (
  node_id         VARCHAR(64)      NOT NULL,
  tenants         VARCHAR(255)     NOT NULL,
  slots_libres    INT              NOT NULL DEFAULT 1,
  slots_ocupados  INT              NOT NULL DEFAULT 0,
  version         VARCHAR(32)      NULL,
  latida_en       DATETIME         NOT NULL,
  visto_en        DATETIME         NULL,

  PRIMARY KEY (node_id),
  KEY idx_latida (latida_en)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;

SELECT 'F10-001' AS migration, 'app_bank_nodes' AS table_name, COUNT(*) AS columnas
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'app_bank_nodes';
