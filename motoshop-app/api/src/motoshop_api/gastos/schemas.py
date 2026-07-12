"""Schemas Pydantic para gastos operativos."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


CATEGORIAS_VALIDAS = {
    "arriendo",
    "nomina",
    "servicios",
    "mantenimiento",
    "marketing",
    "impuestos",
    "combustible",
    "transporte",
    "papeleria",
    "seguros",
    "otros",
}


class GastoBase(BaseModel):
    mes: str = Field(..., description="YYYY-MM")
    categoria: str = Field(..., description="Una de las categorías predefinidas")
    monto: float = Field(..., ge=0)
    descripcion: str | None = None

    @field_validator("mes")
    @classmethod
    def validar_mes(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("mes debe tener formato YYYY-MM")
        return v

    @field_validator("categoria")
    @classmethod
    def validar_categoria(cls, v: str) -> str:
        v_lower = v.lower().strip()
        if v_lower not in CATEGORIAS_VALIDAS:
            raise ValueError(
                f"categoria inválida. Válidas: {', '.join(sorted(CATEGORIAS_VALIDAS))}"
            )
        return v_lower


class GastoCreate(GastoBase):
    """Payload para crear un gasto."""


class GastoUpdate(BaseModel):
    """Payload para actualizar un gasto. Todos los campos opcionales."""

    mes: str | None = None
    categoria: str | None = None
    monto: float | None = Field(default=None, ge=0)
    descripcion: str | None = None

    @field_validator("mes")
    @classmethod
    def validar_mes(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("mes debe tener formato YYYY-MM")
        return v

    @field_validator("categoria")
    @classmethod
    def validar_categoria(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v_lower = v.lower().strip()
        if v_lower not in CATEGORIAS_VALIDAS:
            raise ValueError(
                f"categoria inválida. Válidas: {', '.join(sorted(CATEGORIAS_VALIDAS))}"
            )
        return v_lower


class CopiarGastosRequest(BaseModel):
    """Copia gastos de un mes a otro. Si `ids` viene, sólo copia esos."""

    mes_origen: str = Field(..., description="YYYY-MM")
    mes_destino: str = Field(..., description="YYYY-MM")
    ids: list[int] | None = Field(
        default=None, description="Subconjunto de gastos del mes origen a copiar; None = todos"
    )

    @field_validator("mes_origen", "mes_destino")
    @classmethod
    def validar_mes(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}$", v):
            raise ValueError("mes debe tener formato YYYY-MM")
        return v


class GastoResponse(GastoBase):
    id: int
    tenant: str
    created_at: str
    updated_at: str
    created_by: str | None = None


class GastosListResponse(BaseModel):
    items: list[GastoResponse]
    total: int


class CategoriasResponse(BaseModel):
    """Catálogo de categorías predefinidas."""
    categorias: list[str]
