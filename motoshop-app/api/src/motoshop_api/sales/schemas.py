"""Schemas de ventas."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class SaleOut(BaseModel):
    numfven: str
    fecfven: str | None = None
    nitter: str | None = None
    estfven: str | None = None
    totfven: float | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def convert_types(cls, data):
        if isinstance(data, dict):
            if "fecfven" in data and data["fecfven"] is not None:
                data["fecfven"] = str(data["fecfven"])
            if "totfven" in data and data["totfven"] is not None:
                data["totfven"] = float(data["totfven"])
        return data


class SalesPage(BaseModel):
    items: list[SaleOut]
    total: int
    limit: int
