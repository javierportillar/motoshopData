"""DIAN electronic invoicing module (Slice 6, spec erp-dian-einvoicing)."""

from motoshop_api.erp.dian.adapter import (
    DianAdapter,
    DianStubAdapter,
    compute_pseudo_cufe,
    generate_qr_url,
)
from motoshop_api.erp.dian.models import (
    DianDocOut,
    DianQueueListOut,
    DianRetryIn,
    DianStatusEnum,
)
from motoshop_api.erp.dian.queue import (
    DianQueue,
    get_dian_queue,
    reset_dian_queue,
)
from motoshop_api.erp.dian.router import router as dian_router

__all__ = [
    "DianAdapter",
    "DianDocOut",
    "DianQueue",
    "DianQueueListOut",
    "DianRetryIn",
    "DianStatusEnum",
    "DianStubAdapter",
    "compute_pseudo_cufe",
    "dian_router",
    "generate_qr_url",
    "get_dian_queue",
    "reset_dian_queue",
]
