# ADR-0005 · Conectividad Databricks ↔ MySQL local (P1)

- **Estado:** **Proposed** — bloquea F0 → F1
- **Fecha:** 2026-05-27
- **Bloquea:** F0 (entregable Track A · "Estrategia conectividad decidida y probada")
- **Decide:** Humano (responsable del proyecto)

## Contexto

El MySQL `motoshop2024` vive en un PC Windows local sin IP pública. El cluster Databricks corre en nube (otra red). Para ingestar a Bronze hay que decidir cómo viaja el dato.

## Opciones consideradas

### A · Self-hosted job en el PC empuja dumps a cloud storage *(recomendado por PLAN §12)*

- Un script Python local exporta tablas (CSV/Parquet) a S3 / ADLS / GCS con `ingest_date`.
- Databricks Auto Loader ingiere desde ahí a Bronze.
- **Pros:** desacoplado; sin abrir puertos del router; resiliente a caídas de red; idempotente por `ingest_date`; auditable.
- **Contras:** un eslabón más; el PC debe estar encendido a la hora del job; coste mínimo de storage.

### B · Túnel SSH/VPN desde el PC al VPC de Databricks

- Databricks JDBC se conecta directo al MySQL a través de un túnel persistente.
- **Pros:** ingesta más simple conceptualmente; menos partes móviles.
- **Contras:** túnel siempre arriba; superficie de ataque; dependencia de red estable; Databricks Free/Community no soporta VPC privadas; debugging cuando el túnel cae.

### C · Réplica gestionada en nube (RDS / Cloud SQL)

- Replicar MySQL a una instancia administrada.
- **Pros:** cluster Databricks habla con una BD cloud "normal"; backups automáticos.
- **Contras:** MySQL 5.0 sin soporte oficial — la réplica probablemente requiere mover de versión, lo cual rompe compatibilidad con sgHermes; coste mensual; complejidad de mantener réplica saludable.

## Recomendación

**Opción A — self-hosted dump → cloud storage.** Es la única que respeta las dos restricciones duras: no tocar sgHermes y no abrir puertos. Es además la que mejor escala cuando llegue F-A (e-commerce) y F-E (streaming).

Sub-decisión a tomar después: qué cloud storage (S3, ADLS, GCS). Atado a P5/cuenta Databricks.

## Consecuencias si se acepta A

- Hace falta espacio en el PC para staging temporal y conexión saliente HTTPS.
- Hay que decidir periodicidad (diaria nocturna para F1 según PLAN §7).
- Hay que decidir formato (Parquet recomendado por tipos; CSV es fallback).
- El script se versiona en este repo bajo `infra/` o `notebooks/bronze/`.
