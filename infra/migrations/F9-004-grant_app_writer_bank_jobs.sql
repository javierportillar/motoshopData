-- ============================================================
-- F9-004 Â· grant_app_writer_bank_jobs
--
-- Permisos del usuario `app_writer` sobre la tabla de los jobs de
-- verificaciÃ³n (`app_bank_verification_jobs`). Mismo patrÃ³n que F9-002:
-- los grants NUNCA los automatiza la aplicaciÃ³n; los aplica el operador
-- del entorno, que necesita ALL PRIVILEGES o GRANT OPTION (p. ej. root).
-- El usuario `app_writer` es un alias de sÃ³lo SELECT y no puede
-- auto-concederse permisos. Si el usuario no existe, ejecuta F5-003 primero.
--
-- La base de datos NO estÃ¡ fijada: los nombres de tabla no estÃ¡n
-- cualificados, asÃ­ que cada grant se resuelve contra la base ACTIVA de la
-- sesiÃ³n. Hay que seleccionar una base antes de correr este archivo;
-- si no, MySQL 5.0 falla con ERROR 1046 (No database selected).
--
--   mysql --user root --password= --database=masvital -e "SOURCE infra/migrations/F9-004-grant_app_writer_bank_jobs.sql"
--
-- El runner de migraciones ya conecta con la base que se le indique, asÃ­ que
-- `python -m infra.migrations.run_migrations --prefix F9` aplica este archivo
-- al esquema correcto sin editarlo.
--
-- Rollback (si existe):
--   REVOKE SELECT, INSERT, UPDATE ON `app_bank_verification_jobs` FROM 'app_writer'@'localhost';
-- ============================================================

-- Jobs de verificaciÃ³n: la API crea el job, el nodo actualiza su estado y
-- escribe el resultado. Nunca borra: un job caducado pasa a `expirado`.
GRANT SELECT, INSERT, UPDATE ON `app_bank_verification_jobs` TO 'app_writer'@'localhost';

-- â”€â”€â”€ VerificaciÃ³n â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SELECT 'F9-004' AS migration, 'app_writer' AS usuario,
       COUNT(*) AS privilege_count
FROM information_schema.TABLE_PRIVILEGES
WHERE GRANTEE = "'app_writer'@'localhost'"
  AND TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_bank_verification_jobs';
