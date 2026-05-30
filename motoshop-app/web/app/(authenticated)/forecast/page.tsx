"use client";

import { useState, useMemo } from "react";
import { Card } from "@/lib/ui/Card";
import { useForecast } from "@/lib/api/hooks";
import { StaleDataBanner } from "@/components/StaleDataBanner";
import Link from "next/link";
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

const HORIZON_OPTIONS = [7, 14, 30] as const;

const MOCK_SUGGESTIONS = [
  { sku: "MOTS1297", label: "ACEITE 20W50 MOTUL 1L" },
  { sku: "MOTS0412", label: "FILTRO ACEITE YAMAHA YBR125" },
  { sku: "MOTS0834", label: "PASTILLAS FRENO DELANTERAS" },
];

function formatNumber(v: number): string {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
  return v.toFixed(1);
}

export default function ForecastPage(): JSX.Element {
  const [sku, setSku] = useState("");
  const [selectedSku, setSelectedSku] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<number>(7);
  const [showSuggestions, setShowSuggestions] = useState(false);

  const { data, error, isLoading } = useForecast(selectedSku, horizon);

  const suggestions = useMemo(() => {
    if (!sku.trim()) return [];
    const q = sku.trim().toUpperCase();
    return MOCK_SUGGESTIONS.filter(
      (s) => s.sku.includes(q) || s.label.toUpperCase().includes(q),
    );
  }, [sku]);

  const chartData = useMemo(() => {
    if (!data?.forecast) return [];
    return data.forecast.map((f) => ({
      date: f.forecast_date.slice(5), // MM-DD
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
      <Link href="/dashboards" className="text-sm text-primary hover:underline">
        ← Volver a Dashboards
      </Link>

      <h1 className="text-xl font-bold text-secondary-dark">Predicciones</h1>
      <p className="text-sm text-gray-500">
        Demanda estimada por SKU — Prophet / LightGBM
      </p>

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
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg">
                {suggestions.map((s) => (
                  <button
                    key={s.sku}
                    onMouseDown={() => handleSelect(s.sku)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-gray-50"
                  >
                    <span className="font-mono text-xs font-medium text-primary">
                      {s.sku}
                    </span>
                    <span className="truncate text-gray-600">{s.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={handleSearch}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark"
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
                  ? "bg-primary text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
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
          <div className="h-5 w-48 animate-pulse rounded bg-gray-200" />
          <div className="h-60 animate-pulse rounded-xl bg-gray-100" />
        </div>
      )}

      {/* Error */}
      {error && (
        <Card>
          <p className="text-center text-sm text-red-500">
            {error.message?.includes("404")
              ? `SKU "${selectedSku}" no encontrado`
              : "Error al cargar predicciones"}
          </p>
        </Card>
      )}

      {/* Forecast chart */}
      {data && chartData.length > 0 && (
        <>
          <Card
            header={
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-secondary-dark">
                  {data.sku}
                </h2>
                {data.metrics && (
                  <span className="text-xs text-gray-400">
                    MAPE: {data.metrics.mape?.toFixed(1)}% · v{data.metrics.model_version}
                  </span>
                )}
              </div>
            }
          >
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#9ca3af" />
                <YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" tickFormatter={formatNumber} />
                <Tooltip
                  formatter={(value) => [formatNumber(Number(value ?? 0)), "unidades"]}
                  contentStyle={{
                    borderRadius: "8px",
                    border: "1px solid #e5e7eb",
                    fontSize: "12px",
                  }}
                />
                {/* Confidence interval */}
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="#3b82f6"
                  fillOpacity={0.1}
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="#ffffff"
                  fillOpacity={0.3}
                />
                {/* Predicted line */}
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "#3b82f6" }}
                  activeDot={{ r: 5 }}
                />
              </AreaChart>
            </ResponsiveContainer>
            <div className="mt-2 flex items-center gap-4 text-xs text-gray-400">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-4 rounded bg-blue-500" /> Predicción
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-4 rounded bg-blue-100" /> IC 80%
              </span>
            </div>
          </Card>

          {/* Tabla de valores */}
          <Card header={<h2 className="font-semibold text-secondary-dark">Valores</h2>}>
            <div className="space-y-1">
              {data.forecast.map((f, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2"
                >
                  <span className="text-xs text-gray-500">{f.forecast_date}</span>
                  <div className="text-right">
                    <span className="text-sm font-medium text-secondary-dark">
                      {f.predicted_qty.toFixed(1)} u.
                    </span>
                    {f.confidence_lower && (
                      <span className="ml-2 text-xs text-gray-400">
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
          <p className="py-8 text-center text-sm text-gray-400">
            Buscá un SKU para ver sus predicciones de demanda
          </p>
        </Card>
      )}
    </div>
  );
}
