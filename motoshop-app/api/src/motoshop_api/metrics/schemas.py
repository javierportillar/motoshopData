"""Schemas Pydantic para los endpoints /metrics/*.

Contrato entre Track T (PWA) y Track A (Gold marts). Dev A construye
los marts con exactamente estos campos. Dev T los consume.

Cuando los marts reales no estén disponibles, FakeMetricsRepo
devuelve datos realistas de demo.
"""

from __future__ import annotations

from typing import Literal

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
    ultima_venta: str | None = None
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


# ── Sales Day Detail (V1.9 — popup detallado por día) ─────────────────────

class SalesHourBucket(BaseModel):
    """Ventas agregadas por hora del día (0-23)."""
    hour: int
    total_ventas: float
    num_facturas: int
    ticket_promedio: float


class VendedorDayItem(BaseModel):
    """Vendedor con sus ventas del día/mes."""
    nombre_vendedor: str
    nit_vendedor: str | None = None
    total_ventas: float
    num_facturas: int
    porcentaje: float | None = None  # % del total


class FormaPagoItem(BaseModel):
    """Forma de pago con su volumen."""
    cod_formapago: str
    nombre: str  # Etiqueta legible
    total_ventas: float
    num_facturas: int
    porcentaje: float


class DayComparativa(BaseModel):
    """Comparativa de un día contra otro periodo (semana, mes, año)."""
    label: str  # "semana pasada", "mes pasado", "año pasado"
    fecha_comparada: str
    total_ventas: float
    delta_porcentaje: float | None  # null si el comparado fue 0


class SalesDayDetailResponse(BaseModel):
    """Detalle completo de un día específico para el popup del calendario."""
    date: str
    # KPIs principales
    total_ventas: float
    total_facturas: int
    ticket_promedio: float
    margen_bruto: float  # total_ventas - sum(costo)
    margen_porcentaje: float | None  # null si total_ventas == 0
    items_por_factura: float  # promedio
    ticket_mas_alto: float
    # Distribución horaria
    distribucion_horaria: list[SalesHourBucket]
    hora_pico: int | None  # hora con más ventas
    # Productos top del día (hasta 30)
    productos_top: list[SalesDailyItem]
    # Vendedores del día
    vendedores_top: list[VendedorDayItem]
    # Forma de pago breakdown
    formas_pago: list[FormaPagoItem]
    # Comparativas
    comparativas: list[DayComparativa]


# ── Sales Month Detail (V1.9 — detalle enriquecido del mes) ────────────────

class SalesMonthDetailResponse(BaseModel):
    """Detalle enriquecido del mes: complementa a sales-summary."""
    month: str
    # Métricas de rentabilidad
    margen_bruto: float
    margen_porcentaje: float | None
    # Vendedores top
    vendedores_top: list[VendedorDayItem]
    # Forma de pago breakdown
    formas_pago: list[FormaPagoItem]
    # Mejores y peores días del mes
    mejor_dia: dict | None  # {"date": "YYYY-MM-DD", "total_ventas": ..., "num_facturas": ...}
    peor_dia: dict | None
    # Productos en aceleración / desaceleración vs mes anterior
    aceleradores: list[TopSkuItem]  # top 3 que más crecieron
    frenadores: list[TopSkuItem]    # top 3 que más cayeron


# ── Cash Closure (V1.9.1 — cierre de caja del día) ────────────────────────

class CashClosureFormaPago(BaseModel):
    """Forma de pago dentro del cierre del día (con ticket promedio)."""
    cod_formapago: str
    nombre: str
    total_ventas: float
    num_facturas: int
    ticket_promedio: float
    porcentaje: float


class CashClosureFactura(BaseModel):
    """Factura individual del cierre."""
    num_documento: str
    prefijo: str | None = None
    hora: str  # HH:MM
    cliente: str
    vendedor: str
    cod_formapago: str
    nombre_formapago: str
    total: float


class CashClosureResponse(BaseModel):
    """Cierre de caja del día — tipo Z-report del POS."""
    date: str
    total_dia: float
    total_facturas: int
    formas_pago: list[CashClosureFormaPago]
    facturas: list[CashClosureFactura]
    top_facturas_grandes: list[CashClosureFactura]


# ── Payments History (V1.9.1 — tendencia histórica formas de pago) ────────

class PaymentsHistoryFormaPago(BaseModel):
    cod_formapago: str
    nombre: str


class PaymentsHistoryMonthEntry(BaseModel):
    month: str  # YYYY-MM
    total: float
    formas_pago: list[FormaPagoItem]  # reusamos el schema (con porcentaje)


