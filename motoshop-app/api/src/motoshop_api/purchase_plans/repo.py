"""Repositorio para purchase_plans: Fake (in-memory) + Real (MySQL)."""
from __future__ import annotations

from datetime import datetime
from typing import Protocol

from motoshop_api.purchase_plans.schemas import (
    PurchasePlanCreate,
    PurchasePlanListResponse,
    PurchasePlanResponse,
    PurchasePlanStatusUpdate,
)


class PurchasePlansRepoProtocol(Protocol):
    def create(self, created_by: str, data: PurchasePlanCreate) -> PurchasePlanResponse: ...
    def list(self, created_by: str | None = None, limit: int = 50, offset: int = 0) -> PurchasePlanListResponse: ...
    def get(self, plan_id: int) -> PurchasePlanResponse | None: ...
    def update_status(self, plan_id: int, data: PurchasePlanStatusUpdate) -> PurchasePlanResponse | None: ...


class FakePurchasePlansRepo:
    """Repositorio en memoria para tests y desarrollo local."""

    def __init__(self) -> None:
        self._store: dict[int, dict] = {}
        self._next_id = 1

    def create(self, created_by: str, data: PurchasePlanCreate) -> PurchasePlanResponse:
        plan = {
            "id": self._next_id,
            "created_by": created_by,
            "created_at": datetime.now(),
            "plan_name": data.plan_name,
            "total_skus": data.total_skus,
            "total_value": data.total_value,
            "items": [i.model_dump() for i in data.items],
            "status": "draft",
        }
        self._store[self._next_id] = plan
        self._next_id += 1
        return PurchasePlanResponse(**plan)

    def list(self, created_by: str | None = None, limit: int = 50, offset: int = 0) -> PurchasePlanListResponse:
        items = list(self._store.values())
        if created_by:
            items = [i for i in items if i["created_by"] == created_by]
        items = sorted(items, key=lambda i: i["created_at"], reverse=True)
        total = len(items)
        page = items[offset:offset + limit]
        return PurchasePlanListResponse(
            items=[PurchasePlanResponse(**i) for i in page],
            total=total,
        )

    def get(self, plan_id: int) -> PurchasePlanResponse | None:
        plan = self._store.get(plan_id)
        return PurchasePlanResponse(**plan) if plan else None

    def update_status(self, plan_id: int, data: PurchasePlanStatusUpdate) -> PurchasePlanResponse | None:
        plan = self._store.get(plan_id)
        if not plan:
            return None
        plan["status"] = data.status
        return PurchasePlanResponse(**plan)


# Singleton para tests
_fake_repo: FakePurchasePlansRepo | None = None


def get_purchase_plans_repo() -> PurchasePlansRepoProtocol:
    global _fake_repo
    if _fake_repo is None:
        _fake_repo = FakePurchasePlansRepo()
    return _fake_repo
