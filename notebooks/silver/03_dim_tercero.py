# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · dim_tercero — SCD Type 1 desde bronze.terceros
# MAGIC
# MAGIC PII: SHA2 del nombre para datasets compartidos (Habeas Data Col).

# COMMAND ----------

-- MAGIC %sql

CREATE OR REPLACE TABLE motoshop.silver.dim_tercero AS
SELECT
  TRIM(nitter)    AS nit_tercero,
  TRIM(tipnit)    AS tipo_nit,
  TRIM(digter)    AS digito_verificador,
  TRIM(perjur)    AS persona_juridica,
  TRIM(razsoc)    AS razon_social,
  TRIM(apeter)    AS apellido1,
  TRIM(apeter2)   AS apellido2,
  TRIM(nomter)    AS nombre1,
  TRIM(nomter2)   AS nombre2,
  TRIM(nomcom)    AS nombre_completo,
  SHA2(TRIM(CONCAT(COALESCE(TRIM(nomter), ''), ' ', COALESCE(TRIM(apeter), ''))), 256) AS nombre_hash,
  TRIM(dirter)    AS direccion,
  TRIM(telter)    AS telefono,
  TRIM(movter)    AS movil,
  TRIM(corele)    AS email,
  TRIM(codciu)    AS cod_ciudad,
  TRIM(cliter)    AS clase_cliente,
  TRIM(proter)    AS clase_proveedor,
  TRIM(empter)    AS clase_empleado,
  TRIM(venter)    AS clase_vendedor,
  CAST(fecnac AS DATE)  AS fecha_nacimiento,
  CAST(feccrea AS DATE) AS fecha_creacion,
  TRIM(obster)    AS observaciones,
  CURRENT_DATE()  AS snapshot_date
FROM motoshop.bronze.terceros
WHERE nitter IS NOT NULL;

# COMMAND ----------

-- MAGIC %sql

SELECT
  COUNT(*) AS total,
  COUNT(DISTINCT nit_tercero) AS distintos,
  COUNT(*) - COUNT(DISTINCT nit_tercero) AS duplicados
FROM motoshop.silver.dim_tercero;

# COMMAND ----------

-- MAGIC %sql

SELECT COUNT(*) AS dim_tercero_rows FROM motoshop.silver.dim_tercero;
