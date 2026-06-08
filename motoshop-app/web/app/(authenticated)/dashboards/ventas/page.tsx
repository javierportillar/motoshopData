"use client";

import Link from "next/link";
import { useSalesSummaryV2 } from "@/lib/api/hooks";
import { formatMoney } from "@/lib/format/currency";
import { Card } from "@/components/ui/Card";
import { Stat } from "@/components/ui/Stat";

export default function VentasPage(): JSX.Element {
  const sales = useSalesSummaryV2();
  const d = sales.data;

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-accent hover:underline">← Volver a inicio</Link>
      <div>
        <h1 className="text-xl font-bold text-text-primary">Ventas</h1>
        <p className="text-sm text-text-muted">{d?.max_sales_date ? `Datos hasta ${d.max_sales_date}` : "Cargando..."}</p>
      </div>
      {d && (
        <div className="grid grid-cols-2 gap-3">
          <Card><Stat label="Ventas acumuladas" value={formatMoney(d.current_month_accumulated)} subtitle={`${d.current_month_days_with_sales} días`} /></Card>
          <Card><Stat label="Facturas" value={d.num_facturas.toLocaleString("es-CO")} subtitle="este mes" /></Card>
          <Card><Stat label="Ticket promedio" value={formatMoney(d.ticket_promedio)} subtitle="por factura" /></Card>
          <Card><Stat label="vs mes anterior" value={`${d.previous_month_same_window.delta_pct > 0 ? "+" : ""}${d.previous_month_same_window.delta_pct}%`} /></Card>
        </div>
      )}
    </div>
  );
}
