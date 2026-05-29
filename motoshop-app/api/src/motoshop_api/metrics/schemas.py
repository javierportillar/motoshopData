"""Schemas Pydantic para los endpoints /metrics/*.

Contrato entre Track T (PWA) y Track A (Gold marts). Dev A construye
los marts con exactamente estos campos. Dev T los consume.

Cuando los marts reales no estén disponibles, FakeMetricsRepo
devuelve datos realistas de demo.
"""

from __future__ import annotations

from pydantic import BaseModel


# ── Shared ────────────────────────────────────────────────────────────────

class TopSkuItem(BaseModel):
    cod_producto: str
    nom_producto: str
    cantidad_total: float
    valor_total: float
    porcentaje_ingreso: float | None = None


class BodegaItem(BaseModel):
    cod_bodega: str
    nom_bodega: str
    cantidad: float
    porcentaje: float


class DormidoItem(BaseModel):
    cod_producto: str
    nom_producto: str
    dias_sin_venta: int
    stock_actual: float | None = None


class CohorteItem(BaseModel):
    cohorte_mes: str               # YYYY-MM, mes de primera compra
    mes_observacion: str           # YYYY-MM, mes observado
    num_clientes: int
    ticket_promedio: float
    tasa_recurrencia: float | None = None  # % que compró otra vez


class AbcBucket(BaseModel):
    categoria: str                 # A / B / C
    num_skus: int
    valor_total: float
    porcentaje_ingreso: float


# ── Response models ──────────────────────────────────────────────────────

class SalesSummary(BaseModel):
    business_month: str            # YYYY-MM
    ventas_mes_actual: float
    ventas_mes_anterior: float
    delta_porcentual: float | None = None
    ticket_promedio: float
    num_facturas: int
    top_skus: list[TopSkuItem]


class InventorySummary(BaseModel):
    stock_total: float
    valor_total: float
    num_productos: int
    por_bodega: list[BodegaItem]


class AbcSegmentation(BaseModel):
    business_month: str
    total_skus: int
    total_ingresos: float
    bucket_a: AbcBucket
    bucket_b: AbcBucket
    bucket_c: AbcBucket


class DormidosResponse(BaseModel):
    total: int
    productos: list[DormidoItem]


class CohortesResponse(BaseModel):
    cohortes: list[CohorteItem]
