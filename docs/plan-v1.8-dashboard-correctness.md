# Plan V1.8 · Dashboard correctness y lectura gerencial

V1.8 corrige la lectura de negocio de la PWA: ventas parciales de mes, proyección
mensual, comparación justa contra períodos equivalentes, e inventario accionable.
No agrega infraestructura paga. No usa LLM para inventar números: usa modelos
estadísticos reproducibles y guarda errores para recalibrar.

## Evidencia de auditoría — 2026-06-08

| Hallazgo | Evidencia | Decisión |
|----------|-----------|----------|
| La API está fresca, pero ventas llegan hasta 2026-06-06 | R2 DuckDB: `MAX(business_date)=2026-06-06` en gold, silver facturas y silver detalle | No es bug de UI. Dev W debe validar MySQL Windows si hubo ventas 2026-06-07/08 |
| El `-77.7%` es engañoso | Junio 1–6 = `$5,733,700`; mayo 1–6 = `$5,340,800`; delta justo = `+7.4%` | Reemplazar comparación mes parcial vs mes completo |
| Gráficas muestran meses futuros en cero | Front rellena enero–diciembre con `0` cuando no hay datos | Usar `null`/no render para meses futuros; proyección dashed solo para mes actual/siguiente |
| Inventario vs dormidos no cuadra | Inventario usa `motoshop_gold_mart_inventario_actual`: 4,024 unidades. Dormidos usa `dim_producto.existencia`: 15,378 unidades dormidas | Dormidos debe usar la misma fuente de stock que inventario |
| Log de pipeline confunde | Log dice `hasta 9876-01-01` por una venta inválida futura en `bronze_facventas`; silver la filtra | Loggear fecha máxima válida por tabla, no máximo bruto |

## Objetivo

Gerente debe poder responder en menos de 30 segundos:

1. ¿Cuánto vendimos acumulado este mes?
2. ¿Vamos mejor o peor que un período comparable?
3. ¿Cuánto proyectamos vender este mes y el próximo?
4. ¿Qué tan confiable fue la proyección anterior?
5. ¿Qué inventario tengo, dónde está, cuánto vale y qué está inmovilizado?

## Principios

- **Comparar parcial con parcial.** Nunca comparar junio 1–6 contra mayo completo.
- **No mostrar futuro como cero.** Cero significa “vendimos cero”; futuro significa “sin dato todavía”.
- **Forecast reproducible > LLM mágico.** El modelo puede usar IA/ML si suma, pero debe ser auditable.
- **Una sola verdad de stock.** Inventario, dormidos, alertas y compras deben leer la misma fuente.
- **Datos con fecha visible.** Cada vista debe mostrar `max_sales_date` o `snapshot_date`.

## Sub-bloque A · Data truth y endpoints base

**Owner sugerido:** Dev D / Backend.

### A1. Endpoint de salud de datos de negocio

Crear:

```text
GET /api/admin/data/status
```

Respuesta esperada:

```ts
type DataStatus = {
  sales_max_date: string;          // 2026-06-06
  sales_days_lag: number;          // current_date - sales_max_date
  inventory_snapshot_date: string;
  invalid_future_sales_rows: number;
  latest_pipeline_run_status: "success" | "failed" | "running";
  duckdb_freshness_utc: string;
};
```

DoD:

- Si `sales_days_lag > 1`, UI muestra warning “Ventas disponibles hasta X”.
- Dev W valida en MySQL Windows si `MAX(fecfven)` válido coincide con DuckDB.
- El pipeline log deja de decir “hasta 9876”; separa fecha por tabla y marca inválidos.

### A2. Corregir fuente de stock en dormidos

Cambiar `mart_productos_dormidos` para que `stock_actual` venga de
`motoshop_gold_mart_inventario_actual` o del mismo cálculo latest inventory,
no de `motoshop_silver_dim_producto.existencia`.

DoD:

- `SUM(dormidos.stock_actual) <= SUM(inventario.cantidad_actual)` salvo explicación documentada.
- Test SQL de invariante.
- Dormidos sin venta pero sin stock no aparecen como “inventario inmovilizado”; pueden aparecer como “catálogo sin movimiento” si se necesita.

