# Stat · KPI individual

- **File:** `motoshop-app/web/components/ui/Stat.tsx`
- **Tokens:** `text-primary`, `text-muted`, `bg-primary/10`, `delta-positive`, `delta-negative`
- **Fase:** F7-B (Design System)

## API

```ts
interface StatProps {
  label: string;
  value: string;
  subtitle?: string;
  delta?: number | null;
  deltaLabel?: string;
  icon?: ReactNode;
  className?: string;
}
```

## Estados

### 1. Básico (label + valor)

```tsx
<Stat label="Ventas del mes" value="$12.4M" />
```

### 2. Con delta positivo

```tsx
<Stat
  label="Ticket promedio"
  value="$847"
  delta={5.2}
  deltaLabel="vs mes anterior"
/>
```

Renderiza `↑ 5.2%` en verde (`delta-positive`).

### 3. Con delta negativo

```tsx
<Stat
  label="Rotación promedio"
  value="3.2 días"
  delta={-1.8}
  deltaLabel="vs mes anterior"
/>
```

Renderiza `↓ 1.8%` en rojo (`delta-negative`).

### 4. Delta neutral (0%)

```tsx
<Stat label="Stock actual" value="1,247" delta={0} />
```

Renderiza `→ 0%` en muted.

### 5. Con icono

```tsx
<Stat
  label="Productos activos"
  value="4,392"
  icon={<PackageIcon />}
/>
```

Icono en caja `bg-primary/10 text-primary`.

### 6. En Card (composición)

```tsx
<Card>
  <Stat label="Ventas" value="$12.4M" delta={5.2} deltaLabel="vs mes ant" />
</Card>
```

## Comparación con KpiCard

`Stat` es más liviano que `KpiCard` — no incluye el wrapper Card ni el Link. Pensado para composición: el consumidor decide si lo envuelve en Card, si lo linkea, etc.

`KpiCard` se mantiene en `components/KpiCard.tsx` para compatibilidad con páginas existentes. Migración gradual a `Stat` decidida por Dev T2.
