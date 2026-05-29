import useSWR from "swr";
import { apiFetchJson } from "./client";

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
  nom_bodega?: string;
  stock: number;
}

interface StockResponse {
  codprod: string;
  total: number;
  by_bodega: StockItem[];
}

export function useProducts(query: string, page = 1, limit = 20) {
  const offset = (page - 1) * limit;
  const key = query
    ? `/api/products?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`
    : null;

  return useSWR<ProductsResponse>(key, (url) => apiFetchJson(url), {
    revalidateOnFocus: false,
    dedupingInterval: 30_000,
  });
}

export function useStock(sku: string | null) {
  const key = sku ? `/api/products/${encodeURIComponent(sku)}/stock` : null;
  return useSWR<StockResponse>(key, (url) => apiFetchJson(url), {
    revalidateOnFocus: false,
    dedupingInterval: 10_000,
  });
}
