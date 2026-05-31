# Asignación de Devs - F7 Frontend Fixes v1

**Fecha**: 2026-05-31  
**Revisor**: Senior QA Agent  
**Estado**: Asignado - Listo para ejecución

---

## Equipo Asignado

| Rol | Dev | Especialidad | Disponibilidad |
|-----|-----|--------------|----------------|
| **Dev Frontend 1** | Por asignar | React/Next.js, UI/UX, filtros y navegación | Full-time |
| **Dev Frontend 2** | Por asignar | React/Next.js, gráficos (recharts), visualizaciones | Full-time |
| **Dev Backend 1** | Por asignar | Python/FastAPI, SQL, Databricks queries | Full-time |

---

## Requerimientos de Infraestructura

### PC Windows (Servidor FastAPI)

**⚠️ CRÍTICO**: El servidor FastAPI corre en un PC Windows, no en Linux/Mac.

**Dev Backend 1 necesita acceso al PC Windows para**:
- Editar código FastAPI en `motoshop-app/api/src/motoshop_api/`
- Reiniciar el servidor después de cambios (`start_api.ps1`)
- Probar endpoints localmente (`http://localhost:8000`)
- Verificar logs y debugging
- Ejecutar scripts PowerShell (`check_health.ps1`)

**Opciones de acceso**:
1. **Acceso físico**: Dev Backend 1 trabaja directamente en el PC Windows
2. **Acceso remoto**: RDP (Remote Desktop Protocol) o similar
3. **Desarrollo local + deploy**: Dev Backend 1 trabaja en su máquina local, pero necesita acceso al PC Windows para deploy y testing final

**Scripts PowerShell disponibles**:
- `start_api.ps1`: Inicia servidor FastAPI
- `check_health.ps1`: Verifica health del servidor
- `start_motoshop.ps1`: Inicia stack completo (API + frontend)

**Nota**: Dev Frontend 1 y 2 NO necesitan acceso al PC Windows, trabajan con el frontend en sus máquinas locales y consumen la API remota.

---

## FASE 1: BUGS CRÍTICOS (Semana 1)

**Objetivo**: Funcionalidad básica operativa  
**Duración**: 5 días hábiles  
**Total horas**: 13h

### Dev Frontend 1 (8h)

| Día | Tarea | Issue | Horas | Entregable |
|-----|-------|-------|-------|------------|
| Lun AM | PLAN COMPRAS: Fix filtros ABC | 12.1 | 2h | Filtros A/B/C funcionan |
| Lun PM | PLAN COMPRAS: Fix filtros urgencia | 12.2 | 2h | Filtros alta/media/baja funcionan |
| Mar AM | PLAN COMPRAS: Fix toggle dormidos | 12.3 | 2h | Toggle "Solo dormidos" funciona |
| Mar PM | ALERTAS: Fix filtro urgencia | 7.1 | 2h | Filtros muestran todos los niveles |

**Criterios de aceptación**:
- [ ] PLAN COMPRAS: Al filtrar por ABC A, solo muestra productos A
- [ ] PLAN COMPRAS: Al filtrar por urgencia alta, solo muestra alta
- [ ] PLAN COMPRAS: Toggle "Solo dormidos" filtra correctamente
- [ ] ALERTAS: Filtros Alta/Media/Baja muestran datos correctos

---

### Dev Backend 1 (5h)

| Día | Tarea | Issue | Horas | Entregable |
|-----|-------|-------|-------|------------|
| Lun AM | ACCIONES: Debug endpoint vacío | 8.1 | 3h | Endpoint retorna datos o EmptyState |
| Lun PM | INVENTARIO: Fix "SIN NOMBRE" | 3.1 | 2h | Bodegas muestran nombre correcto |

**Criterios de aceptación**:
- [ ] ACCIONES: `/api/alerts/actions/me` retorna acciones del usuario
- [ ] ACCIONES: Si no hay acciones, frontend muestra EmptyState
- [ ] INVENTARIO: `/api/metrics/inventory-summary` retorna nombres de bodegas
- [ ] INVENTARIO: Si nombre es NULL, muestra "Bodega {id}"

---

### Dev Frontend 1 (continuación)

| Día | Tarea | Issue | Horas | Entregable |
|-----|-------|-------|-------|------------|
| Mar PM | ALERTAS: Fix link producto | 7.2 | 2h | Link "Ver SKU" navega correctamente |

**Criterios de aceptación**:
- [ ] ALERTAS: Link "Ver SKU" lleva a `/products/{sku}` y muestra datos
- [ ] Si SKU no existe, muestra EmptyState con mensaje claro

---

### Hitos Fase 1

