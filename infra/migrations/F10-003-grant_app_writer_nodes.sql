-- ============================================================
-- F10-003 · grants de app_writer sobre el plano de control
--
-- La API (app_writer) late, adquiere/renueva/libera candados y reclama jobs.
-- Mismo patrón que F9-002/F9-004: los grants los aplica el operador con un
-- usuario privilegiado, nunca la aplicación.
--
-- Requiere una base activa (MySQL 5.0 falla con ERROR 1046 si no la hay):
--   mysql --user root --password= --database=masvital -e "SOURCE infra/migrations/F10-003-grant_app_writer_nodes.sql"
--
-- Rollback:
--   REVOKE SELECT, INSERT, UPDATE, DELETE ON `app_bank_account_locks` FROM 'app_writer'@'localhost';
--   REVOKE SELECT, INSERT, UPDATE ON `app_bank_nodes` FROM 'app_writer'@'localhost';
-- ============================================================

GRANT SELECT, INSERT, UPDATE ON `app_bank_nodes` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON `app_bank_account_locks` TO 'app_writer'@'localhost';

SELECT 'F10-003' AS migration, 'app_writer' AS usuario, COUNT(*) AS privilege_count
FROM information_schema.TABLE_PRIVILEGES
WHERE GRANTEE = "'app_writer'@'localhost'"
  AND TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('app_bank_nodes', 'app_bank_account_locks');
