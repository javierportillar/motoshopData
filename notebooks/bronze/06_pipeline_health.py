# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Pipeline Health
# MAGIC Mide lag desde el último manifest subido al UC Volume y emite veredicto.

# COMMAND ----------
import json
from datetime import datetime, timezone

VOLUME = "/Volumes/motoshop/bronze/_landing/_manifests"

manifests = dbutils.fs.ls(VOLUME)
latest = max(manifests, key=lambda f: f.modificationTime)
latest_ts = datetime.fromtimestamp(latest.modificationTime / 1000, tz=timezone.utc)
lag_seconds = (datetime.now(tz=timezone.utc) - latest_ts).total_seconds()

print(f"Último manifest: {latest.name} @ {latest_ts.isoformat()}")
print(f"Lag actual: {lag_seconds/3600:.2f} horas")

if lag_seconds < 2 * 3600:
    status = "OK"
elif lag_seconds < 6 * 3600:
    status = "WARN"
elif lag_seconds < 24 * 3600:
    status = "STALE"
else:
    status = "CRITICAL"

print(f"\nStatus: {status}")
