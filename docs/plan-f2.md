# Plan detallado · Fase 2 · Silver + PWA MVP

> Plan operativo de la Fase 2, derivado de [PLAN.md](../PLAN.md) y de [SEGUIMIENTO.md](../SEGUIMIENTO.md). La Fase 1 ya quedó cerrada y la F1.5 está validada con evidencia física en Windows. Este documento convierte el objetivo de F2 en una secuencia de trabajo ejecutable.

## Objetivo

Construir un modelo Silver limpio y usable, y exponerlo desde una PWA que permita login, búsqueda y consulta de stock con una experiencia suficiente para el uso diario.

**Hito:** *"El vendedor abre la app desde la calle, busca un repuesto, ve precio y stock por bodega, y puede volver a entrar sin perder la sesión."*

## Lo que ya está resuelto

- F1 cerrada con evidencias V6, V7 y C-1.
- F1.5 cerrada con R3 validada por kill-y-retry y R-X2 validada con caché real.
- API read-only funcionando con auth, rate limit y tests verdes.
- Seguimiento y contexto del proyecto ya distinguen F1 cerrada y F2 abierta.
- Los notebooks de Databricks viven en `Repos/javierportillar/motoshopData`; si un cambio ya está en `main`, el agente puede sincronizar el notebook en el Git folder por API cuando la UI no haga evidente el Pull.

## Ruta rápida

1. Cerrar la ADR-0012 para no improvisar el stack de F2 a mitad de sprint.
2. Construir Silver desde Bronze con notebooks SQL reproducibles.
3. Añadir validaciones de calidad y evidencias de salida para Silver.
4. Montar la PWA sobre el scaffold actual con login, búsqueda y ficha de SKU.
5. Cerrar offline básico, manifest e instalación móvil.
6. Actualizar `SEGUIMIENTO.md` con los gates de F2 cuando cada verificación pase.

## Alcance

### Track A · Silver

- `fact_ventas`, `fact_compras`, `fact_inventario`.
- `dim_producto`, `dim_tiempo`, `dim_tercero`, `dim_sucursal`, `dim_bodega`.
- Tipado y limpieza formal de fechas, cantidades y claves.
- Reglas de calidad y validación de duplicados.
- Linaje visible en Unity Catalog.

### Track T · PWA

- Login con persistencia de sesión.
- Búsqueda de productos con paginación.
- Ficha de SKU con precio, stock por bodega y ventas recientes.
- Manifest PWA e instalación móvil.
- Modo offline básico para el catálogo ya consultado.

## Fuera de alcance por ahora

- Limpieza de R1 y R2, salvo que un trigger de riesgo obligue a actuar.
- Escritura sobre sgHermes.
- Fase 4 de ML y Fase 6 de optimización.
- Replantear el API read-only que ya funciona.

## Verificaciones de salida

1. No hay duplicados en Silver.
2. Las fechas inválidas quedan cuarentenadas o fallan de forma explícita.
3. Los totales Silver cuadran con un reporte conocido de sgHermes con tolerancia menor a 0.5%.
4. La PWA sobrevive a cerrar y reabrir la app.
5. La PWA funciona sin conexión una vez cacheado el catálogo básico.
6. La búsqueda responde en menos de 1 s con el volumen actual.
7. Los permisos por rol se respetan.
8. La PWA muestra el mismo dato que MySQL para cinco SKUs aleatorios.

## Siguiente paso

Implementar F2-A primero: modelos Silver + validaciones de calidad + evidencia de salida. Después, pasar al PWA sin mezclar ambos frentes.