## Sub-bloque B · Ventas: comparaciones justas y proyección

**Owner sugerido:** Dev D / Backend + Dev F / Front.

### B1. Sales summary v2

Crear o extender:

```text
GET /api/metrics/sales-summary-v2
```

Respuesta:

```ts
type SalesSummaryV2 = {
  business_month: string;
  max_sales_date: string;
  current_month_accumulated: number;
  current_month_days_with_sales: number;
  previous_month_same_window: {
    from: string;
    to: string;
    amount: number;
    delta_pct: number | null;
  };
  same_month_previous_years: Array<{
    year: number;
    same_day_window_amount: number;
    full_month_amount: number;
    delta_same_window_pct: number | null;
  }>;
  ticket_promedio: number;
  num_facturas: number;
};
```

Regla de comparación:

- Mes actual se corta en `max_sales_date`.
- Mes anterior se compara desde día 1 hasta el día equivalente.
- Si el mes anterior tiene menos días, usar su último día.
- Si el mes actual tiene menos días procesados, no inventar días.

### B2. Evolución diaria mensual

Crear:

```text
GET /api/metrics/sales-daily-month?month=YYYY-MM
```

Respuesta:

```ts
type DailyMonthPoint = {
  date: string;
  day: number;
  sales: number;
  invoices: number;
  avg_ticket: number;
  accumulated: number;
};
```

Front:

- Gráfico barras = ventas diarias.
- Línea = acumulado mensual.
- Tabla debajo: día, ventas, facturas, ticket, top SKU opcional.

### B3. Proyección mes actual y próximo

Crear:

```text
GET /api/metrics/sales-forecast-monthly?horizon=2
```

Modelo inicial $0:

1. Run-rate del mes actual: acumulado / días con venta.
2. Estacionalidad: mismo mes año anterior si existe.
3. Tendencia: últimos 3 meses completos.
4. Ajuste de sesgo: tabla `app_forecast_errors` con error real vs forecast anterior.

Salida:

```ts
type MonthlyForecast = {
  month: string;
  observed_amount: number | null;
  projected_amount: number;
  lower_bound: number;
  upper_bound: number;
  confidence: "low" | "medium" | "high";
  model_version: string;
  drivers: string[];
};
```

Importante:

- No usar LLM para calcular el número. Un LLM puede explicar el forecast, pero no debe ser el modelo.
- “Aprender” significa recalibrar sesgo/error mensual con datos guardados, no que el modelo “recuerde” mágicamente.

### B4. Evaluación mensual automática

Al cerrar cada mes:

- Guardar forecast emitido.
- Comparar contra venta real.
- Calcular MAPE/WAPE y bias.
- Ajustar factor de corrección para el próximo forecast.

Tabla sugerida:

```sql
app_sales_forecast_evaluations(
  id,
  forecast_month,
  model_version,
  predicted_amount,
  actual_amount,
  error_pct,
  bias_correction,
  created_at
)
```

## Sub-bloque C · Front Inicio

**Owner sugerido:** Dev F.

Cambios:

- Card “Ventas del mes” muestra solo acumulado.
- Quitar delta rojo/verde del card principal.
- Subtítulo: `Acumulado hasta 2026-06-06`.
- Link “Ver detalle diario”.
- Gráfico año actual vs anterior:
  - año actual solo hasta mes vigente;
  - no dibujar julio–diciembre en cero;
  - mes actual y siguiente pueden aparecer como proyección con línea punteada.

DoD:

- Junio no muestra caída artificial por comparar contra mayo completo.
- Meses futuros no aparecen como cero.

## Sub-bloque D · Front Ventas

**Owner sugerido:** Dev F.

### Histórica

- Añadir línea de tendencia/proyección.
- Mostrar mes actual proyectado y próximo mes proyectado.
- Tabla: mes, real, forecast, error si ya cerró, facturas, ticket promedio.

### Mensual

