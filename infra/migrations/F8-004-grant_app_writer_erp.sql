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
-- The target database is NOT hardcoded: the table names are unqualified, so
-- every grant resolves against the ACTIVE database of the session. A default
-- database must therefore be selected before running this file; otherwise
-- MySQL 5.0 fails with ERROR 1046 (No database selected).
--
--   mysql --user root --password= --database=masvital -e "SOURCE infra/migrations/F8-004-grant_app_writer_erp.sql"
--
-- The migrations runner already connects with the --database it was given, so
-- `python -m infra.migrations.run_migrations --database <db>` applies this file
-- to the right schema without editing it.

-- app_* foundation tables (write path owns these rows outright)
GRANT SELECT, INSERT, UPDATE ON `app_doc_journal` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `app_idempotency` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `app_migration_state` TO 'app_writer'@'localhost';

-- Sales (slice 3): invoice headers and line items
GRANT SELECT, INSERT, UPDATE ON `facventas` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `detfventas` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `detapago` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `detcuentas` TO 'app_writer'@'localhost';

-- Stock (slice 3): product master carries `existencia` stock; ubiprodbod is
-- the per-warehouse allocation.
GRANT SELECT, UPDATE ON `productos` TO 'app_writer'@'localhost';
GRANT SELECT, UPDATE ON `ubiprodbod` TO 'app_writer'@'localhost';

-- Numbering (slice 3): contadores is managed with LOCK TABLES
GRANT SELECT, UPDATE ON `contadores` TO 'app_writer'@'localhost';

-- Purchases (slice 3): received-goods change headers and line items
GRANT SELECT, INSERT, UPDATE ON `compras` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT, UPDATE ON `detcompras` TO 'app_writer'@'localhost';

-- Numbering latch (slice 3): MySQL 5.0 has NO per-table LOCK TABLES privilege;
-- it is database-scoped, so it cannot be written with an unqualified table
-- name. Run this ONCE per database, replacing <db> with the real name:
--
--   GRANT LOCK TABLES ON `<db>`.* TO 'app_writer'@'localhost';
--
-- Without it the `contadores` reservation fails with ERROR 1044 and the sale
-- never reaches the legacy rows (the table-level grants above are not enough).

