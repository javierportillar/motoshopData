# SQL Warehouse · cumplimiento de la verificación crítica F0 #4

> *"¿El cluster se apaga solo?"* — En Databricks Free Edition no hay
> clusters all-purpose; el equivalente para nuestro pipeline (ver
> [ADR-0010](../docs/decisions/0010-compute-databricks-free.md)) es un
> **Serverless SQL Warehouse** con **auto-stop ≤ 10 min**.

## Configuración esperada

| Setting | Valor objetivo | Por qué |
|---------|----------------|---------|
| Tipo | **Serverless SQL Warehouse** | Único soportado en Free Edition |
| Tamaño | **Starter** (el más pequeño disponible) | Coste mínimo, suficiente para F1 |
| Auto stop | **10 min** | Cumple la verificación crítica #4 |
| Channel | **Current** | Para tener Photon/Delta más nuevos |
| Acceso | El PAT del `.env` debe tener `CAN_USE` | Necesario para que el dump_to_cloud no falle |

## Opción A · Crear desde la UI (lo que se hizo en F0)

1. **Workspace → SQL → SQL Warehouses → Create SQL Warehouse.**
2. **Name:** `motoshop-warehouse`.
3. **Cluster size:** `Starter`.
4. **Auto stop:** `10 minutes`.
5. **Type:** `Serverless`.
6. **Channel:** `Current`.
7. **Create**.

Capturar pantalla del settings panel (ya con auto-stop = 10 min visible) y guardarla en `docs/evidence/sql_warehouse_settings.png` para auditoría — o pegar el texto en `notebooks/bronze/_runs/smoke_test_*.md`.

## Opción B · Crear desde el SDK (reproducible)

Existe el script [`infra/create_sql_warehouse.py`](create_sql_warehouse.py) que
hace lo mismo idempotentemente. Uso:

```bash
pip install -r infra/requirements.txt
python infra/create_sql_warehouse.py
```

Si el warehouse ya existe, no hace nada salvo verificar que el auto-stop ≤ 10
min. Si está mal, imprime una recomendación de ajuste manual (sin tocarlo —
el ALTER de un warehouse en producción debe ser consciente).

## Verificación de la verificación crítica #4

```sql
-- Desde el SQL Editor:
SELECT id, name, auto_stop_mins, state, warehouse_type
FROM SYSTEM.COMPUTE.WAREHOUSES
WHERE name = 'motoshop-warehouse';
```

`auto_stop_mins` debe ser ≤ 10. Si lo es, **verificación crítica #4 ✅**.

## Costo esperado

En Free Edition, el SQL Warehouse Serverless está incluido dentro del crédito
mensual gratuito. El auto-stop de 10 min evita consumo silencioso fuera de los
runs nocturnos del Workflow.
