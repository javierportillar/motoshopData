# Card · Componente contenedor

- **File:** `motoshop-app/web/components/ui/Card.tsx`
- **Tokens:** `bg-surface`, `bg-surface-dark`, `border-border`, `shadow-sm`
- **Fase:** F7-B (Design System)

## API

```ts
interface CardProps {
  children: ReactNode;
  header?: ReactNode;
  footer?: ReactNode;
  variant?: "default" | "dark" | "bordered";
  hover?: boolean;
  className?: string;
}
```

## Variantes

### 1. Default (surface blanco + shadow)

```tsx
<Card header="Título">
  Contenido de la card
</Card>
```

Fondo `#FFFFFF`, borde `#D4D4D4`, shadow-sm, hover levanta shadow.

### 2. Dark (surface oscuro)

```tsx
<Card variant="dark">
  <Logo />
</Card>
```

Fondo `#171717`, texto `text-inverse`. Para headers, sidebars, wraps de logo.

### 3. Bordered (solo borde, sin shadow)

```tsx
<Card variant="bordered" hover={false}>
  <Input label="Buscar" />
</Card>
```

Borde `#A3A3A3` fuerte, sin shadow. Para grupos de inputs, listas densas.

### 4. Con header + footer

```tsx
<Card
  header={<h3 className="font-semibold">Ventas</h3>}
  footer={<span className="text-text-muted">Actualizado hace 2h</span>}
>
  <Stat label="Total" value="$12.4M" />
</Card>
```

## Comparación con lib/ui/Card

| Feature | lib/ui/Card (legacy) | components/ui/Card |
|---------|---------------------|-------------------|
| Border | `border-gray-200` (fijo) | `border-border` (token) |
| Variante dark | No | `variant="dark"` |
| Variante bordered | No | `variant="bordered"` |
| Header/footer | `border-gray-100` | `border-border` |
| Hover | Siempre activo | `hover` prop |
