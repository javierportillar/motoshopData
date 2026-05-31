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
    ultima_compra: str | None = None
    dias_sin_venta: int
    stock_actual: float | None = None


class CohorteItem(BaseModel):
    cohorte_mes: str               # YYYY-MM, mes de primera compra
    mes_observacion: str           # YYYY-MM, mes observado
    num_clientes: int
    ticket_promedio: float
    tasa_recurrencia: float | None = None  # % que compró otra vez
    muestra_pequena: bool = False  # True si num_clientes < 5, para advertencia en frontend


class AbcBucket(BaseModel):
    categoria: str                 # A / B / C
    num_skus: int
    valor_total: float
    porcentaje_ingreso: float


# ── Sales Daily / Monthly / Historical ───────────────────────────────────

class SalesDailyItem(BaseModel):
    sku: str
    nombre: str
    cantidad: float
    valor: float


class SalesDailyResponse(BaseModel):
    date: str
    total_ventas: float
    total_facturas: int
    productos_vendidos: list[SalesDailyItem]


class SalesMonthlyResponse(BaseModel):
    month: str
    total_ventas: float
    total_facturas: int
    delta_porcentaje: float | None = None
    productos_top: list[TopSkuItem]


class SalesHistoricalResponse(BaseModel):
    total_ventas: float
    total_facturas: int
    meses: list[SalesTrendItem]
    fecha_primera_venta: str | None = None


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


class SalesTrendItem(BaseModel):
    year: int
    month: int
    total_ventas: float
    num_facturas: int
    ticket_promedio: float


class SalesTrendResponse(BaseModel):
    periods: int
    items: list[SalesTrendItem]


class VendedorItem(BaseModel):
    nit_vendedor: str
    nombre_vendedor: str
    facturas: int
    total_ventas: float
    ticket_promedio: float


class VendedoresSummaryResponse(BaseModel):
    items: list[VendedorItem]


class VendedorCategoriaItem(BaseModel):
    categoria: str
    total: float


class VendedorComparacion(BaseModel):
    actual: float
    anterior: float
    delta: float | None = None


class VendedorDetailResponse(BaseModel):
    vendedor_id: str
    nombre: str
    ventas_total: float
    ventas_por_categoria: list[VendedorCategoriaItem]
    ticket_promedio: float
    productos_vendidos: int
    comparacion_mes_anterior: VendedorComparacion


class CohorteRetencionItem(BaseModel):
    mes_observacion: str
    num_clientes: int
    tasa_recurrencia: float


class CohorteDetailItem(BaseModel):
    cohorte_mes: str
    total_clientes: int
    ltv_promedio: float
    retencion: list[CohorteRetencionItem]


class CohortesDetailResponse(BaseModel):
    cohortes: list[CohorteDetailItem]
    total_cohortes: int
    nuevos_este_mes: int
    recurrentes_este_mes: int
    top_recurrentes: int


class DriftSummaryItem(BaseModel):
    metric_name: str
    detected_at: str
    drift_magnitude: float
    threshold: float
    status: str  # active | resolved | warning
    recommended_action: str


class DriftSummaryResponse(BaseModel):
    items: list[DriftSummaryItem]
    total_alerts: int
    active_count: int
    warning_count: int
    current_threshold: float


class PlanCompraItem(BaseModel):
    sku: str
    nombre: str
    stock_actual: float
    demanda_7d: float
    cantidad_a_comprar: float
    abc: str  # A | B | C
    urgencia: str | None = None  # alta | media | baja
    dormido: bool
    supplier: str


class PlanComprasResponse(BaseModel):
    items: list[PlanCompraItem]
    total_skus: int
    total_unidades: float
    total_valor_estimado: float
    skus_urgentes: int
    skus_dormidos: int


class ForecastCategoriaItem(BaseModel):
    cod_grupo: str
    demanda_real: float
    demanda_predicha: float
    desviacion_pct: float
    metodo: str


class ForecastCategoriaResponse(BaseModel):
    items: list[ForecastCategoriaItem]
    total_categorias: int
    wape_promedio: float
    cobertura_pct: float
