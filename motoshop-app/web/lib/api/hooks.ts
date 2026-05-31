import useSWR, { type KeyedMutator } from "swr";
import { apiFetchJson } from "./client";
import { getCached, setCache } from "@/lib/offline/cache";

interface Product {
  codprod: string;
  nomprod: string;
  codbar?: string;
  precio?: number;
  [key: string]: unknown;
}

interface ProductsResponse {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

interface StockItem {
  codbod: string;
  nombod?: string;
  cantidad: number;
}

interface StockResponse {
  sku: string;
  total: number;
  by_bodega: StockItem[];
}

const CACHE_TTL_CATALOG = 60 * 60 * 1000; // 1 hour
const CACHE_TTL_STOCK = 5 * 60 * 1000; // 5 min

async function fetchWithOfflineFallback<T>(
  url: string,
  ttlMs: number,
): Promise<T> {
  try {
    const data = await apiFetchJson<T>(url);
    await setCache(url, data, ttlMs);
    return data;
  } catch {
    const cached = await getCached<T>(url);
    if (cached) return cached;
    throw new Error("Sin conexión y sin datos cacheados");
  }
}

export function useProducts(query: string, page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const key = query
    ? `/api/products?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`
    : null;

  return useSWR<ProductsResponse>(
    key,
    (url) => fetchWithOfflineFallback<ProductsResponse>(url, CACHE_TTL_CATALOG),
    {
      revalidateOnFocus: false,
      dedupingInterval: 30_000,
    },
  );
}

export function useStock(sku: string | null) {
  const key = sku ? `/api/products/${encodeURIComponent(sku)}/stock` : null;

  return useSWR<StockResponse>(
    key,
    (url) => fetchWithOfflineFallback<StockResponse>(url, CACHE_TTL_STOCK),
    {
      revalidateOnFocus: false,
      dedupingInterval: 10_000,
    },
  );
}

// ── Metrics / Dashboards ─────────────────────────────────────────────────

interface TopSkuItem {
  cod_producto: string;
  nom_producto: string;
  cantidad_total: number;
  valor_total: number;
  porcentaje_ingreso?: number;
}

interface SalesSummary {
  business_month: string;
  ventas_mes_actual: number;
  ventas_mes_anterior: number;
  delta_porcentual?: number;
  ticket_promedio: number;
  num_facturas: number;
  top_skus: TopSkuItem[];
}

interface BodegaItem {
  cod_bodega: string;
  nom_bodega: string;
  cantidad: number;
  porcentaje: number;
}

interface InventorySummary {
  stock_total: number;
  valor_total: number;
  num_productos: number;
  por_bodega: BodegaItem[];
}

interface AbcBucket {
  categoria: string;
  num_skus: number;
  valor_total: number;
  porcentaje_ingreso: number;
}

interface AbcSegmentation {
  business_month: string;
  total_skus: number;
  total_ingresos: number;
  bucket_a: AbcBucket;
  bucket_b: AbcBucket;
  bucket_c: AbcBucket;
}

interface DormidoItem {
  cod_producto: string;
  nom_producto: string;
  dias_sin_venta: number;
  stock_actual?: number;
  ultimo_movimiento?: string;
}

interface DormidosResponse {
  total: number;
  productos: DormidoItem[];
}

interface CohorteItem {
  cohorte_mes: string;
  mes_observacion: string;
  num_clientes: number;
  ticket_promedio: number;
  tasa_recurrencia?: number;
}

interface CohortesResponse {
  cohortes: CohorteItem[];
}

const DEDUP_METRICS = 60_000; // 1 min (DT-F3-10)

function useMetrics<T>(key: string | null): {
  data: T | undefined;
  error: Error | undefined;
  isLoading: boolean;
  mutate: KeyedMutator<T>;
} {
  const { data, error, isLoading, mutate } = useSWR<T>(key, apiFetchJson<T>, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    dedupingInterval: DEDUP_METRICS,
    refreshInterval: 5 * 60_000, // refresh cada 5 min
  });
  return { data, error, isLoading, mutate };
}

export function useSalesSummary() {
  return useMetrics<SalesSummary>("/api/metrics/sales-summary");
}

export function useInventorySummary() {
  return useMetrics<InventorySummary>("/api/metrics/inventory-summary");
}

export function useAbcSegmentation() {
  return useMetrics<AbcSegmentation>("/api/metrics/abc-segmentation");
}

export function useDormidos() {
  return useMetrics<DormidosResponse>("/api/metrics/dormidos");
}

export function useCohortes() {
  return useMetrics<CohortesResponse>("/api/metrics/cohortes");
}

interface SalesTrendItem {
  year: number;
  month: number;
  total_ventas: number;
  num_facturas: number;
  ticket_promedio: number;
}

