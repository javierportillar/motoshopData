# Smoke test bronze · 2026-05-28

## bodegas (ingest_date=2026-05-28)
- Dump local: 1 fila, 1.3 KB, 0.0s
- Subida UC Volume: ok (4.8s)
- COUNT(*) parquet:  1
- COUNT(*) bronze:   1
- Verdict: ✅ OK — conteos cuadran y N > 0

## formapago (ingest_date=2026-05-28)
- Dump local: 20 filas, 6.7 KB, 0.0s
- Subida UC Volume: ok (1.4s)
- COUNT(*) parquet:  20
- COUNT(*) bronze:   20
- Verdict: ✅ OK — conteos cuadran y N > 0

## Conclusión
Verificación crítica #3 de F0 cumplida. El pipeline MySQL → Parquet → UC Volume → Bronze funciona end-to-end con datos reales.
