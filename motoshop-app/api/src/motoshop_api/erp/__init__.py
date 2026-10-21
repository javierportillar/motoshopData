"""ERP and POS package.

Union of two lineages on the same package:
- POS-core ``repo`` facade (ERPRepository) and
- the transactional write-path for erp-transaccional-web slices 1-6,
  per ADR-0008-03/07/09: ``uow``, ``journal``, ``engine``
  (φ0..φ4), ``idempotency``, ``common`` (Decimal/latin1 palette)
  and ``guards`` (JWT role / module matrix / tenant enablement).
"""

from __future__ import annotations

from motoshop_api.erp.repo import ERPRepository, get_erp_repo, reset_erp_repo

__all__ = ["ERPRepository", "get_erp_repo", "reset_erp_repo"]