- Reemplazar delta actual por:
  - “vs mes anterior mismo corte”
  - “vs junio 2025 mismo corte”
  - “proyección cierre de mes”
- Añadir gráfico ventas diarias del mes:
  - barras diarias;
  - línea acumulada;
  - tooltip con facturas/ticket.
- Añadir tabla diaria.
- Añadir histórico año vigente vs año anterior:
  - año vigente real hasta mes actual;
  - forecast dashed para mes actual y siguiente;
  - año anterior completo como referencia.

## Sub-bloque E · Inventario accionable

**Owner sugerido:** Dev D + Dev F.

### Backend

Crear endpoints:

```text
GET /api/metrics/inventory-detail?page=&page_size=&sort=&q=&bodega=
GET /api/metrics/inventory-movements-summary
GET /api/metrics/inventory-discrepancies
```

Datos mínimos por SKU:

```ts
type InventoryItem = {
  cod_producto: string;
  nom_producto: string;
  cod_bodega: string;
  nom_bodega: string;
  stock_actual: number;
  costo_unitario: number | null;
  valor_inventario: number;
  ultima_venta: string | null;
  ultima_compra: string | null;
  dias_sin_venta: number | null;
  abc: "A" | "B" | "C" | null;
};
```

### Front

Inventario debe tener:

- KPIs: SKUs con stock, unidades, valor, stock dormido real, stock sin movimiento.
- Gráfico por bodega si hay más de una; si solo hay una, no desperdiciar pantalla con “100%”.
- Tabla de inventario con búsqueda, orden y paginación.
- Top 20 por valor inmovilizado.
- Top 20 por unidades.
- Tabla de discrepancias:
  - productos en `dim_producto.existencia` pero no en inventory actual;
  - productos dormidos con stock diferente al inventario.

DoD:

- Usuario entiende por qué stock total no coincide con conteo de dormidos.
- Si no coincide, la pantalla lo explica con una card de alerta, no lo esconde.

## Sub-bloque F · Validación y pruebas

### SQL invariants

- `MAX(gold.sales.business_date) = MAX(silver.sales_detail.business_date)` para ventas válidas.
- `invalid_future_sales_rows` reportado explícitamente.
- `SUM(dormidos.stock_actual) <= SUM(inventory.stock_actual)` cuando dormidos representa inventario inmovilizado.
- Mes actual parcial no se compara contra mes completo.

### API tests

- `sales-summary-v2` con fecha mockeada en mitad de mes.
- `sales-daily-month` retorna días reales, no días futuros en cero.
- `sales-forecast-monthly` retorna mes actual + siguiente.
- `inventory-detail` pagina y ordena.

### Front smoke

- Inicio no muestra delta rojo del mes parcial.
- Tendencia anual no dibuja meses futuros en cero.
- Ventas mensual muestra gráfico diario barras + línea acumulada.
- Ventas histórica muestra forecast y tabla real vs forecast.
- Inventario muestra tabla y top inmovilizado.

## Handoffs

### Dev D — Backend/data

Implementar Sub-bloques A, B backend, E backend y F backend tests. No tocar UI.

### Dev F — Front

Implementar Sub-bloques C, D, E front y smoke tests. No tocar pipeline ni Windows.

### Dev W — Operación Windows

Validar con SQL directo en Windows:

```sql
SELECT MAX(fecfven)
FROM facventas
WHERE fecfven >= '2020-01-01'
  AND fecfven <= CURRENT_DATE;
```

Confirmar si existen ventas 2026-06-07/08. Si existen en MySQL pero no en DuckDB,
el bug es de ingesta. Si no existen, la app está correcta al mostrar ventas hasta
2026-06-06 y debe decirlo claramente.

## Criterio de cierre V1.8

- Inicio, Ventas e Inventario pasan smoke visual en producción.
- `sales_max_date` visible en UI.
- No hay meses futuros en cero.
- Comparaciones parciales son justas.
- Forecast mensual tiene evaluación guardada.
- Inventario y dormidos usan una fuente de stock coherente.
- Revisor firma GO con curl + SQL + screenshots.
