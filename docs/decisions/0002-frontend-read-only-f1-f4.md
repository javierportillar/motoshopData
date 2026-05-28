# ADR-0002 · Frontend solo lectura en F1–F4

- **Estado:** Accepted
- **Fecha:** 2026-05-27
- **Bloquea:** F1 → F4
- **Decide:** Equipo (heredado de PLAN.md §7)

## Contexto

sgHermes es el sistema operativo del negocio. Cualquier escritura concurrente desde un canal nuevo introduce riesgo de conflictos de numeración, bloqueos MyISAM y reconciliación contable difícil. A la vez, el negocio necesita consulta remota lo antes posible.

## Opciones consideradas

1. **Solo lectura** hasta F4; escritura limitada en tablas `app_*` desde F5.
2. **Bidireccional desde F1**, escribiendo directo en tablas de sgHermes.
3. **Reemplazar sgHermes** y migrar todo a un sistema nuevo.

## Decisión

Adoptar (1). La PWA hace consultas (catálogo, stock, ventas, dashboards, predicciones) sin tocar sgHermes durante F1–F4. La escritura (cotizaciones, pedidos remotos) se habilita en F5 contra tablas nuevas `app_*` en InnoDB, separadas de la operación contable.

## Consecuencias

- Riesgo operativo mínimo durante el período de aprendizaje.
- Se permite validar el modelo de uso antes de comprometer el camino de escritura.
- En F5 habrá que diseñar la reconciliación cotización → factura sgHermes.
- Hasta F5, el valor entregable está limitado a consulta y analítica.
