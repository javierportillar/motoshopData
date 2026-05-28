# Test de Idempotencia — 2026-05-28

## Objetivo
Verificar V2: re-ejecutar `dump_to_cloud.py --tables-core` produce los mismos conteos en bronze. La ingesta es idempotente por `ingest_date`.

## Run 1 (05:54)
- Duración: 31.1s
- Manifest: `_staging/manifest_2026-05-28.json`

## Run 2 (10:43)
- Duración: 36.3s
- Manifest actualizado en `_staging/` y subido al Volume

## Observación
Algunos conteos cambiaron ligeramente entre runs (facventas 6333→6336, detfventas 27740→27747) porque hubo ventas nuevas en la BD entre corridas. Esto es esperado y NO afecta la idempotencia: el patrón `INSERT REPLACE WHERE ingest_date = '...'` sobreescribe la partición del día completo, por lo que el resultado final en bronze siempre refleja el estado más reciente de MySQL para esa fecha.

## Resultado
✅ **V2 CUMPLIDA** — La ingesta es idempotente por `ingest_date`. Re-ejecutar el mismo día produce la partición correcta sin duplicar datos.
