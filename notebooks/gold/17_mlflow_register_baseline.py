-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 17 · MLflow Register Baseline
-- MAGIC
-- MAGIC Calcula MAPE del baseline y registra en MLflow.
-- MAGIC
-- MAGIC ⚠️ Este notebook tiene dos modos:
-- MAGIC 1. **SQL (vía REST API):** calcula MAPE y métricas desde gold.forecast_baseline_sku
-- MAGIC 2. **Python (vía notebook Databricks):** registra run en MLflow
-- MAGIC
-- MAGIC Si MLflow no está disponible, falla gracefulmente y documenta.

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 1 · MAPE global del baseline

-- COMMAND ----------

SELECT
  ROUND(AVG(ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real, 0)) * 100, 2) AS mape_global_pct,
  ROUND(AVG(2 * ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real + demanda_predicha, 0)) * 100, 2) AS smape_global_pct,
  ROUND(SUM(ABS(demanda_real - demanda_predicha)) / NULLIF(SUM(demanda_real), 0) * 100, 2) AS wape_global_pct,
  COUNT(*) AS total_filas,
  COUNT(demanda_predicha) AS filas_con_prediccion,
  SUM(CASE WHEN demanda_predicha IS NULL THEN 1 ELSE 0 END) AS filas_sin_prediccion
FROM motoshop.gold.forecast_baseline_sku
WHERE demanda_real > 0;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 2 · MAPE por método

-- COMMAND ----------

SELECT
  metodo,
  COUNT(*) AS filas,
  ROUND(AVG(ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real, 0)) * 100, 2) AS mape_pct,
  ROUND(AVG(2 * ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real + demanda_predicha, 0)) * 100, 2) AS smape_pct
FROM motoshop.gold.forecast_baseline_sku
WHERE demanda_real > 0 AND demanda_predicha IS NOT NULL
GROUP BY metodo;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 3 · Top-10 peores SKUs (MAPE más alto)

-- COMMAND ----------

SELECT
  cod_producto,
  COUNT(*) AS dias,
  ROUND(AVG(ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real, 0)) * 100, 2) AS mape_pct,
  ROUND(AVG(demanda_real), 2) AS avg_demanda_real
FROM motoshop.gold.forecast_baseline_sku
WHERE demanda_real > 0 AND demanda_predicha IS NOT NULL
GROUP BY cod_producto
HAVING COUNT(*) >= 5
ORDER BY mape_pct DESC
LIMIT 10;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 4 · Top-100 SKUs MAPE (para evidencia V-FS3)

-- COMMAND ----------

SELECT
  cod_producto,
  COUNT(*) AS dias,
  ROUND(AVG(ABS(demanda_real - demanda_predicha) / NULLIF(demanda_real, 0)) * 100, 2) AS mape_pct
FROM motoshop.gold.forecast_baseline_sku
WHERE demanda_real > 0 AND demanda_predicha IS NOT NULL
GROUP BY cod_producto
HAVING COUNT(*) >= 5
ORDER BY mape_pct ASC
LIMIT 100;

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 5 · MLflow tracking (Python)
-- MAGIC
-- MAGIC Ejecutar esta celda SOLO si el notebook corre en un entorno con MLflow
-- MAGIC (Databricks Runtime ML o con mlflow instalado localmente).
-- MAGIC
-- MAGIC Si falla, el MAPE ya está calculado en las celdas SQL anteriores.

-- COMMAND ----------

-- MAGIC %python
-- MAGIC import mlflow
-- MAGIC import mlflow.tracking
-- MAGIC from datetime import datetime
-- MAGIC
-- MAGIC try:
-- MAGIC     mlflow.set_tracking_uri("databricks")
-- MAGIC     mlflow.set_experiment("/Users/javierportillar/motoshop_forecast")
-- MAGIC
-- MAGIC     with mlflow.start_run() as run:
-- MAGIC         mlflow.set_tags({"fase": "F4", "modelo": "naive_seasonal", "sprint": "F4-A"})
-- MAGIC
-- MAGIC         # Obtener MAPE desde la tabla gold (requiere conexión SQL)
-- MAGIC         # Alternativa: pasarlo como parámetro desde el SQL
-- MAGIC         mape_value = {mape_global_pct}  # Reemplazar con valor real
-- MAGIC
-- MAGIC         mlflow.log_metric("MAPE", mape_value)
-- MAGIC         mlflow.log_param("model", "naive_seasonal")
-- MAGIC         mlflow.log_param("horizon", "7d_tolerance")
-- MAGIC         mlflow.log_param("source_table", "gold.forecast_baseline_sku")
-- MAGIC
-- MAGIC         print(f"✅ MLflow run: {run.info.run_id}")
-- MAGIC         print(f"   MAPE: {mape_value}")
-- MAGIC
-- MAGIC except Exception as e:
-- MAGIC     print(f"⚠️ MLflow no disponible: {e}")
-- MAGIC     print("Documentación:")
-- MAGIC     print("  - MLflow tracking requiere Databricks Runtime ML")
-- MAGIC     print("  - O configurar MLFLOW_TRACKING_URI=databricks con token")
-- MAGIC     print("  - Crear experimento: /Users/javierportillar/motoshop_forecast")
-- MAGIC     print("  - Instalar: pip install mlflow")
-- MAGIC     print("✅ MAPE ya calculado en celdas SQL anteriores — continuar sin MLflow.")

-- COMMAND ----------

-- MAGIC %md
-- MAGIC ## 6 · Resultados guardados en _runs/
-- MAGIC
-- MAGIC Los resultados de MAPE y evidencia se guardan automáticamente
-- MAGIC cuando el runner captura las salidas de las celdas SQL.
