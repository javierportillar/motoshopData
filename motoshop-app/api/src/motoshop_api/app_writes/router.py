"""Router de escritura: gestionar alertas y listar acciones del usuario."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from motoshop_api.app_writes.repo import (
    AlertActionsRepoProtocol,
    AuditRepo,
    FakeAuditRepo,
    get_alert_actions_repo,
    get_audit_repo,
)
from motoshop_api.app_writes.schemas import (
    AlertActionListResponse,
    AlertActionRequest,
    AlertActionResponse,
)
from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User

router = APIRouter(prefix="/alerts", tags=["alerts-actions"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_idempotency_key(key: str) -> str:
    """Valida que sea un UUID v4."""
    if not UUID_V4_RE.match(key):
        raise HTTPException(
            status_code=HTTP_422,
            detail="Idempotency-Key debe ser un UUID v4 válido",
        )
    return key


@router.post("/{alert_id}/action")
def create_alert_action(
    alert_id: str,
    body: AlertActionRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    user: User = Depends(require_role("admin", "gerente")),
    repo: AlertActionsRepoProtocol = Depends(get_alert_actions_repo),
    audit: AuditRepo = Depends(get_audit_repo),
) -> AlertActionResponse:
    """Registrar una acción sobre una alerta de quiebre.

    - **ordered** (requiere quantity, supplier opcional)
    - **dismissed** (requiere reason)
    - **postponed** (requiere postponed_to)

    Idempotent: si se reenvía el mismo `Idempotency-Key`, devuelve
    el registro original con HTTP 200 en vez de 201.
    """
    _validate_idempotency_key(idempotency_key)

    req_id = x_request_id or str(uuid.uuid4())
    sku = alert_id  # por ahora el alert_id ES el SKU; en F6+ se mapea

    # Verificar replay (idempotency)
    existing = repo.get_action_by_idempotency_key(idempotency_key)
    if existing is not None:
        _log_audit(audit, user, "replay", alert_id, req_id, request, body)
        return Response(content=existing.model_dump_json(), media_type="application/json", status_code=200)

    try:
        result = repo.create_action(
            alert_id=alert_id,
            sku=sku,
            user_id=user.username,
            request_id=req_id,
            body=body,
            idempotency_key=idempotency_key,
        )
    except Exception as e:
        _log_audit(
            audit, user, "create_action", alert_id, req_id, request, body,
            status="failure", error_msg=str(e)[:200],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar acción: {str(e)[:200]}",
        )

    _log_audit(audit, user, "create_action", alert_id, req_id, request, body)

    return Response(content=result.model_dump_json(), media_type="application/json", status_code=201)


@router.get("/actions/me", response_model=AlertActionListResponse)
def list_my_actions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    repo: AlertActionsRepoProtocol = Depends(get_alert_actions_repo),
) -> AlertActionListResponse:
    """Listar acciones del usuario autenticado.

    Filtros opcionales por rango de fechas.
    Paginación con limit/offset.
    """
    return repo.list_user_actions(
        user_id=user.username,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


def _log_audit(
    audit: AuditRepo | FakeAuditRepo,
    user: User,
    action: str,
    alert_id: str,
    request_id: str,
    request: Request,
    body: AlertActionRequest | None = None,
    status: str = "success",
    error_msg: str | None = None,
) -> None:
    """Registra en app_audit_log."""
    try:
        audit.log(
            user_id=user.username,
            user_role=user.role,
            action=action,
            target_type="alert",
            target_id=alert_id,
            request_id=request_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            payload=body.model_dump() if body else None,
            status=status,
            error_msg=error_msg,
        )
    except Exception:
        # El audit log nunca debe romper la request principal
        import structlog

        logger = structlog.get_logger(__name__)
        logger.exception("audit_log_failed", alert_id=alert_id, action=action)
