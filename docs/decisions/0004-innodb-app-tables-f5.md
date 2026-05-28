# ADR-0004 · Tablas `app_*` en InnoDB cuando llegue F5

- **Estado:** Accepted
- **Fecha:** 2026-05-27
- **Bloquea:** F5 (escritura habilitada)
- **Decide:** Equipo (heredado de PLAN.md §6, §15)

## Contexto

Cuando se habilite la escritura desde la PWA (cotizaciones, pedidos remotos, sesiones, audit log), necesitamos transacciones, FKs declarativas y consistencia bajo concurrencia. MyISAM no las soporta.

## Opciones consideradas

1. **Tablas nuevas `app_*` en el mismo MySQL pero engine InnoDB.**
2. **BD paralela** (otro MySQL/PostgreSQL en el mismo PC o nube) para escrituras de app.
3. **Migrar todo `motoshop2024` a InnoDB** (o a MySQL 8).

## Decisión

Adoptar (1). Las nuevas tablas conviven con sgHermes en la misma BD pero usan InnoDB, separadas por prefijo `app_*` y con su propia política de numeración. sgHermes ni se entera.

Tablas previstas: `app_cotizaciones`, `app_pedidos_remotos`, `app_sesiones`, `app_audit_log`.

## Consecuencias

- Mínimo impacto en sgHermes.
- Transacciones y FKs disponibles donde se necesitan.
- Coexistencia de dos engines en la misma BD — aceptable, MySQL lo soporta.
- La reconciliación cotización → factura sgHermes sigue siendo manual/semi-auto al inicio.
