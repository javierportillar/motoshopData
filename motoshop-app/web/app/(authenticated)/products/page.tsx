"use client";

import { useState } from "react";
import { useProducts } from "@/lib/api/hooks";
import { SearchBar } from "@/components/SearchBar";
import { ProductCard } from "@/components/ProductCard";
import { Pagination } from "@/components/Pagination";
import { SkeletonList } from "@/lib/ui/Skeleton";
import { EmptyState } from "@/lib/ui/EmptyState";

export default function ProductsPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const limit = 20;

  const { data, error, isLoading } = useProducts(query, page, limit);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-secondary-dark">Buscar</h1>
        <p className="text-sm text-gray-500">Encuentra repuestos por nombre o código</p>
      </div>

      <SearchBar value={query} onChange={(q) => { setQuery(q); setPage(1); }} />

      {isLoading && <SkeletonList count={5} />}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Error al cargar productos
        </div>
      )}

      {!isLoading && !error && data && data.items.length === 0 && (
        <EmptyState
          icon={
            <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          }
          title="Sin resultados"
          description={query ? `No se encontraron productos para "${query}"` : "Escribe algo para buscar"}
        />
      )}

      {!isLoading && !error && data && data.items.length > 0 && (
        <>
          <p className="text-xs text-gray-400">
            {data.total} resultado{data.total !== 1 ? "s" : ""}
          </p>
          <div className="space-y-2">
            {data.items.map((p) => (
              <ProductCard key={p.codprod} product={p} />
            ))}
          </div>
          <Pagination
            page={page}
            total={data.total}
            limit={limit}
            onPageChange={setPage}
          />
        </>
      )}
    </div>
  );
}
