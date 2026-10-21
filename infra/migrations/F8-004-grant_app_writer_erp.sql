-- F8-004 grant_app_writer_erp.sql
-- Grants the app_writer user the DML permissions the transactional write path
-- needs (journal + idempotency + migration ledger) and the legacy tables the
-- slices 2-5 modules write (verband, stock, numbering).
--
-- F5-003 parity: grants were never automated by the app; they are checkpoint
-- applied by whoever operates the checkpoint environment (needs ALL PRIVILEGES
-- or GRANT OPTION, e.g. root) — the app_writer user itself is a SELECT-only
-- "analytics" alias and cannot self-grant. If the app_writer user does not
-- exist yet, run F5-003 first.
--
-- MySQL 5.0.45 per-table GRANT statements. Run inside a workdir with MySQL
-- client privileges, like this:
--   mysql --user root --password= motoshop2024 -e "SOURCE infra/migrations/F8-004-grant_app_writer_erp.sql" 2>&1
--
-- app_* foundation tables (write path owns these rows outright)
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`app_doc_journal` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`app_idempotency` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`app_migration_state` TO 'app_writer'@'localhost';

-- Sales (slice 3): invoice headers and line items
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`facventas` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`detfventas` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`detapago` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`detcuentas` TO 'app_writer'@'localhost';

-- Stock (slice 3): product master carries `existencia` stock; ubiprodbod is
-- the per-warehouse allocation.
GRANT SELECT, UPDATE ON `motoshop2024`.`productos` TO 'app_writer'@'localhost';
GRANT SELECT, UPDATE ON `motoshop2024`.`ubiprodbod` TO 'app_writer'@'localhost';

-- Numbering (slice 3): contadores is managed with LOCK TABLES
GRANT SELECT, UPDATE ON `motoshop2024`.`contadores` TO 'app_writer'@'localhost';

-- Purchases (slice 3): received-goods change headers and line items
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`compras` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`detcompras` TO 'app_writer'@'localhost';
