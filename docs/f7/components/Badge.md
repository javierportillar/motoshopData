# Badge · Etiqueta de estado

- **File:** `motoshop-app/web/components/ui/Badge.tsx`
- **Tokens:** `success`, `warning`, `error`, `info`, `surface-alt`, `text-secondary`
- **Fase:** F7-B (Design System)

## API

```ts
type BadgeVariant = "success" | "warning" | "error" | "info" | "default";
type BadgeSize = "sm" | "md";

interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  children: ReactNode;
  className?: string;
}
```

## Variantes

### 1. Estados semánticos

```tsx
<Badge variant="success">Confirmado</Badge>   {/* verde */}
<Badge variant="warning">Pendiente</Badge>    {/* ámbar */}
<Badge variant="error">Cancelado</Badge>       {/* rojo oscuro */}
<Badge variant="info">Nuevo</Badge>             {/* azul */}
<Badge variant="default">Archivado</Badge>      {/* neutro */}
```

### 2. Tamaños

```tsx
<Badge size="sm">Compacto</Badge>  {/* tablas densas */}
<Badge size="md">Normal</Badge>    {/* default */}
```

### 3. Compuestos incluidos

```tsx
<StockBadge qty={0} />       // "Sin stock" (error)
<StockBadge qty={3} />       // "3 uds" (warning)
<StockBadge qty={15} />      // "15 uds" (success)

<DeltaBadge value={5.2} />    // ↑ 5.2% (success)
<DeltaBadge value={-1.8} />   // ↓ 1.8% (error)
<DeltaBadge value={0} />      // → 0% (default)

<AlertBadge severity="critical" /> // "Crítica" (error)
<AlertBadge severity="warning" />  // "Atención" (warning)
<AlertBadge severity="info" />     // "Info" (info)
```

## Diferencia con lib/ui/Badge

| Feature | lib/ui/Badge (legacy) | components/ui/Badge |
|---------|----------------------|---------------------|
| Colores | `bg-green-100 text-green-800` (Tailwind) | `bg-success/10 text-success` (tokens MotoShop) |
| Variante info | No | Sí (`#0284C7`) |
| Tamaños | Solo md | sm + md |
| Compuestos | Solo StockBadge | StockBadge + DeltaBadge + AlertBadge |
| success color | `#15803D` (green-700) | `#16A34A` (MotoShop success) |
| error color | `#B91C1C` (red-700) | `#B91C1C` (MotoShop error) |
