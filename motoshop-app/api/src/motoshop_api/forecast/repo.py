"""Repositorio de forecast — mock (FakeForecastRepo) + real (RealForecastRepo vía Databricks SQL).

FakeForecastRepo se usa mientras Dev A no tenga gold.forecast_demanda_sku.
Devuelve datos mock realistas para MOTS1297 (top SKU: aceite 20W50).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Protocol

logger = logging.getLogger(__name__)

from motoshop_api.forecast.schemas import ForecastItem, ForecastMetrics, ForecastResponse


class ForecastRepoProtocol(Protocol):
    """Contrato que cumplen FakeForecastRepo y RealForecastRepo."""

    def get_forecast(self, sku: str, horizon: int) -> ForecastResponse | None: ...


# ── Fake (mock) ──────────────────────────────────────────────────────────

_FORECAST_SKUS: dict[str, tuple[str, list[float]]] = {
    "MOTS1297": ("ACEITE 20W50 MOTUL 1L", [45.0, 42.0, 38.0, 50.0, 48.0, 44.0, 41.0]),
    "MOTS0412": ("FILTRO ACEITE YAMAHA YBR125", [38.0, 36.0, 40.0, 42.0, 37.0, 35.0, 39.0]),
    "MOTS0834": ("PASTILLAS FRENO DELANTERAS", [28.0, 30.0, 26.0, 32.0, 29.0, 27.0, 31.0]),
}

_BASE_DATE = date.today()


def _make_fake_forecast(sku: str, horizon: int) -> ForecastResponse:
    name_vals = _FORECAST_SKUS.get(sku)
    if not name_vals:
        return None

    _, vals = name_vals
    items: list[ForecastItem] = []
    for i in range(min(horizon, len(vals))):
        d = _BASE_DATE + timedelta(days=i)
        qty = vals[i]
        items.append(
            ForecastItem(
                sku=sku,
                forecast_date=d,
                horizon=horizon,
                predicted_qty=qty,
                model_version="prophet-v1-mock",
                confidence_lower=round(qty * 0.8, 1),
                confidence_upper=round(qty * 1.2, 1),
            )
        )

    return ForecastResponse(
        sku=sku,
        forecast=items,
        metrics=ForecastMetrics(
            model_version="prophet-v1-mock",
            mape=12.5,
            smape=11.8,
            training_date=_BASE_DATE.isoformat(),
        ),
    )


class FakeForecastRepo:
    """Devuelve datos mock de forecast mientras no exista gold.forecast_demanda_sku."""

    KNOWN_SKUS = set(_FORECAST_SKUS.keys())

    def get_forecast(self, sku: str, horizon: int) -> ForecastResponse | None:
        return _make_fake_forecast(sku, horizon)


# ── Real (Databricks SQL Warehouse vía SDK) ──────────────────────────────

_REAL_FORECAST_SQL = """
SELECT
    sku,
    forecast_date,
    horizon,
    predicted_qty,
    model_version,
    confidence_lower,
    confidence_upper
FROM motoshop.gold.forecast_demanda_sku
WHERE sku = :sku
  AND horizon = :horizon
ORDER BY forecast_date ASC
"""

_REAL_METRICS_SQL = """
SELECT
    model_version,
    mape,
    smape,
    training_date
FROM motoshop.gold.forecast_model_metrics
WHERE sku = :sku
ORDER BY training_date DESC
LIMIT 1
"""


class RealForecastRepo:
    """Lee de gold.forecast_demanda_sku vía Databricks SQL Warehouse."""

    def __init__(self, workspace_client, warehouse_id: str) -> None:
        self._w = workspace_client
        self._wh_id = warehouse_id

    def get_forecast(self, sku: str, horizon: int) -> ForecastResponse | None:
        rows = self._query(_REAL_FORECAST_SQL, {"sku": sku, "horizon": horizon})
        if not rows:
            logger.info("No forecast data for sku=%s horizon=%d", sku, horizon)
            return None

        items = [
            ForecastItem(
                sku=str(r["sku"]),
                forecast_date=date.fromisoformat(str(r["forecast_date"])) if isinstance(r["forecast_date"], str) else r["forecast_date"],
                horizon=int(r["horizon"]),
                predicted_qty=float(r["predicted_qty"]),
                model_version=str(r["model_version"]),
                confidence_lower=float(r["confidence_lower"]) if r.get("confidence_lower") else None,
                confidence_upper=float(r["confidence_upper"]) if r.get("confidence_upper") else None,
            )
            for r in rows
        ]

        metrics_row = self._query(_REAL_METRICS_SQL, {"sku": sku})
        metrics = None
        if metrics_row:
            m = metrics_row[0]
            metrics = ForecastMetrics(
                model_version=str(m["model_version"]),
                mape=float(m["mape"]) if m.get("mape") else None,
                smape=float(m["smape"]) if m.get("smape") else None,
                training_date=str(m["training_date"]) if m.get("training_date") else None,
            )

        return ForecastResponse(sku=sku, forecast=items, metrics=metrics)

    def _query(self, sql: str, params: dict | None = None) -> list[dict]:
        from databricks.sdk.service.sql import StatementParameterListItem

        sp = []
        if params:
            for k, v in params.items():
                sp.append(StatementParameterListItem(name=k, value=v))

        result = self._w.statement_execution.execute_statement(
            statement=sql,
            warehouse_id=self._wh_id,
            parameters=sp,
            wait_timeout="50s",
        )
        if result.status.state.name != "SUCCEEDED":
            error_detail = result.status.error.message if hasattr(result.status, 'error') and result.status.error else 'unknown'
            logger.error("Databricks query failed: state=%s error=%s", result.status.state.name, error_detail)
            raise RuntimeError(f"Databricks query failed: {result.status.state.name} - {error_detail}")

        cols = [col.name for col in result.manifest.schema.columns]
        total_chunks = result.manifest.total_chunk_count if hasattr(result.manifest, 'total_chunk_count') else 1
        all_rows = []
        for i in range(total_chunks):
            chunk = self._w.statement_execution.get_statement_result_chunk_n(
                result.statement_id, i
            )
            if chunk.data_array:
                all_rows.extend([dict(zip(cols, row)) for row in chunk.data_array])
        return all_rows


# ── Factory ────────────────────────────────────────────────────────────────

def get_forecast_repo(workspace_client=None, warehouse_id=None) -> ForecastRepoProtocol:
    """Devuelve el repo adecuado según configuración.

    Si se pasa workspace_client + warehouse_id, usa RealForecastRepo.
    Si no, usa env: RealForecastRepo en prod/dev, FakeForecastRepo en test.
    """
    if workspace_client is not None and warehouse_id:
        return RealForecastRepo(workspace_client, warehouse_id)
    from motoshop_api.config import settings

    if settings.env != "test":
        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient(host=settings.databricks_host, token=settings.databricks_token)
        wh_id = settings.databricks_http_path.split("/")[-1] if settings.databricks_http_path else ""
        return RealForecastRepo(w, wh_id)
    return FakeForecastRepo()
