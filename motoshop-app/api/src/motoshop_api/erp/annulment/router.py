"""Router `/api/erp/documents/{codclas}/{numfven}/annulment` (task 5.5).

Guard order: route matrix (mounted dependency) → tenant enablement (WF-3) →
annulment role (``require_erp_annul``) → the legacy guard chain inside the
repo (Veri_Anul → Hay_Cie_Eli → Valid_EdiDocele → role → reason).
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status

from motoshop_api.app_writes.repo import AuditRepo, FakeAuditRepo, get_audit_repo
from motoshop_api.auth.users import User
from motoshop_api.erp.annulment.repo import (
    AlreadyAnnulledError,
    AnnulmentForbiddenError,
    DocumentNotFoundError,
    ElectronicDocumentError,
    FakeAnnulmentRepo,
    RealAnnulmentRepo,
    get_annulment_repo,
)
from motoshop_api.erp.annulment.schemas import AnnulmentRequest
from motoshop_api.erp.engine import ErpSaveFailed
from motoshop_api.erp.guards import (
    PeriodLockedError,
    require_erp_annul,
    require_erp_tenant,
)
from motoshop_api.erp.masters.validators import LegacyValidationError
from motoshop_api.tenants import Tenant

logger = structlog.get_logger("motoshop.erp.annulment")

router = APIRouter(prefix="/erp", tags=["erp-anulaciones"])

HTTP_422 = status.HTTP_422_UNPROCESSABLE_CONTENT
HTTP_409 = status.HTTP_409_CONFLICT

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_idempotency_key(key: str) -> str:
    if not UUID_V4_RE.match(key):
        raise HTTPException(
            status_code=HTTP_422,
            detail="Idempotency-Key debe ser un UUID v4 válido",
        )
    return key


def _save_or_http_error(save):
    """Map the repo exceptions to the frozen HTTP contracts."""
    try:
        return save()
    except LegacyValidationError as exc:
        raise HTTPException(status_code=HTTP_422, detail=exc.detail()) from exc
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail()
        ) from exc
    except AlreadyAnnulledError as exc:
        raise HTTPException(status_code=HTTP_409, detail=exc.detail()) from exc
    except ElectronicDocumentError as exc:
        raise HTTPException(status_code=HTTP_409, detail=exc.detail()) from exc
    except PeriodLockedError as exc:
        raise HTTPException(status_code=HTTP_409, detail=str(exc)) from exc
    except AnnulmentForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=exc.detail()
        ) from exc
    except ErpSaveFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": str(exc),
                "code": "erp_save_failed",
                "docnum": exc.docnum,
                "retryable": exc.retryable,
            },
        ) from exc


@router.post("/documents/{codclas}/{numfven}/annulment", status_code=200)
def annul_document(
    codclas: str,
    numfven: int,
    body: AnnulmentRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
    tenant: Tenant = Depends(require_erp_tenant),
    user: User = Depends(require_erp_annul),
    repo: FakeAnnulmentRepo | RealAnnulmentRepo = Depends(get_annulment_repo),
    audit: AuditRepo | FakeAuditRepo = Depends(get_audit_repo),
) -> dict:
    """Annul a document with the FULL legacy reversal (AN-*)."""
    _validate_idempotency_key(idempotency_key)
    request_id = x_request_id or str(uuid.uuid4())
    response = _save_or_http_error(
        lambda: repo.annul(
            body,
            codclas=codclas,
            numfven=numfven,
            tenant=tenant.id,
            empresa=tenant.erp.empresa,
            actor=user.username,
            actor_role=user.role,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
    )
    try:
        audit.log(
            user_id=user.username,
            user_role=user.role,
            action="annul",
            target_type="documento",
            target_id=f"{codclas}/{numfven}",
            request_id=request_id,
            payload={"before": None, "after": response},
        )
    except Exception:  # pragma: no cover - audit must never break the annulment
        logger.warning("erp.annulment.audit_failed", request_id=request_id)
    return response
