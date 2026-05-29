import useSWR from "swr";
import { apiFetchJson } from "./client";
import { getCached, setCache } from "@/lib/offline/cache";

interface Product {
  codprod: string;
  nomprod: string;
  codbar?: string;
  precio?: number;
  [key: string]: unknown;
}

interface ProductsResponse {
  items: Product[];
  total: number;
  limit: number;
  offset: number;
}

interface StockItem {
  codbod: string;
  nombod?: string;
  cantidad: number;
}

interface StockResponse {
  sku: string;
  total: number;
  by_bodega: StockItem[];
}

const CACHE_TTL_CATALOG = 60 * 60 * 1000; // 1 hour
const CACHE_TTL_STOCK = 5 * 60 * 1000; // 5 min

async function fetchWithOfflineFallback<T>(
  url: string,
  ttlMs: number,
): Promise<T> {
  try {
    const data = await apiFetchJson<T>(url);
    await setCache(url, data, ttlMs);
    return data;
  } catch {
    const cached = await getCached<T>(url);
    if (cached) return cached;
    throw new Error("Sin conexión y sin datos cacheados");
  }
}

export function useProducts(query: string, page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const key = query
    ? `/api/products?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`
    : null;

  return useSWR<ProductsResponse>(
    key,
    (url) => fetchWithOfflineFallback<ProductsResponse>(url, CACHE_TTL_CATALOG),
    {
      revalidateOnFocus: false,
      dedupingInterval: 30_000,
    },
  );
}

export function useStock(sku: string | null) {
  const key = sku ? `/api/products/${encodeURIComponent(sku)}/stock` : null;

  return useSWR<StockResponse>(
    key,
    (url) => fetchWithOfflineFallback<StockResponse>(url, CACHE_TTL_STOCK),
    {
      revalidateOnFocus: false,
      dedupingInterval: 10_000,
    },
  );
}
