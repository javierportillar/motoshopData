# Table · Tabla de datos genérica

- **File:** `motoshop-app/web/components/ui/Table.tsx`
- **Tokens:** `bg-surface`, `bg-surface-alt`, `text-primary`, `text-secondary`, `text-muted`, `border-border`
- **Fase:** F7-B (Design System)

## API

```ts
interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyFn: (row: T, index: number) => string;
  striped?: boolean;
  hover?: boolean;
  emptyMessage?: string;
  className?: string;
}

interface Column<T> {
  header: string;
  cell: (row: T, index: number) => ReactNode;
  align?: "left" | "center" | "right";
  className?: string;
}
```

## Estados

### 1. Tabla con datos

```tsx
<Table
  columns={[
    { header: "Producto", cell: (p) => p.nombre },
    { header: "Stock", cell: (p) => p.stock, align: "right" },
    { header: "Estado", cell: (p) => <StockBadge qty={p.stock} /> },
  ]}
  data={productos}
  keyFn={(p) => p.codigo}
/>
```

### 2. Con striped rows

```tsx
<Table
  columns={cols}
  data={productos}
  keyFn={(p) => p.codigo}
  striped
/>
```

Filas alternas en `bg-surface-alt/50`.

### 3. Sin datos (empty state)

```tsx
<Table
  columns={cols}
  data={[]}
  keyFn={(p) => p.id}
  emptyMessage="No se encontraron productos"
/>
```

Muestra mensaje centrado en card con `text-muted`.

### 4. Sin hover

```tsx
<Table columns={cols} data={rows} keyFn={...} hover={false} />
```

Sin highlight al pasar el mouse. Útil para tablas de solo lectura estáticas.