| Día | Hito | Responsable |
|-----|------|-------------|
| Lun EOD | PLAN COMPRAS filtros ABC + urgencia funcionando | Dev Frontend 1 |
| Lun EOD | ACCIONES endpoint debuggeado | Dev Backend 1 |
| Mar EOD | PLAN COMPRAS + ALERTAS completamente funcionales | Dev Frontend 1 |
| Mar EOD | INVENTARIO nombres correctos | Dev Backend 1 |
| Mié AM | **DEMO FASE 1** con stakeholder | Todos |

---

## FASE 2: BUGS + DATA QUALITY (Semana 2)

**Objetivo**: Datos correctos y completos  
**Duración**: 5 días hábiles  
**Total horas**: 13h

### Dev Frontend 2 (4h)

| Día | Tarea | Issue | Horas | Entregable |
|-----|-------|-------|-------|------------|
| Lun AM | FORECAST: Reemplazar MOCK_SUGGESTIONS | 6.1 | 4h | Buscador usa `/api/products?q=...` |

**Criterios de aceptación**:
- [ ] FORECAST: Al escribir en buscador, sugiere SKUs con forecast
- [ ] FORECAST: Sugerencias vienen de backend, no hardcodeadas
- [ ] FORECAST: Si SKU no tiene forecast, muestra mensaje "Sin predicción disponible"

---

### Dev Backend 1 (9h)

| Día | Tarea | Issue | Horas | Entregable |
|-----|-------|-------|-------|------------|
| Lun AM | VENTAS: Auditar dato agosto 2025 | 2.2 | 3h | Query SQL corregida |
| Lun PM | COHORTES: Auditar huecos fechas | 9.1 | 2h | Query SQL sin filtros excluyentes |
| Mar AM | COHORTES: Fix cálculo recurrencia | 9.2 | 2h | Recurrencia calculada correctamente |
| Mar PM | DORMIDOS: Eliminar LIMIT 50 | 5.1 | 2h | Query retorna todos los dormidos |

**Criterios de aceptación**:
- [ ] VENTAS: `/api/metrics/sales-trend` retorna dato agosto 2025 correcto
- [ ] COHORTES: `/api/metrics/cohortes` retorna todos los meses sin huecos
- [ ] COHORTES: Recurrencia = (clientes 2+ compras) / (total clientes cohorte)
- [ ] DORMIDOS: `/api/metrics/dormidos` retorna 500+ productos si existen

---

### Hitos Fase 2

| Día | Hito | Responsable |
|-----|------|-------------|
| Lun EOD | FORECAST buscador funcional | Dev Frontend 2 |
| Lun EOD | VENTAS dato agosto corregido | Dev Backend 1 |
| Mar EOD | COHORTES + DORMIDOS data quality | Dev Backend 1 |
| Mié AM | **DEMO FASE 2** con stakeholder | Todos |

---

## FASE 3: ENHANCEMENTS UX (Semanas 3-4)

**Objetivo**: Experiencia de usuario completa  
**Duración**: 10 días hábiles  
**Total horas**: 37h

### Dev Frontend 1 (19h)

| Semana | Día | Tarea | Issue | Horas | Entregable |
|--------|-----|-------|-------|-------|------------|
| 3 | Lun | INICIO: KPIs clickeables | 1.1 | 2h | KPIs navegan a dashboards |
| 3 | Mar-Mié | VENTAS: Toggle diaria/mensual/histórica | 2.1 | 8h | 3 vistas funcionales |
| 3 | Jue-Vie | VENDEDORES: Detalle + toggles | 10.1, 10.2 | 6h | Detalle vendedor + 3 períodos |
| 4 | Lun | ABC: Explicación + UX | 4.1, 4.2 | 3h | Card explicativa + tooltips |

**Criterios de aceptación**:
- [ ] INICIO: Click en "Ventas mes" → `/dashboards/ventas`
- [ ] INICIO: Click en "Valor inv" → `/dashboards/inventario`
- [ ] VENTAS: Toggle "Diaria" muestra ventas del día + productos
- [ ] VENTAS: Toggle "Mensual" muestra comparación mes actual vs anterior
- [ ] VENTAS: Toggle "Histórica" muestra total acumulado
- [ ] VENDEDORES: Click en vendedor muestra detalle (ventas por categoría, ticket promedio)
- [ ] VENDEDORES: Toggle "Este mes" / "Histórico" / "Últimos 6 meses"
- [ ] ABC: Card "¿Qué es segmentación ABC?" con explicación clara
- [ ] ABC: Tooltip en gráfico explica cada segmento

---

### Dev Frontend 2 (18h)

| Semana | Día | Tarea | Issue | Horas | Entregable |
|--------|-----|-------|-------|-------|------------|
| 3 | Lun-Mié | INICIO: Gráfica año anterior | 1.2 | 6h | SalesTrendChart con 2 series |
| 3 | Jue-Vie | DORMIDOS: Ordenar + días sin venta | 5.2, 5.3 | 4h | Tabla ordenable + columna días |
| 4 | Lun-Mié | FORECAST: Visualización mejorada | 6.2, 6.3 | 6h | Gráfico barras + intervalos claros |
| 4 | Jue | DRIFT: Explicación | 11.1 | 2h | Card explicativa |

