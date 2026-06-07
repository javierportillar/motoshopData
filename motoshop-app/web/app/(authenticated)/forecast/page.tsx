"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useForecast, useForecastCategoria, useForecastNarrative, useProducts } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import {
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";

const HORIZON_OPTIONS = [7, 14, 30] as const;

function CustomBarTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-md">
      <p className="font-medium text-text-primary">{label}</p>
      <p className="mt-1 text-text-secondary">
        <strong>{d.predicted}</strong> unidades
      </p>
      {(d.ciLower != null || d.ciUpper != null) && (
        <p className="text-text-muted">
          IC: {d.ciLower}–{d.ciUpper}
        </p>
      )}
    </div>
  );
}


export default function ForecastPage(): JSX.Element {
  const [sku, setSku] = useState("");
  const [selectedSku, setSelectedSku] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<number>(7);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");

  const { data, error, isLoading } = useForecast(selectedSku, horizon);

  // Debounce search query before sending to API
  useEffect(() => {
    const timer = setTimeout(() => setSearchQuery(sku), 300);
    return () => clearTimeout(timer);
  }, [sku]);

  // Fetch products from API for autocomplete
  const { data: productsData } = useProducts(
    searchQuery,
    1,
    20,
  );

  // Auto-select first product with forecast on initial load
  useEffect(() => {
    if (!selectedSku && productsData?.items && productsData.items.length > 0) {
      const first = productsData.items.find((p: any) => p.has_forecast === true) ?? productsData.items[0];
      if (first) {
        setSku(first.codprod);
        setSelectedSku(first.codprod);
      }
    }
  }, [productsData, selectedSku]);

  const suggestions = useMemo(() => {
    if (!productsData?.items) return [];
    return productsData.items
      .filter((p) => p.has_forecast === true)
      .map((p) => ({ sku: p.codprod, label: p.nomprod }));
  }, [productsData]);

  const chartData = useMemo(() => {
    if (!data?.forecast) return [];
    return data.forecast.map((f) => ({
      date: f.forecast_date.slice(5),
      predicted: f.predicted_qty,
      lower: f.confidence_lower ?? f.predicted_qty * 0.8,
      upper: f.confidence_upper ?? f.predicted_qty * 1.2,
    }));
  }, [data]);

  // Separate fetch with max horizon for bar chart aggregation
  const { data: barSourceData } = useForecast(selectedSku, 30);

  // Aggregate 30-day data into 3 period buckets for the bar chart
  const barChartData = useMemo(() => {
    if (!barSourceData?.forecast) return [];
    const items = barSourceData.forecast;
    const buckets = [
      { label: "0–7 días", start: 0, end: 7 },
      { label: "7–14 días", start: 7, end: 14 },
      { label: "14–30 días", start: 14, end: 30 },
    ];
    return buckets
      .filter((b) => b.start < items.length)
      .map((b) => {
        const slice = items.slice(b.start, Math.min(b.end, items.length));
        if (slice.length === 0) return null;
        const predicted = Number(slice.reduce((s, f) => s + f.predicted_qty, 0).toFixed(1));
        const ciLower = Number(
          slice.reduce((s, f) => s + (f.confidence_lower ?? f.predicted_qty * 0.8), 0).toFixed(1),
        );
        const ciUpper = Number(
          slice.reduce((s, f) => s + (f.confidence_upper ?? f.predicted_qty * 1.2), 0).toFixed(1),
        );
        return { horizon: b.label, predicted, ciLower, ciUpper };
      })
      .filter(Boolean) as { horizon: string; predicted: number; ciLower: number; ciUpper: number }[];
  }, [barSourceData]);

  // Category-level data for comparative chart
  const { data: categoriaData } = useForecastCategoria();

  // Forecast narrative (V1.6 Sprint B)
  const { data: narrative, isLoading: narrativeLoading, mutate: refreshNarrative } = useForecastNarrative();

  function handleSelect(suggestionSku: string) {
    setSku(suggestionSku);
    setSelectedSku(suggestionSku);
    setShowSuggestions(false);
  }

  function handleSearch() {
    if (sku.trim()) {
      setSelectedSku(sku.trim().toUpperCase());
      setShowSuggestions(false);
    }
  }

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">
        ← Volver a inicio
      </Link>

      <div>
        <h1 className="text-xl font-bold text-text-primary">Predicciones de demanda</h1>
        <p className="text-sm text-text-muted">
          Forecast por categoría (vista principal) + drilldown por SKU
        </p>
      </div>

      <StaleDataBanner />

      {/* Forecast Narrative Card (V1.6 Sprint B) */}
      {narrativeLoading ? (
        <Card header={<h2 className="font-semibold text-text-primary">Análisis del forecast</h2>}>
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        </Card>
      ) : narrative ? (
        <Card
          header={
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-text-primary">Análisis del forecast</h2>
              <button
                onClick={() => refreshNarrative()}
                className="rounded px-2 py-1 text-xs text-text-muted hover:bg-surface-alt hover:text-text-secondary transition-colors"
              >
                Regenerar
              </button>
            </div>
          }
        >
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
            {narrative.text}
          </p>
          <p className="mt-3 text-xs text-text-muted">
            Generado por IA · {narrative.generated_at ? new Date(narrative.generated_at).toLocaleString("es-CO") : ""}
          </p>
        </Card>
      ) : null}

      {/* F7-FIX1 bug 6.2 + 4.5: explicación pedagógica de por qué por categoría */}
      <Card>
        <details className="text-sm" open>
          <summary className="cursor-pointer font-medium text-text-primary">
            ¿Por qué predecimos por categoría y no por producto individual?
          </summary>
          <div className="mt-3 space-y-2 text-text-secondary">
            <p>
              El catálogo tiene <strong>~6,000 SKUs</strong>. La mayoría tiene menos de 30 ventas al año
              — demanda intermitente, no se puede predecir cada SKU individual con confianza estadística.
            </p>
            <p>
              <strong>Solución:</strong> agrupar por categoría (cod_grupo). Predicción por categoría
              tiene WAPE ~34% sostenido; por SKU individual da WAPE 45%+ y métricas inestables.
              Decisión documentada en ADR-0020.
            </p>
            <p>
              <strong>Drilldown:</strong> abajo podés buscar un SKU específico si querés verlo.
              Los SKUs con poca historia no devolverán predicción (es honesto, no es bug).
            </p>
            <p className="text-xs text-text-muted">
              Horizonte 7/14/30 días: cada barra es la demanda esperada
              <strong> acumulada</strong> en esa ventana (no por intervalo).
            </p>
          </div>
        </details>
      </Card>

      {/* Forecast por categoría — vista principal (F7-FIX1 bug 4.5) */}
      {categoriaData?.items && categoriaData.items.length > 0 && (
        <Card header={
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-text-primary">Predicción por categoría</h2>
            <Badge variant="default" size="sm">
              WAPE: {categoriaData.wape_promedio?.toFixed(1)}% · {categoriaData.total_categorias} categorías
            </Badge>
          </div>
        }>
          <div className="space-y-2">
            {categoriaData.items
              .slice()
              .sort((a, b) => b.demanda_real - a.demanda_real)
              .map((cat) => (
                <div
                  key={cat.cod_grupo}
                  className="flex flex-col gap-2 rounded-lg border border-border bg-surface-alt px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm font-medium text-text-primary">
                      {cat.cod_grupo === "SIN_GRUPO" ? "Sin clasificar" : cat.cod_grupo}
                    </span>
                    {cat.cod_grupo === "SIN_GRUPO" && (
                      <Badge variant="warning" size="sm">datos stale</Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <span className="text-text-muted">
                      Real: <strong className="text-text-primary">{cat.demanda_real.toFixed(0)}</strong> u.
                    </span>
                    <span className="text-text-muted">
                      Pred: <strong className="text-text-primary">{cat.demanda_predicha.toFixed(0)}</strong> u.
                    </span>
                    <Badge
                      variant={
                        Math.abs(cat.desviacion_pct) > 20
                          ? "error"
                          : Math.abs(cat.desviacion_pct) > 10
                            ? "warning"
                            : "success"
                      }
                      size="sm"
                    >
                      desv. {cat.desviacion_pct > 0 ? "+" : ""}{cat.desviacion_pct.toFixed(1)}%
                    </Badge>
                    <span className="text-xs text-text-muted">{cat.metodo}</span>
                  </div>
                </div>
              ))}
          </div>
        </Card>
      )}

      {/* Drilldown por SKU */}
      <div className="pt-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-muted">
          Drilldown por SKU (opcional)
        </h2>
      </div>

      {/* Buscador de SKU */}
      <div className="relative">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={sku}
              onChange={(e) => {
                setSku(e.target.value);
                setShowSuggestions(true);
                if (selectedSku && e.target.value !== selectedSku) {
                  setSelectedSku(null);
                }
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Ej: MOTS1297"
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-surface shadow-lg">
                {suggestions.map((s) => (
                  <button
                    key={s.sku}
                    onMouseDown={() => handleSelect(s.sku)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-surface-alt"
                  >
                    <span className="font-mono text-xs font-medium text-primary">
                      {s.sku}
                    </span>
                    <span className="truncate text-text-secondary">{s.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={handleSearch}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg hover:bg-primary-light"
          >
            Buscar
          </button>
        </div>
      </div>

      {/* Selector de horizonte */}
      {selectedSku && (
        <div className="flex gap-2">
          {HORIZON_OPTIONS.map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                horizon === h
                  ? "bg-primary text-primary-fg"
                  : "bg-surface-alt text-text-secondary hover:bg-surface-alt/80"
              }`}
            >
              {h} días
            </button>
          ))}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-60 rounded-xl" />
        </div>
      )}

      {/* Error */}
      {error && (
        <ErrorState title="Error al cargar" message="No se pudieron obtener los datos de predicciones." severity="warning" />
      )}

      {/* Forecast chart */}
      {data && chartData.length > 0 && (
        <>
          <Card
            header={
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-text-primary">{data.sku}</h2>
                {data.metrics && (
                  <Badge variant="default" size="sm">
                    MAPE: {data.metrics.mape?.toFixed(1)}% · v{data.metrics.model_version}
                  </Badge>
                )}
              </div>
            }
          >
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#a3a3a3" />
                <YAxis tick={{ fontSize: 11 }} stroke="#a3a3a3" tickFormatter={(v: number) => Math.round(v).toString()} />
                <Tooltip
                  formatter={(value) => [Math.round(Number(value ?? 0)).toString(), "unidades"]}
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #d4d4d4",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="#0EA5E9"
                  fillOpacity={0.1}
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="#FFFFFF"
                  fillOpacity={0.3}
                />
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="#0EA5E9"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "#0EA5E9" }}
                  activeDot={{ r: 5 }}
                />
              </AreaChart>
            </ResponsiveContainer>
            <div className="mt-2 flex items-center gap-4 text-xs text-text-muted">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-4 rounded bg-accent" /> Predicción
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-4 rounded bg-accent/10" /> IC 80%
              </span>
            </div>
          </Card>

          {/* Gráfico de barras por período */}
          {barChartData.length > 0 && (
            <Card header={<h2 className="font-semibold text-text-primary">Resumen por período</h2>}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={barChartData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="horizon" tick={{ fontSize: 11 }} stroke="#a3a3a3" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#a3a3a3" tickFormatter={(v) => Math.round(v).toString()} />
                  <Tooltip content={<CustomBarTooltip />} />
                  <Bar dataKey="predicted" fill="#0EA5E9" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

        </>
      )}

      {/* Estado vacío del SKU drilldown */}
      {!selectedSku && !isLoading && (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Buscá un SKU específico arriba para ver su predicción individual.
            La vista principal de categorías ya está mostrando arriba.
          </p>
        </Card>
      )}
    </div>
  );
}
