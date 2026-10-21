"""FastAPI Router for DIAN Electronic Invoicing under /api/erp/dian."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User
from motoshop_api.erp.dian.models import (
    DianDocOut,
    DianQueueListOut,
    DianRetryIn,
    DianStatusEnum,
)
from motoshop_api.erp.dian.queue import DianQueue, get_dian_queue
from motoshop_api.erp.guards import ERP_ERP_MANAGEMENT_ROLES
from motoshop_api.erp.repo import ERPRepository, get_erp_repo

router = APIRouter(tags=["erp-dian"])


@router.get("/status", response_model=DianQueueListOut)
async def get_dian_status_list(
    status_filter: Annotated[DianStatusEnum | None, Query(alias="status")] = None,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    queue: DianQueue = Depends(get_dian_queue),
) -> DianQueueListOut:
    """Returns list of electronic documents in DIAN queue with state metrics for tenant."""
    docs = queue.list_dian_documents(tenant_id=tenant_id, status=status_filter)
    all_docs = queue.list_dian_documents(tenant_id=tenant_id)
    total = len(all_docs)
    accepted = sum(1 for d in all_docs if d.status == DianStatusEnum.ACCEPTED)
    pending = sum(1 for d in all_docs if d.status == DianStatusEnum.PENDING)
    failed = sum(1 for d in all_docs if d.status == DianStatusEnum.FAILED)
    rejected = sum(1 for d in all_docs if d.status == DianStatusEnum.REJECTED)

    return DianQueueListOut(
        documents=docs,
        total=total,
        accepted=accepted,
        pending=pending,
        failed=failed,
        rejected=rejected,
    )


@router.get("/document/{sale_id}", response_model=DianDocOut)
async def get_dian_document(
    sale_id: str,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    queue: DianQueue = Depends(get_dian_queue),
) -> DianDocOut:
    """Returns CUFE, QR code URL, and transmission status for a specific sale."""
    doc = queue.get_dian_status_for_sale(sale_id=sale_id, tenant_id=tenant_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DIAN document for sale '{sale_id}' not found",
        )
    return doc


@router.post("/retry/{sale_id}", response_model=DianDocOut)
async def retry_dian_transmission(
    sale_id: str,
    payload: DianRetryIn | None = None,
    user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    queue: DianQueue = Depends(get_dian_queue),
) -> DianDocOut:
    """Retries transmission for a failed or pending electronic document.

    Restricted to admin / gerente roles.
    """
    if user.role not in ERP_ERP_MANAGEMENT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Rol '{user.role}' no tiene permiso para reintentar transmisiones DIAN",
        )

    force = payload.force if payload else False
    return queue.retry_sale(sale_id=sale_id, tenant_id=tenant_id, force=force)


@router.post(
    "/enqueue/{sale_id}",
    response_model=DianDocOut,
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_dian_transmission(
    sale_id: str,
    _user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant),
    repo: ERPRepository = Depends(get_erp_repo),
    queue: DianQueue = Depends(get_dian_queue),
) -> DianDocOut:
    """Enqueues an issued sale for DIAN electronic transmission and executes initial dispatch."""
    sale = repo.get_sale(tenant_id=tenant_id, sale_id=sale_id)
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sale '{sale_id}' not found for tenant '{tenant_id}'",
        )
    if sale.status == "voided":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot enqueue a voided sale for DIAN transmission",
        )

    doc = queue.enqueue_sale(sale=sale, tenant_id=tenant_id)
    # Process queue with stub adapter
    queue.process_queue(tenant_id=tenant_id, ignore_backoff=True)
    updated_doc = queue.get_dian_status_for_sale(sale_id=sale_id, tenant_id=tenant_id)
    return updated_doc or doc