**Criterios de aceptación**:
- [ ] INICIO: SalesTrendChart muestra 2 líneas (2025 + 2026) con colores distintos
- [ ] INICIO: Leyenda indica "Año actual" y "Año anterior"
- [ ] DORMIDOS: Tabla ordenable por "Fecha última compra" (asc/desc)
- [ ] DORMIDOS: Columna "Días sin venta" calculada y mostrada
- [ ] FORECAST: Gráfico de barras con eje X = horizonte (7, 14, 30 días)
- [ ] FORECAST: Tooltip explica "Día 0-7: 2 unidades, día 7-14: 2 unidades..."
- [ ] FORECAST: Intervalo de confianza mostrado como área sombreada
- [ ] DRIFT: Card "¿Qué es monitoreo de drift?" con explicación clara
- [ ] DRIFT: Tooltip en cada métrica explica su significado

---

### Hitos Fase 3

| Semana | Día | Hito | Responsable |
|--------|-----|------|-------------|
| 3 | Mié EOD | INICIO KPIs + gráfica año anterior | Dev Frontend 1 + 2 |
| 3 | Vie EOD | VENTAS toggles + VENDEDORES detalle | Dev Frontend 1 |
| 3 | Vie EOD | DORMIDOS ordenable + días sin venta | Dev Frontend 2 |
| 4 | Mié EOD | FORECAST visualización mejorada | Dev Frontend 2 |
| 4 | Jue EOD | ABC + DRIFT explicaciones | Dev Frontend 1 + 2 |
| 4 | Vie AM | **DEMO FINAL v1** con stakeholder | Todos |

---

## Dependencias y Bloqueos

| Tarea | Depende de | Bloqueante si |
|-------|------------|---------------|
| VENTAS toggles (2.1) | Backend endpoints para diaria/mensual/histórica | Backend no disponible en Semana 3 |
| FORECAST buscador (6.1) | Backend endpoint lista SKUs con forecast | Backend no disponible en Semana 2 |
| VENDEDORES toggles (10.2) | Backend parámetros de período | Backend no disponible en Semana 3 |
| INICIO gráfica año anterior (1.2) | Backend parámetro `?year=` en sales-trend | Backend no disponible en Semana 3 |

**Mitigación**: Dev Backend 1 disponible en Fase 1-2 para agregar endpoints necesarios. Si se bloquea, escalar a Tech Lead.

---

## Comunicación y Seguimiento

### Daily Standups
- **Hora**: 9:00 AM (15 min)
- **Formato**: 
  - ¿Qué hice ayer?
  - ¿Qué haré hoy?
  - ¿Tengo bloqueos?

### Demos
- **Fase 1**: Miércoles Semana 1, 10:00 AM
- **Fase 2**: Miércoles Semana 2, 10:00 AM
- **Fase 3 (Final)**: Viernes Semana 4, 10:00 AM

### Tracker
- **Herramienta**: GitHub Issues / Jira
- **Labels**: `fase-1`, `fase-2`, `fase-3`, `bug-critico`, `enhancement`
- **Asignación**: Cada issue asignado a dev específico

---

## Criterios de Éxito v1

- [ ] Todos los filtros funcionan (PLAN COMPRAS, ALERTAS)
- [ ] Navegación entre páginas funciona (KPIs clickeables, links productos)
- [ ] Datos mostrados son correctos (auditoría data quality)
- [ ] Componentes analíticos tienen explicación (ABC, DRIFT)
- [ ] Toggles de período funcionan (VENTAS, VENDEDORES)
- [ ] Gráficos muestran contexto histórico (INICIO, FORECAST)
- [ ] Stakeholder aprueba en DEMO FINAL

---

## Rollback Plan

Si Fase 1 no se completa en Semana 1:
- **Acción**: Extender Fase 1 a Semana 2
- **Impacto**: v1 se retrasa 1 semana
- **Decisión**: Tech Lead + Stakeholder

Si Fase 2 revela problemas de data quality mayores:
- **Acción**: Pausar Fase 3, dedicar Semana 3 a fixes
- **Impacto**: v1 se retrasa 1 semana, enhancements van a v1.1
- **Decisión**: Tech Lead + Stakeholder

---

## Próximos Pasos Inmediatos

1. **Hoy**: Asignar nombres de devs a roles (Dev Frontend 1, Dev Frontend 2, Dev Backend 1)
2. **Hoy**: Crear issues en tracker con labels de fase
3. **Mañana 9:00 AM**: Primer daily standup
4. **Mañana**: Devs inician Fase 1 según asignación
5. **Miércoles**: Demo Fase 1

---

**Documento generado por**: Senior QA Agent  
**Fecha**: 2026-05-31  
**Versión**: 1.0  
**Estado**: Listo para ejecución
