# Bitácora de decisiones arquitecturales (ADRs)

Cada decisión técnica importante del proyecto vive aquí como un archivo Markdown corto. La tabla resumen está en [SEGUIMIENTO.md → Bitácora de decisiones](../../SEGUIMIENTO.md#bitácora-de-decisiones).

## Formato

```
# ADR-NNNN · Título
- **Estado:** Proposed | Accepted | Superseded
- **Fecha:** YYYY-MM-DD
- **Bloquea:** fase / entregable
- **Decide:** quién

## Contexto
## Opciones consideradas
## Decisión (o recomendación si todavía es Proposed)
## Consecuencias
```

## Índice

| # | Título | Estado | Fase |
|---|--------|--------|------|
| [0001](0001-medallion-architecture.md) | Arquitectura medallion bronze→silver→gold | Accepted | F0+ |
| [0002](0002-frontend-read-only-f1-f4.md) | Frontend solo lectura en F1–F4 | Accepted | F1–F4 |
| [0003](0003-pwa-nextjs.md) | PWA con Next.js en lugar de app nativa | Accepted | F2 |
| [0004](0004-innodb-app-tables-f5.md) | Tablas `app_*` en InnoDB cuando llegue F5 | Accepted | F5 |
| [0005](0005-databricks-mysql-connectivity.md) | Conectividad Databricks ↔ MySQL local (P1) | **Proposed** | F0 → F1 |
| [0006](0006-remote-tunnel.md) | Túnel remoto para exponer la API (P2) | **Proposed** | F0 → F1 |
| [0007](0007-api-hosting.md) | Hosting de la API (P3) | **Proposed** | F0 → F1 |
| [0008](0008-auth-provider.md) | Provider de autenticación (P4) | **Proposed** | F1 |
| [0009](0009-monorepo-vs-two-repos.md) | Monorepo vs. dos repos separados | Accepted | F0 |
| [0010](0010-compute-databricks-free.md) | Compute en Databricks Free Edition | Accepted | F0 → F1 |