class PaymentsHistoryMonthSimple(BaseModel):
    """Entrada de serie mensual sin porcentaje (solo total bruto por forma)."""
    cod_formapago: str
    nombre: str
    total_ventas: float


class PaymentsHistoryMonth(BaseModel):
    month: str
    total: float
    formas_pago: list[PaymentsHistoryMonthSimple]


class PaymentsVariacionItem(BaseModel):
    cod_formapago: str
    nombre: str
    pct_actual: float
    pct_seis_meses_atras: float
    delta_puntos: float


class PaymentsHistoryResponse(BaseModel):
    months: int
    formas_pago: list[PaymentsHistoryFormaPago]  # universo de codigos vistos
    series: list[PaymentsHistoryMonth]  # serie mensual stacked
    variacion_seis_meses: list[PaymentsVariacionItem]


# ── Sales Day Invoices (V1.9.2 — facturas con items expandidos) ───────────

class InvoiceItem(BaseModel):
    num_item: int
    cod_producto: str
    nombre: str
    cantidad: float
    valor_unitario: float
    descuento_valor: float
    iva_valor: float
    total_detalle: float
    # V1.10.2: costo y ganancia (costo con fallback a ultima compra)
    costo_unitario: float = 0.0
    costo_total: float = 0.0
    ganancia: float | None = None
    margen_pct: float | None = None
    cod_bodega: str | None = None


class DayInvoice(BaseModel):
    num_documento: str
    cod_clase: str
    prefijo: str | None = None
    hora: str  # HH:MM
    cliente: str
    vendedor: str
    cod_formapago: str
    nombre_formapago: str
    subtotal: float
    total_descuentos: float
    total_iva: float
    total: float
    costo_total: float = 0.0
    ganancia: float | None = None
    margen_pct: float | None = None
    items: list[InvoiceItem]


class SalesDayInvoicesResponse(BaseModel):
    date: str
    total_facturas: int
    total_dia: float
    total_costo: float = 0.0
    total_ganancia: float | None = None
    total_items: int
    invoices: list[DayInvoice]


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
    page: int
    page_size: int
    total: int
    items: list[DormidoItem]
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


class AbcDetalleItem(BaseModel):
    cod_producto: str
    nom_producto: str
    valor_total: float
    porcentaje_bucket: float


class AbcDetalleResponse(BaseModel):
    bucket: str
    total_skus: int
    total_valor: float
    items: list[AbcDetalleItem]


class ActionRecommendationItem(BaseModel):
    sku: str
    nom_producto: str
    reason: str
    priority: Literal["alta", "media", "baja"]
    period: str
    status: Literal["open", "monitor", "scheduled"]
    action_type: Literal["reponer", "liquidar", "comprar"]


class ActionRecommendationsResponse(BaseModel):
    period: str
    total: int
    items: list[ActionRecommendationItem]


# ── Purchases Day Detail (V2.0 — detalle de compras por día) ────────────────

class PurchaseDayDocument(BaseModel):
    """Documento de compra con sus items."""
    num_documento: str
    cod_producto: str
    nom_producto: str
    cantidad: float
    valor_unitario: float
    costo_producto: float | None = None
    total: float


class PurchasesDayDetailResponse(BaseModel):
    """Resumen de compras de un día específico."""
    date: str
    total_compras: float
    total_documentos: int
    items: list[PurchaseDayDocument]


# ── Análisis financiero (V1.11: horas-pico + balance) ───────────────────────

class HoraPicoItem(BaseModel):
    """Ventas y pedidos agregados por hora del día (0-23)."""
    hour: int
    total_ventas: float
    num_facturas: int
    ticket_promedio: float


class HoraPicoResponse(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    items: list[HoraPicoItem]
    hora_pico_facturas: int | None = None
    hora_pico_ventas: int | None = None


class BalanceDiaItem(BaseModel):
    """Un día del balance: ventas, costo mercancía vendida, gastos operativos."""
    date: str
    ventas: float
    costo_mercancia: float
    gastos_operativos: float
    ganancia_bruta: float       # ventas - costo_mercancia
    ganancia_neta: float        # ganancia_bruta - gastos_operativos
    balance_acumulado: float    # acumulado de ganancia_neta


class BalanceResponse(BaseModel):
    fecha_inicio: str
    fecha_fin: str
    items: list[BalanceDiaItem]
    total_ventas: float
    total_costo_mercancia: float
    total_gastos_operativos: float
    total_ganancia_bruta: float
    total_ganancia_neta: float
    margen_bruto_pct: float | None = None
    margen_neto_pct: float | None = None
