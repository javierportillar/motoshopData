"""Tenant-authenticated read routes for persistent purchase assessments."""

from __future__ import annotations

from datetime import UTC, date, datetime
from math import ceil
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.purchase_assessments.repository import (
    PurchaseAssessmentRepository,
    PurchaseAssessmentRepositoryError,
    get_purchase_assessment_repository,
)
from motoshop_api.purchase_assessments.schemas import (
    PurchaseAssessmentListResponse,
    PurchaseAssessmentResponse,
)

router = APIRouter(prefix="/purchase-assessments", tags=["purchase-assessments"])
limiter = Limiter(key_func=get_remote_address)
_BACKFILL_START = date(2026, 9, 1)


def _storage_error() -> HTTPException:
    return HTTPException(status_code=503, detail="Servicio de evaluaciones de compra no disponible")


@router.get("/invoice", response_model=PurchaseAssessmentResponse)
def get_invoice_assessment(
    request: Request,
    business_date: date,
    cod_clase: str = Query(min_length=1, max_length=40),
    num_documento: str = Query(min_length=1, max_length=120),
    nit_proveedor: str | None = Query(default=None, max_length=80),
    tenant_id: str = Depends(get_tenant),
    repository: PurchaseAssessmentRepository = Depends(get_purchase_assessment_repository),
) -> PurchaseAssessmentResponse:
    """Get the most recent assessment for the complete purchase invoice identity."""
    if business_date < _BACKFILL_START:
        raise HTTPException(status_code=422, detail="La fecha debe ser desde 2026-09-01")
    try:
        row = repository.get_invoice(
            tenant_id,
            business_date.isoformat(),
            cod_clase,
            num_documento,
            nit_proveedor,
        )
    except PurchaseAssessmentRepositoryError as exc:
        raise _storage_error() from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluación de compra no encontrada")
    return PurchaseAssessmentResponse.model_validate(row)


@router.post(
    "/{assessment_id}/retry",
    response_model=PurchaseAssessmentResponse,
    status_code=202,
)
@limiter.limit("5/minute")
def retry_fallback_assessment(
    request: Request,
    assessment_id: UUID,
    tenant_id: str = Depends(get_tenant),
    repository: PurchaseAssessmentRepository = Depends(get_purchase_assessment_repository),
) -> PurchaseAssessmentResponse:
    """Requeue only this tenant's deterministic fallback, preserving its evidence."""
    try:
        row = repository.get_assessment_by_id(tenant_id, str(assessment_id))
    except PurchaseAssessmentRepositoryError as exc:
        raise _storage_error() from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Evaluación de compra no encontrada")
    if row.get("status") in {"pending", "processing"}:
        return PurchaseAssessmentResponse.model_validate(row)
    if row.get("status") != "fallback" or row.get("generation_mode") != "deterministic_fallback":
        raise HTTPException(
            status_code=409,
            detail="Solo se puede reintentar una evaluación en respaldo determinístico",
        )

    retry_at = row.get("next_retry_at")
    if retry_at:
        parsed_retry_at = retry_at if isinstance(retry_at, datetime) else datetime.fromisoformat(
            str(retry_at).replace("Z", "+00:00")
        )
        if parsed_retry_at.tzinfo is None:
            parsed_retry_at = parsed_retry_at.replace(tzinfo=UTC)
        seconds_remaining = (parsed_retry_at - datetime.now(UTC)).total_seconds()
        if seconds_remaining > 0:
            raise HTTPException(
                status_code=429,
                detail="Esperá el intervalo de seguridad antes de reintentar esta evaluación",
                headers={"Retry-After": str(max(1, ceil(seconds_remaining)))},
            )

    try:
        queued = repository.queue_fallback_retry(tenant_id, str(assessment_id))
        if queued is not None:
            return PurchaseAssessmentResponse.model_validate(queued)
        current = repository.get_assessment_by_id(tenant_id, str(assessment_id))
    except PurchaseAssessmentRepositoryError as exc:
        raise _storage_error() from exc
    if current is None:
        raise HTTPException(status_code=404, detail="Evaluación de compra no encontrada")
    if current.get("status") in {"pending", "processing"}:
        return PurchaseAssessmentResponse.model_validate(current)
    raise HTTPException(
        status_code=409,
        detail="La evaluación cambió de estado; actualizá el detalle antes de reintentar",
    )


@router.get("", response_model=PurchaseAssessmentListResponse)
def list_purchase_assessments(
    request: Request,
    date_from: date = Query(default=_BACKFILL_START),
    date_to: date | None = Query(default=None),
    nit_proveedor: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=100),
    tenant_id: str = Depends(get_tenant),
    repository: PurchaseAssessmentRepository = Depends(get_purchase_assessment_repository),
) -> PurchaseAssessmentListResponse:
    """List a bounded, tenant/provider-scoped date range of invoice assessments."""
    effective_to = date_to or date.today()
    if date_from < _BACKFILL_START or date_from > effective_to:
        raise HTTPException(status_code=422, detail="Rango de fechas de compra inválido")
    if (effective_to - date_from).days > 366:
        raise HTTPException(status_code=422, detail="El rango máximo es de 366 días")
    try:
        rows = repository.list_assessments(
            tenant_id,
            date_from.isoformat(),
            effective_to.isoformat(),
            nit_proveedor,
            limit,
        )
    except PurchaseAssessmentRepositoryError as exc:
        raise _storage_error() from exc
    return PurchaseAssessmentListResponse(
        items=[PurchaseAssessmentResponse.model_validate(row) for row in rows],
        date_from=date_from,
        date_to=effective_to,
        limit=limit,
    )
