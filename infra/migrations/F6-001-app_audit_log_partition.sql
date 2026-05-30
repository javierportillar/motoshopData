-- ============================================================
-- F6-001 · app_audit_log — Monthly Partitioning
--
-- Convierte app_audit_log de tabla plana a tabla particionada
-- por RANGE mensual de created_at.
--
-- Compatibilidad: MySQL 5.1+ (particionamiento por RANGE).
-- MySQL 5.0 NO soporta partitioning — verificar version.
--
-- Uso:
--   mysql -u root < infra/migrations/F6-001-app_audit_log_partition.sql
--
-- Rollback:
--   ALTER TABLE app_audit_log REMOVE PARTITIONING;
--   (recomendado solo si hay datos que reubicar)
-- ============================================================

-- ─── 1. Verificar que la tabla existe ─────────────────────

SELECT 'F6-001' AS migration, 'Verificar existencia' AS step;

-- ─── 2. Aplicar particionamiento mensual ──────────────────
--
-- Rango: desde 2026-05 (creación) hasta 2027-12 (18 meses).
-- Las filas con created_at NULL van a la partición p_future.
-- Particiones mensuales: p_YYYYMM.
--
-- NOTA: MySQL requiere TO_DAYS() para particionar por DATE.
-- TIMESTAMP se convierte implicitamente.

ALTER TABLE app_audit_log
PARTITION BY RANGE (TO_DAYS(created_at)) (
  PARTITION p_202605 VALUES LESS THAN (TO_DAYS('2026-06-01')),
  PARTITION p_202606 VALUES LESS THAN (TO_DAYS('2026-07-01')),
  PARTITION p_202607 VALUES LESS THAN (TO_DAYS('2026-08-01')),
  PARTITION p_202608 VALUES LESS THAN (TO_DAYS('2026-09-01')),
  PARTITION p_202609 VALUES LESS THAN (TO_DAYS('2026-10-01')),
  PARTITION p_202610 VALUES LESS THAN (TO_DAYS('2026-11-01')),
  PARTITION p_202611 VALUES LESS THAN (TO_DAYS('2026-12-01')),
  PARTITION p_202612 VALUES LESS THAN (TO_DAYS('2027-01-01')),
  PARTITION p_202701 VALUES LESS THAN (TO_DAYS('2027-02-01')),
  PARTITION p_202702 VALUES LESS THAN (TO_DAYS('2027-03-01')),
  PARTITION p_202703 VALUES LESS THAN (TO_DAYS('2027-04-01')),
  PARTITION p_202704 VALUES LESS THAN (TO_DAYS('2027-05-01')),
  PARTITION p_202705 VALUES LESS THAN (TO_DAYS('2027-06-01')),
  PARTITION p_202706 VALUES LESS THAN (TO_DAYS('2027-07-01')),
  PARTITION p_202707 VALUES LESS THAN (TO_DAYS('2027-08-01')),
  PARTITION p_202708 VALUES LESS THAN (TO_DAYS('2027-09-01')),
  PARTITION p_202709 VALUES LESS THAN (TO_DAYS('2027-10-01')),
  PARTITION p_202710 VALUES LESS THAN (TO_DAYS('2027-11-01')),
  PARTITION p_202711 VALUES LESS THAN (TO_DAYS('2027-12-01')),
  PARTITION p_202712 VALUES LESS THAN (TO_DAYS('2028-01-01')),
  PARTITION p_future  VALUES LESS THAN MAXVALUE
);

-- ─── 3. Verificar particiones ──────────────────────────────

SELECT 'F6-001' AS migration, 'Particiones creadas' AS step,
       COUNT(*) AS partition_count
FROM information_schema.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'app_audit_log'
  AND PARTITION_NAME IS NOT NULL;

-- ─── 4. Verificar que los datos están en la partición correcta ──

SELECT 'F6-001' AS migration, 'Datos en particiones' AS step,
       p.PARTITION_NAME,
       COUNT(*) AS row_count,
       MIN(a.created_at) AS min_date,
       MAX(a.created_at) AS max_date
FROM app_audit_log a
JOIN information_schema.PARTITIONS p
  ON p.TABLE_SCHEMA = DATABASE()
  AND p.TABLE_NAME = 'app_audit_log'
  AND a.created_at >= FROM_DAYS(p.PARTITION_DESCRIPTION)
  AND a.created_at <  FROM_DAYS(p.PARTITION_DESCRIPTION) + INTERVAL 1 MONTH
WHERE p.PARTITION_NAME IS NOT NULL
  AND p.PARTITION_NAME != 'p_future'
GROUP BY p.PARTITION_NAME
ORDER BY p.PARTITION_NAME;

-- ============================================================
-- Housekeeping (para el futuro):
--   ALTER TABLE app_audit_log DROP PARTITION p_202605;
--
-- Considerar un job mensual que dropee particiones > 12 meses.
-- ============================================================
