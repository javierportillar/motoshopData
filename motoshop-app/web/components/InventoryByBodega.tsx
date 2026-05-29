"use client";

import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";

const BODEGA_COLORS = [
  "#7B1818",
  "#C67B3D",
  "#4B6A8E",
  "#5B8C5A",
  "#8B6F9E",
];

interface BodegaItem {
  cod_bodega: string;
  nom_bodega: string;
  cantidad: number;
  porcentaje: number;
}

interface InventoryByBodegaProps {
  data: BodegaItem[];
  height?: number;
}

export function InventoryByBodega({
  data,
  height = 220,
}: InventoryByBodegaProps): JSX.Element {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        Sin datos de inventario
      </div>
    );
  }

  const chartData = data.map((b) => ({
    name: b.nom_bodega,
    value: b.porcentaje,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={80}
          paddingAngle={2}
          dataKey="value"
        >
          {chartData.map((_, i) => (
            <Cell
              key={i}
              fill={BODEGA_COLORS[i % BODEGA_COLORS.length]}
            />
          ))}
        </Pie>
        <Tooltip
          formatter={(value) => [`${Number(value ?? 0).toFixed(1)}%`, "Stock"]}
          contentStyle={{
            borderRadius: "8px",
            border: "1px solid #e5e7eb",
            fontSize: "12px",
          }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value: string) => (
            <span className="text-xs text-gray-600">{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
