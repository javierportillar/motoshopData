-- ============================================================
-- F10-004 · contador de intentos de ejecución
--
-- El rescate de un job `ejecutando` vencido lo devuelve a `en_cola` con
-- `intentos + 1`. Al segundo intento queda `fallido` con
-- `ejecucion_vencida`. Sin esta columna no hay forma de distinguir "se
-- colgó una vez" de "se cuelga siempre" ni de cortar el bucle.
--
-- Archivo separado a propósito: si la columna ya existe (instalación previa),
-- este ALTER falla solo y el resto de F10 se aplica igual. El runner tolera
-- el error 1060 (Duplicate column name) y sigue.
--
-- Requiere una base activa (MySQL 5.0 falla con ERROR 1046 si no la hay):
--   mysql --user root --password= --database=masvital -e "SOURCE infra/migrations/F10-004-app_bank_verification_jobs_intentos.sql"
--
-- Rollback:
--   ALTER TABLE app_bank_verification_jobs DROP COLUMN intentos;
-- ============================================================

ALTER TABLE app_bank_verification_jobs
  ADD COLUMN intentos INT NOT NULL DEFAULT 0;

SELECT 'F10-004' AS migration, 'app_bank_verification_jobs' AS table_name, COUNT(*) AS tiene_intentos
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_bank_verification_jobs'
  AND COLUMN_NAME = 'intentos';
