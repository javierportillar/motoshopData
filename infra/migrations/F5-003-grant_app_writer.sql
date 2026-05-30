-- ============================================================
-- F5-003 · Usuario MySQL app_writer
--
-- Nuevo usuario para operaciones de escritura desde la API.
-- Solo INSERT/SELECT sobre tablas app_* (InnoDB) y SELECT
-- sobre sgHermes (MyISAM) para validar alert_id/SKU.
--
-- ⚠️ ANTES DE EJECUTAR: reemplazar <PASTE_APP_WRITER_PASSWORD>
-- por una contraseña fuerte.
--
-- La contraseña REAL va en:
--   motoshop-app/api/.env → MYSQL_APP_WRITER_PASSWORD=<password>
--   infra/.env            → MYSQL_APP_WRITER_PASSWORD=<password>
--
-- NUNCA hardcodear la contraseña en este archivo.
--
-- Compatibilidad: MySQL 5.0+
--   - SET PASSWORD FOR ... = PASSWORD('...') en vez de ALTER USER
--   - No usa IF NOT EXISTS ni DROP IF EXISTS
--   - Si el usuario ya existe, ejecutar primero el bloque
--     de DROP USER comentado al final
--
-- Uso:
--   mysql -u root < infra/migrations/F5-003-grant_app_writer.sql
--
-- Rollback (si existe):
--   DROP USER 'app_writer'@'localhost';
--   FLUSH PRIVILEGES;
-- ============================================================

CREATE USER 'app_writer'@'localhost'
  IDENTIFIED BY '<PASTE_APP_WRITER_PASSWORD>';

-- Acceso de escritura a tablas app_* (InnoDB)
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`app_alert_actions` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT ON `motoshop2024`.`app_audit_log` TO 'app_writer'@'localhost';

-- Acceso de lectura a sgHermes (para validar alert_id/SKU contra gold)
GRANT SELECT ON `motoshop2024`.* TO 'app_writer'@'localhost';

FLUSH PRIVILEGES;

-- ─── Verificación ────────────────────────────────────────────
SELECT 'F5-003' AS migration, 'app_writer' AS usuario_creado,
       COUNT(*) AS privilege_count
FROM information_schema.USER_PRIVILEGES
WHERE GRANTEE LIKE '%app_writer%';

-- ─── Rotación de contraseña (si el usuario ya existe) ────────
-- SET PASSWORD FOR 'app_writer'@'localhost' = PASSWORD('<NEW_PASSWORD>');
-- FLUSH PRIVILEGES;

-- ─── Limpieza (para recrear) ─────────────────────────────────
-- DROP USER 'app_writer'@'localhost';
-- FLUSH PRIVILEGES;
