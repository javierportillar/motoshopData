"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from "recharts";
import { formatMoney } from "@/lib/format/currency";

interface DataPoint {
  label: string;
  valor: number;
}

export interface SalesTrendChartProps {
  data: DataPoint[];
  dataKey?: string;
  height?: number;
  /** Optional second series for year-over-year comparison */
  previousYearData?: DataPoint[];
  previousYearKey?: string;
  previousYearLabel?: string;
  currentYearLabel?: string;
}

export function SalesTrendChart({
  data,
  dataKey = "valor",
  height = 250,
  previousYearData,
  previousYearKey = "valor_anterior",
  previousYearLabel = "Año anterior",
  currentYearLabel = "Año actual",
}: SalesTrendChartProps): JSX.Element {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        Sin datos de tendencia
      </div>
    );
  }

  // Merge previous year data into the chart data for a combined view
  const mergedData: Record<string, unknown>[] | DataPoint[] = previousYearData
    ? data.map((dp, i) => ({
        label: dp.label,
        [dataKey]: dp.valor,
        [previousYearKey]: previousYearData[i]?.valor ?? null,
      }))
    : data;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={mergedData as any} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => formatMoney(v)}
        />
        <Tooltip
          formatter={(value, name) => [
            `$${Number(value ?? 0).toLocaleString("es-CO")}`,
            name === previousYearKey ? previousYearLabel : currentYearLabel,
          ]}
          contentStyle={{
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            fontSize: "12px",
          }}
        />
        {previousYearData && <Legend />}
        {previousYearData && (
          <Line
            type="monotone"
            dataKey={previousYearKey}
            name={previousYearLabel}
            stroke="#999"
            strokeWidth={1.5}
            strokeDasharray="5 5"
            dot={{ r: 2, fill: "#999" }}
            activeDot={{ r: 4 }}
          />
        )}
        <Line
          type="monotone"
          dataKey={previousYearData ? dataKey : dataKey}
          stroke="#7B1818"
          strokeWidth={2}
          dot={{ r: 3, fill: "#7B1818" }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
