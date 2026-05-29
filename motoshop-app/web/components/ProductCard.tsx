import { StockBadge } from "@/lib/ui/Badge";

interface Product {
  codprod: string;
  nomprod: string;
  codbar?: string;
  precio?: number;
  stock?: number;
}

export function ProductCard({ product }: { product: Product }): JSX.Element {
  return (
    <div className="card flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-semibold text-secondary-dark">
          {product.nomprod}
        </h3>
        <p className="mt-0.5 text-xs text-gray-500">
          {product.codprod}
          {product.codbar && (
            <span className="ml-2 text-gray-400">| {product.codbar}</span>
          )}
        </p>
        {typeof product.precio === "number" && product.precio > 0 && (
          <p className="mt-1 text-sm font-semibold text-primary">
            ${product.precio.toLocaleString("es-CO")}
          </p>
        )}
      </div>
      {typeof product.stock === "number" && (
        <StockBadge qty={product.stock} />
      )}
    </div>
  );
}
