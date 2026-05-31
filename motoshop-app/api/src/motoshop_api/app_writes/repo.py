"""Repositorio de escritura para acciones sobre alertas.

Protocol + Real (MySQL InnoDB) + Fake (memoria para tests).
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

from sqlalchemy import select, func, insert, delete

from motoshop_api.app_writes.models import app_alert_actions, app_audit_log
from motoshop_api.app_writes.schemas import (
    AlertActionItem,
    AlertActionListResponse,
    AlertActionRequest,
    AlertActionResponse,
)


# ─── AlertActionsRepo Protocol ─────────────────────────────────


class AlertActionsRepoProtocol(Protocol):
    """Contrato que cumplen FakeAlertActionsRepo y RealAlertActionsRepo."""

    def create_action(
        self,
        alert_id: str,
        sku: str,
        user_id: str,
        request_id: str,
        body: AlertActionRequest,
        idempotency_key: str,
    ) -> AlertActionResponse: ...

    def get_action_by_idempotency_key(
        self, idempotency_key: str
    ) -> AlertActionResponse | None: ...

    def list_user_actions(
        self,
        user_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AlertActionListResponse: ...


# ─── Fake (memoria para tests) ────────────────────────────────


class FakeAlertActionsRepo:
    """Implementación en memoria para tests."""

    def __init__(self) -> None:
        self._actions: list[dict] = []
        self._next_id = 1

    def create_action(
        self,
        alert_id: str,
        sku: str,
        user_id: str,
        request_id: str,
        body: AlertActionRequest,
        idempotency_key: str,
    ) -> AlertActionResponse:
        existing = self.get_action_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        now = datetime.now(timezone.utc)
        record = {
            "id": self._next_id,
            "alert_id": alert_id,
            "sku": sku,
            "user_id": user_id,
            "action_type": body.action_type,
            "quantity": float(body.quantity) if body.quantity else None,
            "supplier": body.supplier,
            "reason": body.reason,
            "postponed_to": body.postponed_to,
            "notes": body.notes,
            "idempotency_key": idempotency_key,
            "created_at": now,
            "request_id": request_id,
        }
        self._next_id += 1
        self._actions.append(record)

        return AlertActionResponse(
            id=record["id"],
            alert_id=record["alert_id"],
            sku=record["sku"],
            action_type=record["action_type"],
            user_id=record["user_id"],
            created_at=record["created_at"],
        )

    def get_action_by_idempotency_key(
        self, idempotency_key: str
    ) -> AlertActionResponse | None:
        for a in self._actions:
            if a["idempotency_key"] == idempotency_key:
                return AlertActionResponse(
                    id=a["id"],
                    alert_id=a["alert_id"],
                    sku=a["sku"],
                    action_type=a["action_type"],
                    user_id=a["user_id"],
                    created_at=a["created_at"],
                )
        return None

    def list_user_actions(
        self,
        user_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AlertActionListResponse:
        filtered = [a for a in self._actions if a["user_id"] == user_id]
        if date_from:
            filtered = [a for a in filtered if a["created_at"].date() >= date_from]
        if date_to:
            filtered = [a for a in filtered if a["created_at"].date() <= date_to]

        filtered.sort(key=lambda a: a["created_at"], reverse=True)
        total = len(filtered)
        page = filtered[offset : offset + limit]

        items = [
            AlertActionItem(
                id=a["id"],
                alert_id=a["alert_id"],
                sku=a["sku"],
                action_type=a["action_type"],
                quantity=a.get("quantity"),
                supplier=a.get("supplier"),
                reason=a.get("reason"),
                postponed_to=a.get("postponed_to"),
                notes=a.get("notes"),
                created_at=a["created_at"],
            )
            for a in page
        ]

        return AlertActionListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    def _clear(self) -> None:
        self._actions.clear()
        self._next_id = 1


_FAKE_ALERT_ACTIONS_REPO: FakeAlertActionsRepo | None = None
_FAKE_AUDIT_REPO: FakeAuditRepo | None = None


def _get_shared_fake_alert_actions_repo() -> FakeAlertActionsRepo:
    """Singleton compartido para dependency_overrides en tests."""
    global _FAKE_ALERT_ACTIONS_REPO
    if _FAKE_ALERT_ACTIONS_REPO is None:
        _FAKE_ALERT_ACTIONS_REPO = FakeAlertActionsRepo()
    return _FAKE_ALERT_ACTIONS_REPO


def _get_shared_fake_audit_repo() -> FakeAuditRepo:
    """Singleton compartido para dependency_overrides en tests."""
    global _FAKE_AUDIT_REPO
    if _FAKE_AUDIT_REPO is None:
        _FAKE_AUDIT_REPO = FakeAuditRepo()
    return _FAKE_AUDIT_REPO


def _reset_fake_repos() -> None:
    """Resetea los singletons de test."""
    global _FAKE_ALERT_ACTIONS_REPO, _FAKE_AUDIT_REPO
    if _FAKE_ALERT_ACTIONS_REPO is not None:
        _FAKE_ALERT_ACTIONS_REPO._clear()
    if _FAKE_AUDIT_REPO is not None:
        _FAKE_AUDIT_REPO._clear()
    _FAKE_ALERT_ACTIONS_REPO = None
    _FAKE_AUDIT_REPO = None


# ─── Real (MySQL InnoDB) ──────────────────────────────────────


class RealAlertActionsRepo:
    """Implementación real contra MySQL con usuario app_writer."""

    def __init__(self) -> None:
        from motoshop_api.db.engine import get_writer_engine

        self._engine = get_writer_engine()

    def create_action(
        self,
        alert_id: str,
        sku: str,
        user_id: str,
        request_id: str,
        body: AlertActionRequest,
        idempotency_key: str,
    ) -> AlertActionResponse:
        existing = self.get_action_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        from sqlalchemy import text

        with self._engine.connect() as conn:
            result = conn.execute(
                insert(app_alert_actions).values(
                    alert_id=alert_id,
                    sku=sku,
                    user_id=user_id,
                    action_type=body.action_type,
                    quantity=body.quantity,
                    supplier=body.supplier,
                    reason=body.reason,
                    postponed_to=body.postponed_to,
                    notes=body.notes,
                    idempotency_key=idempotency_key,
                    request_id=request_id,
                )
            )
            new_id = result.inserted_primary_key[0]
            # Leer created_at real de la DB (TIMESTAMP, sin microsegundos)
            created_at_row = conn.execute(
                text("SELECT created_at FROM app_alert_actions WHERE id = :id"),
                {"id": new_id},
            ).fetchone()
            created_at = created_at_row[0]

        logger.info(
            "create_action user_id=%s alert_id=%s sku=%s action_type=%s id=%s",
            user_id, alert_id, sku, body.action_type, new_id,
        )

        return AlertActionResponse(
            id=new_id,
            alert_id=alert_id,
            sku=sku,
            action_type=body.action_type,
            user_id=user_id,
            created_at=created_at,
        )

    def get_action_by_idempotency_key(
        self, idempotency_key: str
    ) -> AlertActionResponse | None:
        from sqlalchemy import text

        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, alert_id, sku, user_id, action_type, created_at "
                    "FROM app_alert_actions "
                    "WHERE idempotency_key = :key"
                ),
                {"key": idempotency_key},
            ).fetchone()

        if row is None:
            return None

        return AlertActionResponse(
            id=row[0],
            alert_id=row[1],
            sku=row[2],
            user_id=row[3],
            action_type=row[4],
            created_at=row[5],
        )

    def list_user_actions(
        self,
        user_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AlertActionListResponse:
        from sqlalchemy import text

        where_clauses = ["user_id = :user_id"]
        params: dict = {"user_id": user_id, "limit": limit, "offset": offset}

        if date_from:
            where_clauses.append("DATE(created_at) >= :date_from")
            params["date_from"] = date_from
        if date_to:
            where_clauses.append("DATE(created_at) <= :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses)

        logger.debug("list_user_actions SQL: COUNT query where=%s params=%s", where_sql, params)

        with self._engine.connect() as conn:
            # Total count
            count_row = conn.execute(
                text(f"SELECT COUNT(*) FROM app_alert_actions WHERE {where_sql}"),
                params,
            ).fetchone()
            total = count_row[0]

            # Items
            rows = conn.execute(
                text(
                    f"SELECT id, alert_id, sku, action_type, quantity, "
                    f"supplier, reason, postponed_to, notes, created_at "
                    f"FROM app_alert_actions WHERE {where_sql} "
                    f"ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            ).fetchall()

        logger.info(
            "list_user_actions user_id=%s date_from=%s date_to=%s total=%d limit=%d offset=%d",
            user_id, date_from, date_to, total, limit, offset,
        )

        items = [
            AlertActionItem(
                id=r[0],
                alert_id=r[1],
                sku=r[2],
                action_type=r[3],
                quantity=r[4],
                supplier=r[5],
                reason=r[6],
                postponed_to=r[7],
                notes=r[8],
                created_at=r[9],
            )
            for r in rows
        ]

        return AlertActionListResponse(
            items=items, total=total, limit=limit, offset=offset
        )


# ─── AuditLog Repo ────────────────────────────────────────────


class AuditRepo:
    """Registra eventos de auditoria en app_audit_log."""

    def __init__(self) -> None:
        from motoshop_api.db.engine import get_writer_engine

        self._engine = get_writer_engine()

    def log(
        self,
        user_id: str,
        user_role: str,
        action: str,
        target_type: str,
        target_id: str,
        request_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        payload: dict | None = None,
        status: str = "success",
        error_msg: str | None = None,
    ) -> None:
        with self._engine.connect() as conn:
            conn.execute(
                insert(app_audit_log).values(
                    user_id=user_id,
                    user_role=user_role,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    request_id=request_id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    payload=json.dumps(payload) if payload else None,
                    status=status,
                    error_msg=error_msg,
                )
            )


class FakeAuditRepo:
    """Audit en memoria para tests — nunca toca la DB."""

    def __init__(self) -> None:
        self.logs: list[dict] = []

    def log(
        self,
        user_id: str,
        user_role: str,
        action: str,
        target_type: str,
        target_id: str,
        request_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        payload: dict | None = None,
        status: str = "success",
        error_msg: str | None = None,
    ) -> None:
        self.logs.append(
            {
                "user_id": user_id,
                "user_role": user_role,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "request_id": request_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "payload": payload,
                "status": status,
                "error_msg": error_msg,
            }
        )

    def _clear(self) -> None:
        self.logs.clear()


# ─── Factory ─────────────────────────────────────────────────


def get_alert_actions_repo() -> AlertActionsRepoProtocol:
    """Inyección: RealAlertActionsRepo en prod/dev, Fake en tests."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return RealAlertActionsRepo()
    return FakeAlertActionsRepo()


def get_audit_repo() -> AuditRepo | FakeAuditRepo:
    """Real en prod/dev, Fake en tests."""
    from motoshop_api.config import settings

    if settings.env != "test":
        return AuditRepo()
    return FakeAuditRepo()
