-- ============================================================
-- F9-002 · grant_app_writer_bank
--
-- Permisos del usuario `app_writer` sobre la tabla de la ingesta
-- bancaria (`app_bank_movements`). Mismo patrón que F5-003 / F8-004:
-- los grants NUNCA los automatiza la aplicación; los aplica el operador
-- del entorno, que necesita ALL PRIVILEGES o GRANT OPTION (p. ej. root).
-- El usuario `app_writer` es un alias de sólo SELECT y no puede
-- auto-concederse permisos. Si el usuario no existe, ejecuta F5-003 primero.
--
-- La base de datos NO está fijada: los nombres de tabla no están
-- cualificados, así que cada grant se resuelve contra la base ACTIVA de
-- la sesión. Hay que seleccionar una base antes de correr este archivo;
-- si no, MySQL 5.0 falla con ERROR 1046 (No database selected).
--
--   mysql --user root --password= --database=masvital -e "SOURCE infra/migrations/F9-002-grant_app_writer_bank.sql"
--
-- El runner de migraciones ya conecta con la base que se le indique, así que
-- `python -m infra.migrations.run_migrations --prefix F9` aplica este archivo
-- al esquema correcto sin editarlo.
--
-- Rollback (si existe):
--   REVOKE SELECT, INSERT, UPDATE ON `app_bank_movements` FROM 'app_writer'@'localhost';
-- ============================================================

-- Ingesta bancaria: la API lee, inserta y cambia el estado de los movimientos.
-- Nunca borra: un movimiento no se elimina, se marca IGNORADO.
GRANT SELECT, INSERT, UPDATE ON `app_bank_movements` TO 'app_writer'@'localhost';

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F9-002' AS migration, 'app_writer' AS usuario,
       COUNT(*) AS privilege_count
FROM information_schema.SCHEMA_PRIVILEGES
WHERE GRANTEE = "'app_writer'@'localhost'"
  AND TABLE_NAME = 'app_bank_movements';
