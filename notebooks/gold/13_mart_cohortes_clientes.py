-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 13 · mart_cohortes_clientes — cohortes por mes de primera compra
-- MAGIC
-- MAGIC SCD1 snapshot mensual (DT-F3-6).
-- MAGIC Cada fila es: business_month × cliente, con métricas de comportamiento.
-- MAGIC Particionado por business_month. Patrón idempotente: DELETE + INSERT.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · Crear tabla si no existe

-- COMMAND ----------

CREATE TABLE IF NOT EXISTS motoshop.gold.mart_cohortes_clientes (
  business_month DATE,
  mes_cohorte DATE,
  nit_cliente STRING,
  nombre_cliente STRING,
  meses_desde_cohorte INT,
  compro_este_mes BOOLEAN,
  ticket_promedio DOUBLE,
  ingresos_totales DOUBLE,
  es_activo BOOLEAN
) USING DELTA PARTITIONED BY (business_month);

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · DELETE + INSERT (idempotente por business_month)

-- COMMAND ----------

DELETE FROM motoshop.gold.mart_cohortes_clientes
WHERE business_month >= DATE '2020-01-01' AND business_month <= CURRENT_DATE();

-- COMMAND ----------

INSERT INTO motoshop.gold.mart_cohortes_clientes
WITH primera_compra AS (
  SELECT
    nit_cliente,
    DATE_TRUNC('MONTH', MIN(business_date)) AS mes_cohorte
  FROM motoshop.silver.fact_ventas
  WHERE business_date >= DATE '2020-01-01'
    AND business_date <= CURRENT_DATE()
  GROUP BY nit_cliente
),
ventas_mensuales AS (
  SELECT
    DATE_TRUNC('MONTH', fv.business_date) AS business_month,
    fv.nit_cliente,
    fv.nombre_cliente,
    COUNT(DISTINCT fv.num_documento) AS facturas_mes,
    COUNT(fvd.cod_producto) AS items_mes,
    ROUND(AVG(fv.total_factura), 2) AS ticket_promedio,
    ROUND(SUM(fvd.valor_unitario * fvd.cantidad - COALESCE(fvd.descuento_valor, 0)), 2) AS ingresos_mes
  FROM motoshop.silver.fact_ventas fv
  INNER JOIN motoshop.silver.fact_ventas_detalle fvd
    ON fv.num_documento = fvd.num_documento
    AND fv.cod_clase = fvd.cod_clase
    AND fv.business_date = fvd.business_date
  WHERE fv.business_date >= DATE '2020-01-01'
    AND fv.business_date <= CURRENT_DATE()
  GROUP BY DATE_TRUNC('MONTH', fv.business_date), fv.nit_cliente, fv.nombre_cliente
)
SELECT
  vm.business_month,
  pc.mes_cohorte,
  vm.nit_cliente,
  vm.nombre_cliente,
  CAST(DATEDIFF(vm.business_month, pc.mes_cohorte) / 31 AS INT) AS meses_desde_cohorte,
  CASE WHEN vm.facturas_mes > 0 THEN TRUE ELSE FALSE END AS compro_este_mes,
  vm.ticket_promedio,
  vm.ingresos_mes AS ingresos_totales,
  CASE
    WHEN vm.facturas_mes >= 2 THEN TRUE
    ELSE FALSE
  END AS es_activo
FROM ventas_mensuales vm
LEFT JOIN primera_compra pc ON vm.nit_cliente = pc.nit_cliente
ORDER BY vm.business_month, vm.nit_cliente;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Validación

-- COMMAND ----------

SELECT
  COUNT(*) AS rows,
  MIN(business_month) AS min_month,
  MAX(business_month) AS max_month,
  COUNT(DISTINCT mes_cohorte) AS cohortes,
  COUNT(DISTINCT nit_cliente) AS clientes_unicos,
  COUNT(DISTINCT CONCAT(mes_cohorte, '_', nit_cliente)) AS pares_cohorte_cliente
FROM motoshop.gold.mart_cohortes_clientes;

-- COMMAND ----------

SELECT * FROM motoshop.gold.mart_cohortes_clientes LIMIT 10;
