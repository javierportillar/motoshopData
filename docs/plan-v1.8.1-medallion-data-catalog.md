# Plan V1.8.1 · Medallion Data Catalog

Agregar una vista admin tipo Databricks para inspeccionar el estado de las capas
bronze, silver y gold dentro del DuckDB productivo, sin ejecutar SQL libre y sin
agregar costo de infraestructura.

## Estado actual verificado — 2026-06-08

| Área | Estado |
|------|--------|
| Front Inicio/Ventas | Smoke prod OK preliminar: Inicio ya no muestra Jul-Dic en cero, Diaria no muestra NaN, Forecast muestra junio/julio proyectados. |
| Inventario | Sigue pendiente A2: dormidos debe unificar fuente de stock con inventario. |
| Pipeline observability | Existe `/admin/pipeline` con corridas y pasos. No muestra catálogo de tablas por capa. |
| DuckDB local | `out/motoshop_gold.duckdb` está viejo vs prod; sirve para estructura, no para verdad de negocio. |
| Medallion | El pipeline construye bronze desde MySQL, transforma silver y genera gold. La UI todavía no permite ver tablas/capas. |

## Objetivo

Crear una vista `/admin/data-catalog` para responder rápido:

1. ¿Qué tablas existen en bronze, silver y gold?
2. ¿Cuántas filas tiene cada tabla?
3. ¿Cuál es la fecha máxima de negocio o snapshot por tabla?
4. ¿Qué columnas tiene cada tabla?
5. ¿Qué muestra una muestra segura de datos?
6. ¿Qué cambió en la última corrida del pipeline?

## Principios

- Read-only. No SQL libre desde el frontend.
- Admin-only para muestras de datos.
- Gerente puede ver resumen si hace falta, pero no raw bronze con NIT/clientes.
- Bronze/silver/gold se detectan por prefijo de tabla en DuckDB.
- Si una capa no existe en el DuckDB actual, la UI debe mostrarlo como hallazgo, no romper.

## Backend

### Endpoint 1 · Catálogo general

```text
GET /api/admin/data/catalog
```

Respuesta sugerida:

```ts
type DataCatalogResponse = {
  duckdb_freshness_utc: string;
  layers: Array<{
    layer: "bronze" | "silver" | "gold" | "app" | "other";
    table_count: number;
    total_rows: number;
    max_business_date: string | null;
    warnings: string[];
  }>;
  tables: Array<{
    table_name: string;
    layer: string;
    row_count: number;
    column_count: number;
    date_column: string | null;
    max_date: string | null;
    status: "ok" | "empty" | "stale" | "missing";
  }>;
};
```

### Endpoint 2 · Detalle de tabla

```text
GET /api/admin/data/catalog/{table_name}?limit=50
```

Respuesta sugerida:

```ts
type DataTableDetail = {
  table_name: string;
  layer: string;
  row_count: number;
  columns: Array<{
    name: string;
    type: string;
    nullable: boolean;
  }>;
  sample_rows: Record<string, unknown>[];
  quality: {
    null_counts: Record<string, number>;
    max_date: string | null;
    warnings: string[];
  };
};
```

Seguridad:

- Validar `table_name` contra `information_schema.tables`; nunca interpolar tablas no existentes.
- `limit` máximo 100.
- Redactar o bloquear columnas sensibles en raw bronze si el rol no es `admin`.

### Endpoint 3 · Lineage simple

```text
GET /api/admin/data/lineage
```

Ejemplo:

```ts
type DataLineage = {
  edges: Array<{
    from: string;
    to: string;
    transform: "silver" | "gold";
  }>;
};
```

## Pipeline metadata opcional

Para ver “qué pasó cuando corrió el script”, agregar tabla en `pipeline_runs.duckdb`:

```sql
app_pipeline_table_stats(
  id,
  run_id,
  layer,
  table_name,
  row_count,
  max_date,
  status,
  captured_at
)
```

El pipeline debe capturar stats después de bronze, después de silver y después de gold.
Esto permite comparar corrida actual vs corrida anterior.

## Frontend

Crear:

```text
/admin/data-catalog
```

Secciones:

1. Cards por capa: Bronze, Silver, Gold, App.
2. Tabla buscable de tablas: capa, filas, columnas, fecha máxima, estado.
3. Modal/drawer de detalle: columnas, muestra segura, warnings.
4. Mini-lineage: Bronze → Silver → Gold.
5. Link desde `/admin/pipeline` a “Ver tablas generadas”.

UX:

- Bronze en color cobre.
- Silver en gris metálico.
- Gold en dorado.
- Warnings visibles: tabla vacía, fecha vieja, capa ausente, filas futuras inválidas.

## Dueños sugeridos

| Bloque | Owner | Motivo |
|--------|-------|--------|
| Backend endpoints | Dev D o quien toque API/DuckDB desde Mac | No requiere Windows. Lee DuckDB productivo en Render. |
| Front `/admin/data-catalog` | Dev F | Vista admin, tablas, drawer, filtros. |
| Captura por corrida en script | Dev W solo si se decide persistir `app_pipeline_table_stats` desde Windows | Requiere que el Scheduled Task ejecute el script actualizado. |

## DoD

- `GET /api/admin/data/catalog` responde HTTP 200 en prod.
- Se ven tablas agrupadas por bronze/silver/gold.
- Se muestra row_count y max_date por tabla.
- `/admin/data-catalog` carga autenticado como admin.
- No hay SQL libre en UI.
- No se muestran meses/fechas futuras como datos válidos.
- Screenshot de overview, detalle de tabla y lineage.
- Typecheck + build pasan.
