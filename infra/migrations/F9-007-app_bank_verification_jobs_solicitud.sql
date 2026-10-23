-- F9-007 · app_bank_verification_jobs: solicitud del job (modo factura / modo pago)
--
-- POR QUE: el contrato de verificacion pasa a tener dos modos. En modo "pago"
-- no hay factura: el POS manda solo el importe (y opcionalmente el NIT y el
-- nombre del cliente). Esos datos tienen que llegar al worker, que corre en
-- otro hilo y reconstruye el job desde la fila.
--
-- Se guarda en una columna aparte (y no dentro de `resultado_json`) porque
-- `resultado_json` es la SALIDA del job y se limpia en cada reintento
-- (`_SQL_REVIVIR`); la solicitud tiene que sobrevivir al reintento.
--
-- Es aditiva y reversible: la columna es NULL-able y ningun lector viejo la
-- mira. Rollback al final del archivo.
--
-- Uso:
--   mysql -u root motoshop2024 < infra\migrations\F9-007-app_bank_verification_jobs_solicitud.sql

ALTER TABLE app_bank_verification_jobs
  ADD COLUMN solicitud_json TEXT COLLATE utf8_unicode_ci NULL AFTER resultado_json;

SELECT 'F9-007' AS migration, 'app_bank_verification_jobs' AS table_name,
       COUNT(*) AS columna_presente
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_bank_verification_jobs'
  AND COLUMN_NAME = 'solicitud_json';

-- ROLLBACK (reversible; no borra datos de negocio, solo la columna nueva):
--   ALTER TABLE app_bank_verification_jobs DROP COLUMN solicitud_json;
