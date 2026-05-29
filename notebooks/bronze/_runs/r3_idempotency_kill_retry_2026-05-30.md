# R3 · Idempotencia kill-y-retry — 2026-05-30

Notebook/flujo: `infra/dump_to_cloud.py --tables-core --ingest-date 2026-05-30`
Warehouse usado para validación bronze: `43bc044eaef4cca4`

## Setup
- Fecha de prueba: 2026-05-30
- Volumen destino: `/Volumes/motoshop/bronze/_landing`
- Manifest local generado: `_staging/manifest_2026-05-30.json`
- Materialización bronze validada con SQL Warehouse: `CREATE OR REPLACE TABLE ... FROM read_files(...)`

## Run 1 (matado)
- Duración hasta kill: ~14s
- Tablas completadas: 2 / 12
- Última tabla en proceso: `productos`
- Observación: `facventas` y `detfventas` ya estaban subidos; `productos` alcanzó a escribir parquet local, pero no llegó a completar el upload.

## Run 2 (retry)
- Duración: 35.9s
- Tablas completadas: 12 / 12
- Manifiesto subido: `/Volumes/motoshop/bronze/_landing/_manifests/manifest_2026-05-30.json`

## Conteos finales (bronze vs origen)
| Tabla | Bronze | Origen | Diferencia |
|-------|--------|--------|------------|
| facventas | 6340 | 6340 | 0 |
| detfventas | 27775 | 27775 | 0 |
| productos | 6185 | 6185 | 0 |
| auxinventario | 26174 | 26174 | 0 |
| bodegas | 1 | 1 | 0 |
| terceros | 161 | 161 | 0 |
| compras | 762 | 762 | 0 |
| detcompras | 11623 | 11623 | 0 |
| sucursales | 0 | 0 | 0 |
| formapago | 20 | 20 | 0 |
| subproduct | 0 | 0 | 0 |
| preciosxpro | 123 | 123 | 0 |

## Veredicto
✅ R3 cumplida — el kill-y-retry deja Bronze consistente y la corrida final reproduce exactamente el origen.

## Trade-off documentado
`INSERT REPLACE WHERE` + `overwrite=True` sobreescribe la partición completa del día cuando la corrida termina bien. Si se mata a mitad, quedan artefactos parciales en `_staging/` o en el Volume, pero el retry completo converge al estado correcto.
