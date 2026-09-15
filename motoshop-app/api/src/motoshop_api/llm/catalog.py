"""Fixed query catalog; callers cannot choose SQL, tables, or columns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QuerySpec:
    domain: str
    sql: str
    max_rows: int = 100

    def bind(self, tenant_id: str, _args: dict[str, object]) -> list[object]:
        return [tenant_id]
_TABLES = dict(zip(("sales", "purchases", "inventory", "abc", "dormant_products", "alerts", "forecasts", "analyses"),
                   ("gold_mart_ventas_diarias_sku", "silver_fact_compras", "gold_mart_inventario_actual",
                    "gold_mart_rotacion_abc", "gold_mart_productos_dormidos", "gold_alertas_quiebre",
                    "gold_forecast_categoria", "gold_mart_ventas_diarias_sku"), strict=True))
_CATALOG = {domain: QuerySpec(domain, f"SELECT ? AS tenant_id, COUNT(*) AS row_count FROM {table}")
            for domain, table in _TABLES.items()}
def get_query_spec(domain: str) -> QuerySpec:
    """Get a canonical, bounded query for a known DuckDB domain."""
    if domain not in _CATALOG:
        raise KeyError(f"No governed query for domain '{domain}'")
    return _CATALOG[domain]
