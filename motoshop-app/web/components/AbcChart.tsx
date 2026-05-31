"use client";

import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
} from "recharts";

const COLORS: Record<string, string> = {
  A: "#7B1818", // burgundy
  B: "#C67B3D", // amber
  C: "#9ca3af", // gray
};

interface AbcBucket {
  categoria: string;
  num_skus: number;
  valor_total: number;
  porcentaje_ingreso: number;
}

interface AbcChartProps {
  bucketA: AbcBucket;
  bucketB: AbcBucket;
  bucketC: AbcBucket;
  height?: number;
  explanations?: Record<string, string>;
}

export function AbcChart({
  bucketA,
  bucketB,
  bucketC,
  height = 220,
  explanations,
}: AbcChartProps): JSX.Element {
  const desc: Record<string, string> = explanations ?? {};

  const data = [
    {
      name: `A (${bucketA.num_skus} SKUs)`,
      value: bucketA.porcentaje_ingreso,
      color: COLORS.A,
      desc: desc.A ?? "",
    },
    {
      name: `B (${bucketB.num_skus} SKUs)`,
      value: bucketB.porcentaje_ingreso,
      color: COLORS.B,
      desc: desc.B ?? "",
    },
    {
      name: `C (${bucketC.num_skus} SKUs)`,
      value: bucketC.porcentaje_ingreso,
      color: COLORS.C,
      desc: desc.C ?? "",
    },
  ];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={80}
          paddingAngle={3}
          dataKey="value"
        >
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          formatter={(value, _name, props) => [
            <span key="val" className="text-xs">
              {Number(value ?? 0).toFixed(1)}%
              {props.payload?.desc ? (
                <>
                  <br />
                  <span className="text-text-muted italic">{props.payload.desc}</span>
                </>
              ) : null}
            </span>,
            "% Ingresos",
          ]}
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
