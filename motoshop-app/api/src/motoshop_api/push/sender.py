"""Push sender — envía notificaciones push vía pywebpush para alertas de quiebre.

Solo envía para urgencia=alta. Lee suscripciones de silver.app_push_subscriptions.
Requiere VAPID_KEY y PRIVATE_VAPID_KEY en .env.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class SubscriptionStoreProtocol(Protocol):
    """Obtiene suscripciones push activas."""

    def get_active_subscriptions(self) -> list[dict]: ...
    def remove_subscription(self, endpoint: str) -> None: ...


# ── Push sender ───────────────────────────────────────────────────────────

def send_push_alert(
    alert_sku: str,
    alert_producto: str,
    dias_hasta_quiebre: int,
    urgencia: str,
    store: SubscriptionStoreProtocol,
    vapid_private_key: str,
    vapid_public_key: str,
) -> int:
    """Envía notificación push a todas las suscripciones activas.

    Solo envía si urgencia == 'alta'.
    Retorna cantidad de pushes enviados exitosamente.
    """
    if urgencia != "alta":
        logger.info("Skipping push for urgencia=%s (only 'alta' is pushed)", urgencia)
        return 0

    try:
        from pywebpush import WebPusher
    except ImportError:
        logger.error("pywebpush not installed. Run: pip install pywebpush")
        return 0

    payload = json.dumps({
        "title": "⚠️ Alerta de quiebre",
        "body": f"{alert_producto} — {dias_hasta_quiebre} días de stock",
        "tag": f"stockout:{alert_sku}",
        "url": f"/alerts",
        "icon": "/icons/alert-icon-192.png",
        "badge": "/icons/alert-badge.png",
    })

    subs = store.get_active_subscriptions()
    sent = 0
    for sub in subs:
        try:
            pusher = WebPusher({
                "endpoint": sub["endpoint"],
                "keys": {
                    "p256dh": sub["p256dh"],
                    "auth": sub["auth"],
                },
            })
            pusher.send(
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": "mailto:admin@motoshop.app"},
                ttl=86400,
            )
            sent += 1
        except Exception as e:
            # 410 Gone = subscription expirada, la limpiamos
            if hasattr(e, "response") and e.response.status_code == 410:
                logger.info("Removing expired subscription: %s", sub["endpoint"][:50])
                store.remove_subscription(sub["endpoint"])
            else:
                logger.warning("Push send failed for %s: %s", sub["endpoint"][:50], e)

    logger.info("Push sent: %d/%d success for alert %s", sent, len(subs), alert_sku)
    return sent


# ── Subscription store (Databricks) ───────────────────────────────────────

class DatabricksSubscriptionStore:
    """Lee suscripciones desde silver.app_push_subscriptions vía Databricks SQL."""

    def __init__(self, workspace_client, warehouse_id: str) -> None:
        self._w = workspace_client
        self._wh_id = warehouse_id

    def get_active_subscriptions(self) -> list[dict]:
        return self._query("""
            SELECT endpoint, p256dh, auth
            FROM motoshop.silver.app_push_subscriptions
            WHERE active = TRUE
        """)

    def remove_subscription(self, endpoint: str) -> None:
        self._query(
            "UPDATE motoshop.silver.app_push_subscriptions SET active = FALSE WHERE endpoint = :endpoint",
            {"endpoint": endpoint},
        )

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
            wait_timeout="30s",
        )
        if result.status.state.name != "SUCCEEDED":
            error_detail = result.status.error.message if hasattr(result.status, 'error') and result.status.error else 'unknown'
            logger.error("Databricks query failed: state=%s error=%s", result.status.state.name, error_detail)
            raise RuntimeError(f"Databricks query failed: {result.status.state.name} - {error_detail}")

        if not result.manifest:
            return []

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
