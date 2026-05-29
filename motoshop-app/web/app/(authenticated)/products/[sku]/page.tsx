"use client";

import { useProducts, useStock } from "@/lib/api/hooks";
import { StockBadge } from "@/lib/ui/Badge";
import { Card } from "@/lib/ui/Card";
import { Skeleton } from "@/lib/ui/Skeleton";
import { EmptyState } from "@/lib/ui/EmptyState";
import { Button } from "@/lib/ui/Button";
import { SyncStatus } from "@/components/SyncStatus";
import { useParams, useRouter } from "next/navigation";

export default function SkuPage(): JSX.Element {
  const { sku } = useParams<{ sku: string }>();
  const router = useRouter();
  const { data: stock, isLoading: stockLoading, mutate: mutateStock } = useStock(sku);
  const { data: products, isLoading: productsLoading } = useProducts(sku, 1, 1);

  const product = products?.items?.[0];
  const stockLoadingState = stockLoading || productsLoading;

  return (
    <div className="space-y-4">
      {/* Back button */}
      <button
        onClick={() => router.back()}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-secondary-dark"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        Volver
      </button>

      {stockLoadingState && (
        <div className="space-y-4">
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {!stockLoadingState && !stock && (
        <EmptyState
          icon={
            <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 8v4M12 16h.01" />
            </svg>
          }
          title="Producto no encontrado"
          description={`No se encontró stock para el SKU ${sku}`}
        />
      )}

      {!stockLoadingState && stock && (
        <>
          <div>
            <h1 className="text-xl font-bold text-secondary-dark">
              {product?.nomprod ?? sku}
            </h1>
            <p className="text-sm text-gray-500">
              {stock.codprod}
              {product?.codbar && (
                <span className="ml-2 text-gray-400">| {product.codbar}</span>
              )}
            </p>
          </div>

          {/* Total stock */}
          <Card>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Stock total</p>
                <p className="text-3xl font-bold text-primary">{stock.total}</p>
              </div>
              <Button
                onClick={() => mutateStock()}
                variant="ghost"
                size="sm"
              >
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 4v6h-6M1 20v-6h6" />
                  <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
                </svg>
                Actualizar
              </Button>
            </div>
          </Card>

          {/* Stock by bodega */}
          <Card header={<h2 className="font-semibold text-secondary-dark">Por bodega</h2>}>
            {stock.by_bodega && stock.by_bodega.length > 0 ? (
              <div className="space-y-2">
                {stock.by_bodega.map((b) => (
                  <div
                    key={b.codbod}
                    className="flex items-center justify-between rounded-lg border border-gray-100 p-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-secondary-dark">
                        {b.nom_bodega ?? b.codbod}
                      </p>
                      <p className="text-xs text-gray-400">{b.codbod}</p>
                    </div>
                    <StockBadge qty={b.stock} />
                  </div>
                ))}
              </div>
            ) : (
              <p className="py-4 text-center text-sm text-gray-400">
                Sin datos de bodegas para este SKU
              </p>
            )}
          </Card>

          <SyncStatus />
        </>
      )}
    </div>
  );
}
