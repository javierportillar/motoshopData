/** Formatea un valor monetario según su magnitud: M para millones, K para miles, literal para < $1K. */
export function formatMoney(value: number): string {
  if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${Math.round(value).toLocaleString("es-CO")}`;
}
