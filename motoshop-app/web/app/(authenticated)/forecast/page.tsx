"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { useForecast, useProducts } from "@/lib/api/hooks";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";
import { formatMoney } from "@/lib/format/currency";

const HORIZON_OPTIONS = [7, 14, 30] as const;


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
    !selectedSku && sku.trim() ? searchQuery : "",
    1,
    20,
  );

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
        <h1 className="text-xl font-bold text-text-primary">Predicciones</h1>
        <p className="text-sm text-text-muted">
          Demanda estimada por SKU
        </p>
      </div>

      <StaleDataBanner />

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

          {/* Tabla de valores */}
          <Card header={<h2 className="font-semibold text-text-primary">Valores</h2>}>
            <div className="space-y-1">
              {data.forecast.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg bg-surface-alt px-3 py-2"
                >
                  <span className="text-xs text-text-muted">{f.forecast_date}</span>
                  <div className="text-right">
                    <span className="text-sm font-medium text-text-primary">
                      {f.predicted_qty.toFixed(1)} u.
                    </span>
                    {f.confidence_lower != null && (
                      <span className="ml-2 text-xs text-text-muted">
                        ({f.confidence_lower.toFixed(1)}–{f.confidence_upper?.toFixed(1)})
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      {/* Estado vacío */}
      {!selectedSku && !isLoading && (
        <Card>
          <p className="py-8 text-center text-sm text-text-muted">
            Buscá un SKU para ver sus predicciones de demanda
          </p>
        </Card>
      )}
    </div>
  );
}
