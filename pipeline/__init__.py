"""Pipeline V1.5 · Port de notebooks Databricks SQL a Python + DuckDB.

Orquestador: run_all.py ejecuta bronze→silver→gold en orden y produce
out/motoshop_gold.duckdb.

No requiere PySpark ni Databricks. Lee directamente de MySQL bronze
(a traves de exportados JSON como seed interino) y escribe a DuckDB.
"""
