"""Qué tablas necesita el backend del gold (para publicar un artefacto chico).

El gold tiene ~175 tablas de analítica; el backend sólo lee estas 16. Publicar un
``{tenant}_metrics.duckdb`` con únicamente estas tablas baja la descarga de ~50 MB
a unos pocos MB, con la misma frescura: es lo que permite refrescar seguido sin
pagar el costo en memoria (el swap abre el archivo nuevo mientras el viejo sigue
vivo y en 512 MB eso es un OOM).

Si se agrega una consulta que toque otra tabla, el test de consistencia falla:
la lista se mantiene desde el código, no a mano.
"""

from __future__ import annotations

#: Tablas con historial largo que se recortan a las últimas N fechas de snapshot.
#:
#: ``silver_fact_inventario`` tiene 3,7 M de filas (456 fechas) y son el 60 % del
#: artefacto. El backend sólo consulta el estado actual (última ``business_date``)
#: y un agregado por bodega; en el respaldo de la nube alcanza con la ventana.
#: En las PCs se sigue usando el gold completo.
VENTANA_POR_TABLA: dict[str, int] = {
    "silver_fact_inventario": 7,
}

#: Tablas del gold que el backend lee (verificado contra los SQL de
#: ``metrics/``, ``products/``, ``erp/repo.py``, ``llm/briefing.py`` y
#: ``purchase_assessments/``).
TABLAS_ARTEFACTO: tuple[str, ...] = (
    "silver_fact_ventas",
    "silver_fact_ventas_detalle",
    "silver_fact_compras",
    "silver_fact_compras_detalle",
    "silver_dim_producto",
    "silver_dim_bodega",
    "silver_fact_inventario",
    "gold_mart_ventas_diarias_sku",
    "gold_mart_inventario_actual",
    "gold_mart_productos_dormidos",
    "gold_mart_rotacion_abc",
    "gold_mart_abc_xyz",
    "gold_mart_cohortes_clientes",
    "gold_alertas_quiebre",
    "gold_alertas_drift",
    "gold_forecast_categoria",
)
