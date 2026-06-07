"use client";

import { useState, useCallback } from "react";
import { useProducts, useSemanticSearch } from "@/lib/api/hooks";
import { SearchBar } from "@/components/SearchBar";
import { ProductCard } from "@/components/ProductCard";
import { Pagination } from "@/components/Pagination";
import { SkeletonList } from "@/lib/ui/Skeleton";
import { EmptyState } from "@/lib/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";

export default function ProductsPage(): JSX.Element {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [semanticMode, setSemanticMode] = useState(false);
  const limit = 20;

  const textResults = useProducts(!semanticMode ? query : "", page, limit);
  const semanticResults = useSemanticSearch(semanticMode ? query : "", 20);

  const data = semanticMode ? semanticResults.data : textResults.data;
  const error = semanticMode ? semanticResults.error : textResults.error;
  const isLoading = semanticMode ? semanticResults.isLoading : textResults.isLoading;

  const handleQuery = useCallback((q: string) => {
    setQuery(q);
    setPage(1);
  }, []);

  const items = semanticMode
    ? (data as { results?: unknown[]; total?: number } | undefined)
    : {
        items: (data as { items?: unknown[] } | undefined)?.items ?? [],
        total: (data as { total?: number } | undefined)?.total ?? 0,
      };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-secondary-dark">Buscar</h1>
          <p className="text-sm text-gray-500">
            {semanticMode
              ? "Búsqueda inteligente — describí lo que necesitás"
              : "Encuentra repuestos por nombre o código"}
          </p>
        </div>
        <button
          onClick={() => setSemanticMode(!semanticMode)}
          className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
            semanticMode
              ? "bg-accent text-white"
              : "bg-surface-alt text-text-muted hover:text-text-secondary"
          }`}
        >
          <span className={`h-2.5 w-2.5 rounded-full ${semanticMode ? "bg-white animate-pulse" : "bg-text-muted"}`} />
          {semanticMode ? "Inteligente" : "Texto"}
        </button>
      </div>

      <SearchBar value={query} onChange={handleQuery} />

      {isLoading && <SkeletonList count={5} />}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Error al cargar productos
        </div>
      )}

      {!isLoading && !error && data && (
        <>
          {semanticMode ? (
            /* Semantic search results */
            (data as unknown as { results?: unknown[]; total?: number }).results?.length ? (
              <>
                <p className="text-xs text-gray-400">
                  {(data as unknown as { total: number }).total} resultado{(data as unknown as { total: number }).total !== 1 ? "s" : ""} semántico{(data as unknown as { total: number }).total !== 1 ? "s" : ""}
                </p>
                <div className="space-y-2">
                  {(data as unknown as { results: { codprod: string; nomprod: string; score: number }[] }).results.map((r) => (
                    <div
                      key={r.codprod}
                      className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 hover:bg-surface-alt"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-text-primary">{r.nomprod}</p>
                        <p className="text-xs text-text-muted font-mono">{r.codprod}</p>
                      </div>
                      <Badge variant={r.score > 0.7 ? "success" : r.score > 0.5 ? "warning" : "default"} size="sm">
                        {(r.score * 100).toFixed(0)}%
                      </Badge>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <EmptyState
                icon={
                  <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="11" cy="11" r="8" />
                    <path d="M21 21l-4.35-4.35" />
                  </svg>
                }
                title="Sin resultados"
                description={query ? `No se encontraron productos para "${query}"` : "Describí el repuesto que buscás"}
              />
            )
          ) : (
            /* Traditional search results */
            <>
              {!data || (data as { items: unknown[] }).items.length === 0 ? (
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
              ) : (
                <>
                  <p className="text-xs text-gray-400">
                    {(data as { total: number }).total} resultado{(data as { total: number }).total !== 1 ? "s" : ""}
                  </p>
                  <div className="space-y-2">
                    {(data as { items: { codprod: string; nomprod: string; [key: string]: unknown }[] }).items.map((p) => (
                      <ProductCard key={p.codprod} product={p} />
                    ))}
                  </div>
                  <Pagination
                    page={page}
                    total={(data as { total: number }).total}
                    limit={limit}
                    onPageChange={setPage}
                  />
                </>
              )}
            </>
          )}
        </>
      )}

      {!isLoading && !error && !data && (
        <EmptyState
          icon={
            <svg className="h-12 w-12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="11" cy="11" r="8" />
              <path d="M21 21l-4.35-4.35" />
            </svg>
          }
          title="Buscador de repuestos"
          description={semanticMode ? "Describí el repuesto que necesitás en lenguaje natural" : "Escribí un nombre o código para buscar"}
        />
      )}
    </div>
  );
}
