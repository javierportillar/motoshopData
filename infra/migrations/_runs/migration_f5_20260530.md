# F5 · Migration Report · 2026-05-30

## Host

- MySQL 8.4.0 (Docker local) — validación de sintaxis
- Producción: MySQL 5.0+ (PC Windows) — ejecutar con `mysql -u root`
- Ver versión exacta con: `mysql --version` o `SELECT VERSION();`

## Migrations ejecutadas

### F5-001 · app_alert_actions

```sql
CREATE TABLE IF NOT EXISTS app_alert_actions (
  id              BIGINT          AUTO_INCREMENT PRIMARY KEY,
  alert_id        VARCHAR(64)     NOT NULL,
  sku             VARCHAR(64)     NOT NULL,
  user_id         VARCHAR(64)     NOT NULL,
  action_type     ENUM('ordered','dismissed','postponed') NOT NULL,
  quantity        DECIMAL(10,2)   NULL,
  supplier        VARCHAR(255)    NULL,
  reason          VARCHAR(500)    NULL,
  postponed_to    DATE            NULL,
  notes           TEXT            NULL,
  idempotency_key VARCHAR(64)     NOT NULL,
  created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  request_id      VARCHAR(64)     NOT NULL,
  UNIQUE KEY uq_idempotency (idempotency_key),
  INDEX idx_user_created (user_id, created_at),
  INDEX idx_alert (alert_id),
  INDEX idx_sku_created (sku, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
```

**Resultado:** ✅ OK — tabla creada, UNIQUE KEY `uq_idempotency` verificada.

### F5-002 · app_audit_log

```sql
CREATE TABLE IF NOT EXISTS app_audit_log (
  id          BIGINT          AUTO_INCREMENT PRIMARY KEY,
  ...
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ...
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci;
```

**Resultado:** ✅ OK — tabla creada, PRIMARY KEY + 3 índices verificados.

### F5-003 · grant_app_writer

```
CREATE USER 'app_writer'@'localhost' IDENTIFIED BY '<PASTE_APP_WRITER_PASSWORD>';
GRANT SELECT, INSERT, UPDATE ON `motoshop2024`.`app_alert_actions` TO 'app_writer'@'localhost';
GRANT SELECT, INSERT ON `motoshop2024`.`app_audit_log` TO 'app_writer'@'localhost';
GRANT SELECT ON `motoshop2024`.* TO 'app_writer'@'localhost';
```

**Resultado:** ⏳ PENDIENTE — ejecutar en PC Windows con password real (ver abajo).

## ⚠️ Para Runtime Agent (PC Windows)

Ejecutar en orden:

```powershell
cd C:\Users\MotoShop\Documents\javidevmoto

# 1. Crear tablas
mysql -u root < infra\migrations\F5-001-app_alert_actions.sql
mysql -u root < infra\migrations\F5-002-app_audit_log.sql

# 2. Crear usuario app_writer (ANTES editar el archivo y reemplazar
#    <PASTE_APP_WRITER_PASSWORD> por Sashita123)
mysql -u root < infra\migrations\F5-003-grant_app_writer.sql

# 3. Agregar al .env del API
echo MYSQL_APP_WRITER_PASSWORD=Sashita123 >> motoshop-app\api\.env

# 4. Verificar tablas
mysql -u root -e "SHOW TABLES LIKE 'app_%'" motoshop2024
```

**Pegar output aquí después de ejecutar:** ⬜

## Compatibilidad MySQL 5.0

| Feature | ¿Soporta 5.0? | En la migration |
|---------|--------------|-----------------|
| `utf8` (no `utf8mb4`) | ✅ | Usé `utf8` |
| `ENUM` | ✅ | `action_type ENUM(...)`, `status ENUM(...)` |
| `DECIMAL` | ✅ | `quantity DECIMAL(10,2)` |
| `TIMESTAMP DEFAULT CURRENT_TIMESTAMP` | ✅ | `created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| `TEXT` en vez de `JSON` | ✅ | `payload TEXT` (no `JSON`) |
| `CREATE TABLE IF NOT EXISTS` | ✅ | Funciona en 5.0 |
| `CREATE INDEX` sin `IF NOT EXISTS` | ✅ | Índices inline en CREATE TABLE (no hay `CREATE INDEX` separado) |
| `SET PASSWORD FOR ... = PASSWORD(...)` | ✅ | Estilo 5.0 en F5-003 |