interface SalesTrendResponse {
  periods: number;
  items: SalesTrendItem[];
}

export function useSalesTrend(periods = 6) {
  return useMetrics<SalesTrendResponse>(
    `/api/metrics/sales-trend?periods=${periods}`,
  );
}

// ── Nuevos endpoints F7-D (Dev A2) ──────────────────────────────────────────

interface VendedorItem {
  nit_vendedor: string;
  nombre_vendedor: string;
  facturas: number;
  total_ventas: number;
  ticket_promedio: number;
}

interface VendedoresSummaryResponse {
  items: VendedorItem[];
}

export function useVendedoresSummary() {
  return useMetrics<VendedoresSummaryResponse>("/api/metrics/vendedores-summary");
}

interface CohorteRetencionItem {
  mes_observacion: string;
  num_clientes: number;
  tasa_recurrencia: number;
}

interface CohorteDetailItem {
  cohorte_mes: string;
  total_clientes: number;
  ltv_promedio: number;
  retencion: CohorteRetencionItem[];
}

interface CohortesDetailResponse {
  cohortes: CohorteDetailItem[];
  total_cohortes: number;
  nuevos_este_mes: number;
  recurrentes_este_mes: number;
  top_recurrentes: number;
}

export function useCohortesDetail() {
  return useMetrics<CohortesDetailResponse>("/api/metrics/cohortes-detail");
}

interface DriftItem {
  metric_name: string;
  detected_at: string;
  drift_magnitude: number;
  threshold: number;
  status: string; // active | resolved | warning
  recommended_action: string;
}

interface DriftSummaryResponse {
  items: DriftItem[];
  total_alerts: number;
  active_count: number;
  warning_count: number;
  current_threshold: number;
}

export function useDriftSummary() {
  return useMetrics<DriftSummaryResponse>("/api/metrics/drift-summary");
}

interface PlanCompraItem {
  sku: string;
  nombre: string;
  stock_actual: number;
  demanda_7d: number;
  cantidad_a_comprar: number;
  abc: string; // A | B | C
  urgencia: string | null; // alta | media | baja
  dormido: boolean;
  supplier: string;
}

interface PlanComprasResponse {
  items: PlanCompraItem[];
  total_skus: number;
  total_unidades: number;
  total_valor_estimado: number;
  skus_urgentes: number;
  skus_dormidos: number;
}

export function usePlanCompras() {
  return useMetrics<PlanComprasResponse>("/api/metrics/plan-compras");
}

interface ForecastCategoriaItem {
  cod_grupo: string;
  demanda_real: number;
  demanda_predicha: number;
  desviacion_pct: number;
  metodo: string;
}

interface ForecastCategoriaResponse {
  items: ForecastCategoriaItem[];
  total_categorias: number;
  wape_promedio: number;
  cobertura_pct: number;
}

export function useForecastCategoria() {
  return useMetrics<ForecastCategoriaResponse>("/api/metrics/forecast-categoria");
}

// ── Forecast / Predicciones ────────────────────────────────────────────────

interface ForecastItem {
  sku: string;
  forecast_date: string;
  horizon: number;
  predicted_qty: number;
  model_version: string;
  confidence_lower?: number;
  confidence_upper?: number;
}

interface ForecastMetrics {
  model_version: string;
  mape?: number;
  smape?: number;
  training_date?: string;
}

interface ForecastResponse {
  sku: string;
  forecast: ForecastItem[];
  metrics?: ForecastMetrics;
}

const FORECAST_DEDUP = 60_000;

export function useForecast(sku: string | null, horizon: number) {
  const key = sku ? `/api/forecast/${encodeURIComponent(sku)}?horizon=${horizon}` : null;
  return useSWR<ForecastResponse>(key, apiFetchJson<ForecastResponse>, {
    revalidateOnFocus: false,
    dedupingInterval: FORECAST_DEDUP,
    refreshInterval: 5 * 60_000,
  });
}

// ── Alerts / Alertas ──────────────────────────────────────────────────────

interface AlertItem {
  sku: string;
  nom_producto: string;
  stock_actual: number;
  demanda_predicha: number;
  dias_hasta_quiebre: number;
  urgencia: "alta" | "media" | "baja";
}

interface AlertsResponse {
  alerts: AlertItem[];
  total: number;
  timestamp: string;
}

export function useAlerts(urgency?: string) {
  const qs = urgency ? `?urgency=${urgency}` : "";
  return useSWR<AlertsResponse>(
    `/api/alerts/stockout${qs}`,
    apiFetchJson<AlertsResponse>,
    {
      revalidateOnFocus: false,
      dedupingInterval: FORECAST_DEDUP,
      refreshInterval: 5 * 60_000,
    },
  );
}
