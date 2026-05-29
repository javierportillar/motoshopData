"""Repositorio de alertas de quiebre — mock + real vía Databricks SQL.

FakeAlertsRepo se usa mientras no exista gold.alertas_quiebre.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Protocol

logger = logging.getLogger(__name__)

from motoshop_api.alerts.schemas import AlertItem, AlertsResponse


Urgency = Literal["alta", "media", "baja"]


class AlertsRepoProtocol(Protocol):
    """Contrato que cumplen FakeAlertsRepo y RealAlertsRepo."""

    def get_stockout_alerts(self, urgency: str | None = None) -> AlertsResponse: ...


# ── Fake (mock) ──────────────────────────────────────────────────────────

_FAKE_ALERTS: list[AlertItem] = [
    AlertItem(sku="MOTS1297", nom_producto="ACEITE 20W50 MOTUL 1L", stock_actual=12.0, demanda_predicha=45.0, dias_hasta_quiebre=3, urgencia="alta"),
    AlertItem(sku="MOTS0412", nom_producto="FILTRO ACEITE YAMAHA YBR125", stock_actual=8.0, demanda_predicha=38.0, dias_hasta_quiebre=4, urgencia="alta"),
    AlertItem(sku="MOTS0834", nom_producto="PASTILLAS FRENO DELANTERAS", stock_actual=15.0, demanda_predicha=28.0, dias_hasta_quiebre=6, urgencia="media"),
    AlertItem(sku="MOTS1723", nom_producto="CUBIERTA PIRELLI 130/70-17", stock_actual=3.0, demanda_predicha=10.0, dias_hasta_quiebre=7, urgencia="media"),
    AlertItem(sku="MOTS0945", nom_producto="BATERIA YUASA YB14L-A2", stock_actual=5.0, demanda_predicha=12.0, dias_hasta_quiebre=10, urgencia="baja"),
    AlertItem(sku="MOTS2618", nom_producto="GUAYA ACELERADOR UNIVERSAL", stock_actual=22.0, demanda_predicha=34.0, dias_hasta_quiebre=14, urgencia="baja"),
]


class FakeAlertsRepo:
    """Devuelve alertas mock mientras no exista gold.alertas_quiebre."""

    def get_stockout_alerts(self, urgency: str | None = None) -> AlertsResponse:
        alerts = _FAKE_ALERTS
        if urgency:
            alerts = [a for a in alerts if a.urgencia == urgency]
        return AlertsResponse(
            alerts=alerts,
            total=len(alerts),
            timestamp=datetime.now(),
        )


# ── Real (Databricks SQL Warehouse vía SDK) ──────────────────────────────

_REAL_ALERTS_SQL = """
SELECT
    sku,
    nom_producto,
    stock_actual,
    demanda_predicha,
    dias_hasta_quiebre,
    urgencia
FROM motoshop.gold.alertas_quiebre
{where_clause}
ORDER BY
    CASE urgencia
        WHEN 'alta' THEN 1
        WHEN 'media' THEN 2
        WHEN 'baja' THEN 3
    END,
    dias_hasta_quiebre ASC
"""


class RealAlertsRepo:
    """Lee de gold.alertas_quiebre vía Databricks SQL Warehouse."""

    def __init__(self, workspace_client, warehouse_id: str) -> None:
        self._w = workspace_client
        self._wh_id = warehouse_id

    def get_stockout_alerts(self, urgency: str | None = None) -> AlertsResponse:
        where = ""
        params = None
        if urgency:
            where = "WHERE urgencia = :urgency"
            params = {"urgency": urgency}

        sql = _REAL_ALERTS_SQL.format(where_clause=where)
        rows = self._query(sql, params)

        alerts = [
            AlertItem(
                sku=str(r["sku"]),
                nom_producto=str(r["nom_producto"]),
                stock_actual=float(r["stock_actual"]),
                demanda_predicha=float(r["demanda_predicha"]),
                dias_hasta_quiebre=int(r["dias_hasta_quiebre"]),
                urgencia=str(r["urgencia"]),
            )
            for r in rows
        ]
        return AlertsResponse(alerts=alerts, total=len(alerts), timestamp=datetime.now())

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

def get_alerts_repo(workspace_client=None, warehouse_id=None) -> AlertsRepoProtocol:
    """Devuelve el repo adecuado según configuración."""
    if workspace_client is not None and warehouse_id:
        return RealAlertsRepo(workspace_client, warehouse_id)
    return FakeAlertsRepo()
