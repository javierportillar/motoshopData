# ADR-0001 · Arquitectura medallion bronze→silver→gold

- **Estado:** Accepted
- **Fecha:** 2026-05-27
- **Bloquea:** F0 → F1+
- **Decide:** Equipo (heredado de PLAN.md §4)

## Contexto

`motoshop2024` vive en un MySQL 5.0 local sobre MyISAM. No hay pipeline, ni capacidad analítica. El Track A debe procesar este dato sin tocar la fuente y con margen para sumar futuras fuentes (e-commerce, redes, externos).

## Opciones consideradas

1. **Medallion bronze→silver→gold sobre Delta Lake** (Databricks).
2. **Saltarse bronze:** ir directo de la BD a un modelo silver.
3. **Híbrido:** snapshots directos a silver, sin Delta.

## Decisión

Adoptar medallion estándar (1).

- **Bronze:** espejo inmutable particionado por `ingest_date`. Nada de transformaciones.
- **Silver:** datos conformados, tipados, deduplicados, con reglas de calidad.
- **Gold:** marts analíticos y feature tables.

Todo sobre Delta Lake en Unity Catalog (`motoshop.{bronze,silver,gold}`).

## Consecuencias

- Time-travel y reproceso garantizados (Delta).
- Linaje y permisos centralizados (Unity Catalog).
- Coste de almacenamiento ligeramente mayor por mantener bronze inmutable. Aceptable dado el volumen actual.
- Curva de aprendizaje para quien venga de un ETL tradicional.
