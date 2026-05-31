# Prompts Completos - F7 Frontend Fixes v1 (3 Fases)

**Fecha**: 2026-05-31  
**Uso**: Copiar y pegar cada prompt completo al dev correspondiente  
**Duración total**: 4 semanas (63h)

---

## PROMPT COMPLETO: Dev Frontend 1

```
Sos Dev Frontend 1 del proyecto MotoShop. Tu rol es arreglar bugs críticos y agregar enhancements en el frontend de Next.js/React.

## CONTEXTO DEL PROYECTO

MotoShop es una PWA de análisis de ventas e inventario para una tienda de repuestos de motos. El stack es:
- Frontend: Next.js 14 + React 18 + TypeScript + Tailwind CSS
- UI Components: Design system propio en `motoshop-app/web/components/ui/`
- API: FastAPI corriendo en PC Windows (no necesitás acceso, consumís endpoints remotos)
- Datos: Databricks (backend ya maneja queries)

## TU MISIÓN COMPLETA (3 FASES - 4 SEMANAS)

Tenés 27 horas totales distribuidas en 3 fases.

---

# FASE 1: BUGS CRÍTICOS (Semana 1) - 8h

**Objetivo**: Funcionalidad básica operativa  
**Deadline**: Miércoles 10:00 AM (Demo Fase 1)

## TAREA 1.1: PLAN COMPRAS - Fix filtros ABC (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: Los filtros ABC (A, B, C) no hacen nada.

**Qué hacer**:
1. Abrí el archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el filtro ABC
3. Verificá que el `filter()` se aplique correctamente sobre los datos
4. Asegurate que al cambiar el filtro, la tabla se re-renderice

**Criterio de aceptación**:
- Al hacer click en "A", solo se muestran productos ABC = "A"
- Al hacer click en "B", solo se muestran productos ABC = "B"
- Al hacer click en "C", solo se muestran productos ABC = "C"
- Al hacer click en "Todas", se muestran todos

**Commit**: `fix(fase-1): PLAN COMPRAS filtros ABC funcionando`

---

## TAREA 1.2: PLAN COMPRAS - Fix filtros urgencia (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: Los filtros de urgencia (alta, media, baja) no muestran resultados.

**Qué hacer**:
1. En el mismo archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el filtro de urgencia
3. Verificá que el `filter()` compare correctamente (case sensitivity)

**Criterio de aceptación**:
- Al hacer click en "alta", solo se muestran productos urgencia = "alta"
- Al hacer click en "media", solo se muestran productos urgencia = "media"
- Al hacer click en "baja", solo se muestran productos urgencia = "baja"

**Commit**: `fix(fase-1): PLAN COMPRAS filtros urgencia funcionando`

---

## TAREA 1.3: PLAN COMPRAS - Fix toggle dormidos (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: El toggle "Solo dormidos" no filtra la tabla.

**Qué hacer**:
1. En el mismo archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el toggle
3. Verificá que el `filter()` filtre por campo `dormido`

**Criterio de aceptación**:
- Al activar "Solo dormidos", solo se muestran productos con `dormido = true`
- Al desactivar, se muestran todos los productos

**Commit**: `fix(fase-1): PLAN COMPRAS toggle dormidos funcionando`

---

## TAREA 1.4: ALERTAS - Fix filtro urgencia (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/alerts/page.tsx`

**Problema**: Solo se muestran alertas ALTA. Los filtros Media y Baja no muestran nada.

**Qué hacer**:
1. Abrí el archivo `alerts/page.tsx`
2. Buscá cómo se llama al endpoint `/api/alerts/stockout?urgency={urgency}`
3. Verificá que el parámetro `urgency` se pase correctamente al endpoint
4. Posible bug: el frontend hardcodea `urgency=alta`

**Criterio de aceptación**:
- Al hacer click en "Alta", se muestran solo alertas alta
- Al hacer click en "Media", se muestran solo alertas media
- Al hacer click en "Baja", se muestran solo alertas baja
- Los contadores se actualizan

**Commit**: `fix(fase-1): ALERTAS filtros urgencia funcionando`

---

# FASE 2: (Semana 2) - 0h

**Nota**: En Fase 2 no tenés tareas asignadas. Dev Frontend 2 y Dev Backend 1 trabajan en data quality.

**Tu rol en Fase 2**:
- Revisar PRs de Dev Frontend 2 si es necesario
- Preparar estructura para Fase 3 (componentes reutilizables)
- Documentar cambios de Fase 1

---

# FASE 3: ENHANCEMENTS UX (Semanas 3-4) - 19h

**Objetivo**: Experiencia de usuario completa  
**Deadline**: Viernes Semana 4, 10:00 AM (Demo Final v1)

## TAREA 3.1: INICIO - KPIs clickeables (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/page.tsx`

**Problema**: Los KPIs (ventas mes, facturas, ticket, valor inv) no son clickeables.

**Qué hacer**:
1. Abrí el archivo `page.tsx` (Home)
2. Buscá los componentes `<Stat>` que muestran KPIs
3. Envolvé cada `<Stat>` en un `<Link>` de Next.js
4. Navegación:
   - "Ventas mes" → `/dashboards/ventas`
   - "Facturas" → `/dashboards/ventas`
   - "Ticket promedio" → `/dashboards/ventas`
   - "Valor inventario" → `/dashboards/inventario`

**Criterio de aceptación**:
- Click en "Ventas mes" navega a `/dashboards/ventas`
- Click en "Valor inventario" navega a `/dashboards/inventario`
- Hover muestra cursor pointer
- Navegación es instantánea (Next.js Link)

**Commit**: `feat(fase-3): INICIO KPIs clickeables navegan a dashboards`

---

## TAREA 3.2: VENTAS - Toggles diaria/mensual/histórica (8h)

**Archivo**: `motoshop-app/web/app/(authenticated)/dashboards/ventas/page.tsx`

**Problema**: Falta toggle para vistas: diaria / mensual / histórica.

**Qué hacer**:
1. Abrí el archivo `ventas/page.tsx`
2. Agregá tabs con 3 vistas usando componente `<Tabs>` o similar
3. **Vista Diaria**:
   - Ventas del día actual
   - Productos vendidos hoy (tabla)
   - Detalle por vendedor
4. **Vista Mensual**:
   - Ventas del mes actual
   - Comparación con mes anterior (delta %)
   - Gráfico de tendencia mensual
5. **Vista Histórica**:
   - Total acumulado desde inicio
   - Gráfico de tendencia histórica (todos los meses)

**Dependencias**:
- ⚠️ **BLOQUEANTE**: Dev Backend 1 debe crear endpoints:
  - `/api/metrics/sales-daily?date=2026-05-31`
  - `/api/metrics/sales-monthly?month=2026-05`
  - `/api/metrics/sales-historical`
- Si endpoints no están listos, usá datos mock y dejá TODO comments

**Criterio de aceptación**:
- Toggle "Diaria" muestra ventas del día + productos vendidos
- Toggle "Mensual" muestra comparación mes actual vs anterior
- Toggle "Histórica" muestra total acumulado
- Transición entre vistas es suave (sin reload)

**Commit**: `feat(fase-3): VENTAS toggles diaria/mensual/histórica`

---

## TAREA 3.3: VENDEDORES - Detalle + toggles (6h)

**Archivo**: `motoshop-app/web/app/(authenticated)/vendedores/page.tsx`

**Problema**: Falta más detalle del vendedor y toggles por período.

**Qué hacer**:
1. Abrí el archivo `vendedores/page.tsx`
2. Agregá tabs: "Este mes" / "Histórico" / "Últimos 6 meses"
3. Al hacer click en un vendedor, mostrá detalle:
   - Ventas por categoría top
   - Ticket promedio
   - Productos vendidos
   - Comparación con mes anterior

**Dependencias**:
- ⚠️ **BLOQUEANTE**: Dev Backend 1 debe agregar parámetros a `/api/metrics/vendedores-summary`:
  - `?period=month` (este mes)
  - `?period=historical` (histórico)
  - `?period=6months` (últimos 6 meses)
  - `?vendedor_id=123` (detalle de vendedor específico)

**Criterio de aceptación**:
- Toggle "Este mes" muestra ranking del mes actual
- Toggle "Histórico" muestra ranking acumulado
- Toggle "Últimos 6 meses" muestra tendencia
- Click en vendedor muestra modal con detalle

**Commit**: `feat(fase-3): VENDEDORES detalle + toggles período`

---

## TAREA 3.4: ABC - Explicación + UX (3h)

**Archivo**: `motoshop-app/web/app/(authenticated)/dashboards/abc/page.tsx`

**Problema**: Usuario no entiende qué significa ABC, para qué sirve.

**Qué hacer**:
1. Abrí el archivo `abc/page.tsx`
2. Agregá Card con título "¿Qué es la segmentación ABC?"
3. Contenido explicativo:
   - **A**: 20% productos que generan 80% ingresos (alta rotación)
   - **B**: 30% productos que generan 15% ingresos (rotación media)
   - **C**: 50% productos que generan 5% ingresos (baja rotación)
4. Agregá tooltip en gráfico explicando cada segmento
5. Mostrá insight accionable: "Prioriza stock de productos A para evitar quiebres"

**Criterio de aceptación**:
- Card explicativa visible al inicio de la página
- Tooltip en gráfico muestra explicación al hover
- Insight accionable destacado con color

**Commit**: `feat(fase-3): ABC explicación clara + tooltips`

---

## ENTREGABLES FINALES

Cuando termines todas las tareas:
1. Todos los commits pusheados a `main`
2. Mensaje en Slack: "Dev Frontend 1 completó todas las tareas (27h)"
3. Si terminás antes del deadline, avisá para reasignar tareas

## DEPENDENCIAS Y BLOQUEOS

| Tarea | Depende de | Si está bloqueado |
|-------|------------|-------------------|
| 3.2 VENTAS toggles | Backend endpoints (Dev Backend 1) | Usá datos mock + TODO comments |
| 3.3 VENDEDORES toggles | Backend parámetros (Dev Backend 1) | Usá datos mock + TODO comments |

**Regla**: Si una dependencia no está lista después de 2 días, escalá en daily standup.

## CÓMO VERIFICAR QUE TODO FUNCIONA

```bash
cd motoshop-app/web
npm run dev
# Navegá a cada página y verificá criterios de aceptación
```

**Deadline final**: Viernes Semana 4, 10:00 AM (Demo Final v1)
```

---

## PROMPT COMPLETO: Dev Frontend 2

```
Sos Dev Frontend 2 del proyecto MotoShop. Tu rol es arreglar bugs y agregar visualizaciones en el frontend de Next.js/React, específicamente en Forecast y gráficos.

## CONTEXTO DEL PROYECTO

MotoShop es una PWA de análisis de ventas e inventario para una tienda de repuestos de motos. El stack es:
- Frontend: Next.js 14 + React 18 + TypeScript + Tailwind CSS
- UI Components: Design system propio en `motoshop-app/web/components/ui/`
- Gráficos: recharts (AreaChart, LineChart, BarChart)
- API: FastAPI corriendo en PC Windows (no necesitás acceso, consumís endpoints remotos)
- Datos: Databricks (backend ya maneja queries)

## TU MISIÓN COMPLETA (3 FASES - 4 SEMANAS)

Tenés 22 horas totales distribuidas en 3 fases.

---

# FASE 1: (Semana 1) - 0h

**Nota**: En Fase 1 no tenés tareas asignadas. Dev Frontend 1 y Dev Backend 1 trabajan en bugs críticos.

**Tu rol en Fase 1**:
- Revisar PRs de Dev Frontend 1 si es necesario
- Familiarizarte con el código de Forecast y gráficos
- Preparar estructura para Fase 2

---

# FASE 2: BUGS + DATA QUALITY (Semana 2) - 4h

**Objetivo**: Datos correctos y completos  
**Deadline**: Miércoles Semana 2, 10:00 AM (Demo Fase 2)

## TAREA 2.1: FORECAST - Reemplazar MOCK_SUGGESTIONS (4h)

**Archivo**: `motoshop-app/web/app/(authenticated)/forecast/page.tsx`

**Problema**: El buscador de SKU usa sugerencias hardcodeadas (`MOCK_SUGGESTIONS`) en lugar de buscar en el backend.

**Qué hacer**:
1. Abrí el archivo `forecast/page.tsx`
2. Buscá el array `MOCK_SUGGESTIONS`
3. Reemplazalo con llamada al endpoint `/api/products?q={query}&limit=20`
4. Usá el hook `useProducts` que ya existe en `lib/api/hooks.ts`
5. Filtrá resultados para mostrar solo SKUs con forecast disponible

**Código de referencia**:
```typescript
import { useProducts } from '@/lib/api/hooks';

const [query, setQuery] = useState('');
const { data: products } = useProducts(query, 20, 0);
const suggestions = products?.items.filter(p => p.has_forecast) || [];
```

**Criterio de aceptación**:
- Al escribir "MOTS", sugiere todos los SKUs que empiezan con "MOTS"
- Al escribir "1234", sugiere todos los SKUs que contienen "1234"
- Si SKU no tiene forecast, muestra mensaje "Sin predicción disponible"
- Sugerencias se actualizan en tiempo real

**Commit**: `fix(fase-2): FORECAST buscador usa backend en lugar de mocks`

---

# FASE 3: ENHANCEMENTS UX (Semanas 3-4) - 18h

**Objetivo**: Experiencia de usuario completa  
**Deadline**: Viernes Semana 4, 10:00 AM (Demo Final v1)

## TAREA 3.1: INICIO - Gráfica año anterior (6h)

**Archivo**: `motoshop-app/web/components/SalesTrendChart.tsx`

**Problema**: Gráfica de tendencia no muestra año anterior para comparación.

**Qué hacer**:
1. Abrí el archivo `SalesTrendChart.tsx`
2. Modificá el componente para aceptar 2 series:
   - Serie 1: Año actual (2026) - color primario
   - Serie 2: Año anterior (2025) - color secundario
3. Agregá leyenda: "Año actual" y "Año anterior"
4. Eje X: Enero a Diciembre (12 meses)
5. Eje Y: Valor de ventas

**Dependencias**:
- ⚠️ **BLOQUEANTE**: Dev Backend 1 debe agregar parámetro `?year=` a `/api/metrics/sales-trend`
- Ejemplo: `/api/metrics/sales-trend?periods=12&year=2026` y `?year=2025`

**Código de referencia** (recharts):
```typescript
import { LineChart, Line, XAxis, YAxis, Legend } from 'recharts';

<LineChart data={data}>
  <XAxis dataKey="month" />
  <YAxis />
  <Legend />
  <Line dataKey="current_year" name="Año actual" stroke="#C83828" />
  <Line dataKey="previous_year" name="Año anterior" stroke="#999" strokeDasharray="5 5" />
</LineChart>
```

**Criterio de aceptación**:
- Gráfica muestra 2 líneas (2025 + 2026) con colores distintos
- Leyenda indica "Año actual" y "Año anterior"
- Eje X muestra Enero a Diciembre
- Tooltip muestra valores de ambos años al hover

**Commit**: `feat(fase-3): INICIO gráfica compara año actual vs anterior`

---

## TAREA 3.2: DORMIDOS - Ordenar + días sin venta (4h)

**Archivo**: `motoshop-app/web/app/(authenticated)/dashboards/dormidos/page.tsx`

**Problema**: Falta ordenar por fecha de última compra y columna "Días sin venta".

**Qué hacer**:
1. Abrí el archivo `dormidos/page.tsx`
2. Agregá columna "Días sin venta" calculada: `dias_sin_venta = CURRENT_DATE - ultima_venta`
3. Agregá columna "Fecha última compra"
4. Hacé la tabla ordenable por ambas columnas (asc/desc)
5. Usá componente `<Table>` con prop `sortable`

**Dependencias**:
- ⚠️ **BLOQUEANTE**: Dev Backend 1 debe retornar campos `ultima_compra` y `dias_sin_venta` en `/api/metrics/dormidos`

**Criterio de aceptación**:
- Tabla muestra columna "Días sin venta" (ej: "125 días")
- Tabla muestra columna "Fecha última compra" (ej: "2026-01-15")
- Click en header ordena asc/desc
- Orden por defecto: "Días sin venta" desc (más antiguos primero)

**Commit**: `feat(fase-3): DORMIDOS tabla ordenable + días sin venta`

---

## TAREA 3.3: FORECAST - Visualización mejorada (6h)

**Archivo**: `motoshop-app/web/app/(authenticated)/forecast/page.tsx`

**Problema**: No queda claro si valores 7/14/30 días son acumulados o por período.

**Qué hacer**:
1. Abrí el archivo `forecast/page.tsx`
2. Cambiá visualización actual (tabla) por gráfico de barras:
   - Eje X: Horizonte (7, 14, 30 días)
   - Eje Y: Unidades predichas
   - Barras: Valor predicho
   - Área sombreada: Intervalo de confianza
3. Agregá tooltip explicativo:
   - "Día 0-7: 2 unidades (IC: 0.6-4.3)"
   - "Día 7-14: 2 unidades (IC: 0.8-4.5)"
   - "Día 14-30: 1 unidad (IC: -1.0-2.9)"
4. Agregá gráfico comparativo: predicciones altas vs bajas por producto

**Dependencias**:
- ✅ Ya completado: Tarea 2.1 (buscador funcional)
- Backend ya retorna datos de forecast con intervalos de confianza

**Código de referencia** (recharts):
```typescript
import { BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceArea } from 'recharts';

<BarChart data={forecastData}>
  <XAxis dataKey="horizon" />
  <YAxis />
  <Tooltip content={<CustomTooltip />} />
  <ReferenceArea y1={lower_bound} y2={upper_bound} fill="#ccc" opacity={0.3} />
  <Bar dataKey="predicted" fill="#C83828" />
</BarChart>
```

**Criterio de aceptación**:
- Gráfico de barras muestra predicciones para 7, 14, 30 días
- Intervalo de confianza mostrado como área sombreada
- Tooltip explica claramente cada período
- Gráfico comparativo muestra predicciones altas vs bajas

**Commit**: `feat(fase-3): FORECAST visualización mejorada con gráficos claros`

---

## TAREA 3.4: DRIFT - Explicación (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/drift/page.tsx`

**Problema**: Usuario no entiende qué es drift, para qué sirve, qué significan los estados.

**Qué hacer**:
1. Abrí el archivo `drift/page.tsx`
2. Agregá Card con título "¿Qué es el monitoreo de drift?"
3. Contenido explicativo:
   - **Drift**: Desviación de métricas clave respecto a su valor histórico
   - **Estados**:
     - Alerta: Métrica fuera de rango, requiere atención
     - Resuelto: Métrica volvió a rango normal
   - **Métricas monitoreadas**:
     - WAPE baseline: Error de predicción del modelo
     - Ventas diarias: Volumen de ventas promedio
     - Cobertura forecast: % de SKUs con predicción válida
     - Tasa recurrencia: % de clientes que recompran
4. Agregá tooltip en cada métrica

**Criterio de aceptación**:
- Card explicativa visible al inicio de la página
- Tooltip en cada métrica explica su significado
- Estados "Alerta" y "Resuelto" tienen colores distintivos

**Commit**: `feat(fase-3): DRIFT explicación clara + tooltips`

---

## ENTREGABLES FINALES

Cuando termines todas las tareas:
1. Todos los commits pusheados a `main`
2. Mensaje en Slack: "Dev Frontend 2 completó todas las tareas (22h)"
3. Si terminás antes del deadline, avisá para reasignar tareas

## DEPENDENCIAS Y BLOQUEOS

| Tarea | Depende de | Si está bloqueado |
|-------|------------|-------------------|
| 3.1 INICIO gráfica | Backend parámetro `?year=` (Dev Backend 1) | Usá datos mock + TODO comments |
| 3.2 DORMIDOS ordenar | Backend campos `ultima_compra`, `dias_sin_venta` (Dev Backend 1) | Usá datos mock + TODO comments |

**Regla**: Si una dependencia no está lista después de 2 días, escalá en daily standup.

## CÓMO VERIFICAR QUE TODO FUNCIONA

```bash
cd motoshop-app/web
npm run dev
# Navegá a:
# - /forecast → probá buscador + visualización
# - /dashboards/dormidos → probá ordenamiento
# - /drift → verificá explicación
# - / (home) → verificá gráfica año anterior
```

**Deadline final**: Viernes Semana 4, 10:00 AM (Demo Final v1)
```

---

## PROMPT COMPLETO: Dev Backend 1

```
Sos Dev Backend 1 del proyecto MotoShop. Tu rol es arreglar bugs críticos y agregar endpoints en el backend FastAPI que corre en un PC Windows.

## CONTEXTO DEL PROYECTO

MotoShop es una PWA de análisis de ventas e inventario para una tienda de repuestos de motos. El stack es:
- Backend: FastAPI + Python 3.11 + SQLAlchemy
- Base de datos: Databricks (queries SQL)
- Servidor: PC Windows (acceso físico o RDP)
- Scripts PowerShell: `start_api.ps1`, `check_health.ps1`

## ⚠️ REQUERIMIENTO CRÍTICO: ACCESO AL PC WINDOWS

El servidor FastAPI corre en un PC Windows. Necesitás acceso para:
- Editar código en `motoshop-app/api/src/motoshop_api/`
- Reiniciar el servidor: `.\start_api.ps1`
- Verificar health: `.\check_health.ps1`
- Probar endpoints: `http://localhost:8000`

**Opciones de acceso**:
1. Acceso físico al PC Windows
2. RDP (Remote Desktop Protocol)
3. Desarrollo local + deploy remoto al PC Windows

## TU MISIÓN COMPLETA (3 FASES - 4 SEMANAS)

Tenés 14 horas totales distribuidas en 2 fases.

---

# FASE 1: BUGS CRÍTICOS (Semana 1) - 5h

**Objetivo**: Funcionalidad básica operativa  
**Deadline**: Martes EOD (antes de Demo Fase 1 el miércoles)

## TAREA 1.1: ACCIONES - Debug endpoint vacío (3h)

**Archivo**: `motoshop-app/api/src/motoshop_api/alerts/repo.py` (o similar)

**Problema**: El endpoint `/api/alerts/actions/me` retorna array vacío `[]` incluso cuando el usuario ha gestionado alertas.

**Qué hacer**:
1. Abrí el archivo que maneja alertas (buscá `get_my_actions` o similar)
2. Verificá la query SQL que obtiene las acciones del usuario
3. Posibles bugs:
   - El `user_id` no se pasa correctamente a la query
   - La tabla `alert_actions` no tiene datos
   - El JOIN con tabla de usuarios está mal
4. Agregá logs para debuggear:
   ```python
   logger.info(f"get_my_actions called for user_id={user_id}")
   logger.info(f"Query: {query}")
   logger.info(f"Results: {results}")
   ```

**Criterio de aceptación**:
- Si el usuario ha gestionado alertas, el endpoint retorna array con acciones
- Si el usuario NO ha gestionado alertas, el endpoint retorna array vacío `[]`
- Frontend muestra EmptyState si array está vacío

**Cómo verificar**:
```powershell
# En PC Windows
cd motoshop-app
.\start_api.ps1

# En otra terminal
curl http://localhost:8000/api/alerts/actions/me?date_from=2026-01-01&date_to=2026-12-31
```

**Commit**: `fix(fase-1): ACCIONES endpoint retorna datos correctamente`

---

## TAREA 1.2: INVENTARIO - Fix "SIN NOMBRE" en bodegas (2h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: El endpoint `/api/metrics/inventory-summary` retorna bodegas con nombre "SIN NOMBRE".

**Qué hacer**:
1. Abrí `motoshop-app/api/src/motoshop_api/metrics/repo.py`
2. Buscá la función `get_inventory_summary()`
3. Verificá la query SQL que obtiene stock por bodega
4. Posible bug: el JOIN con tabla de bodegas está mal o falta
5. Agregá fallback: si nombre es NULL, mostrar "Bodega {id}"

**Query corregida**:
```python
query = """
SELECT 
    i.bodega_id,
    COALESCE(b.nombre, CONCAT('Bodega ', i.bodega_id)) as nombre_bodega,
    SUM(i.stock) as stock_total,
    SUM(i.valor) as valor_total
FROM mart_inventario_actual i
LEFT JOIN dim_bodegas b ON i.bodega_id = b.id
GROUP BY i.bodega_id, b.nombre
"""
```

**Criterio de aceptación**:
- Endpoint retorna bodegas con nombre real (ej: "Bodega Central")
- Si bodega no tiene nombre, muestra "Bodega {id}"
- Frontend muestra nombres correctos

**Cómo verificar**:
```powershell
curl http://localhost:8000/api/metrics/inventory-summary
# Debe retornar nombres de bodegas correctos
```

**Commit**: `fix(fase-1): INVENTARIO bodegas muestran nombre correcto`

---

# FASE 2: BUGS + DATA QUALITY (Semana 2) - 9h

**Objetivo**: Datos correctos y completos  
**Deadline**: Martes EOD Semana 2 (antes de Demo Fase 2 el miércoles)

## TAREA 2.1: VENTAS - Auditar dato agosto 2025 (3h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: El endpoint `/api/metrics/sales-trend` retorna dato agosto 2025 = 592,100 pero stakeholder dice que es incorrecto.

**Qué hacer**:
1. Abrí `motoshop-app/api/src/motoshop_api/metrics/repo.py`
2. Buscá la función `get_sales_trend()`
3. Verificá la query SQL:
   - ¿Está filtrando correctamente por fecha?
   - ¿Los JOINs están bien?
   - ¿Hay duplicación de datos?
4. Ejecutá query directa en Databricks para verificar:
   ```sql
   SELECT 
       DATE_FORMAT(fecha, 'yyyy-MM') as mes,
       SUM(total) as ventas
   FROM fact_ventas
   WHERE DATE_FORMAT(fecha, 'yyyy-MM') = '2025-08'
   GROUP BY DATE_FORMAT(fecha, 'yyyy-MM')
   ```
5. Compará resultado con lo que retorna el endpoint

**Criterio de aceptación**:
- Endpoint retorna dato agosto 2025 correcto (verificado con query directa)
- Si hay discrepancia, corregir query SQL

**Commit**: `fix(fase-2): VENTAS dato agosto 2025 corregido`

---

## TAREA 2.2: COHORTES - Auditar huecos fechas (2h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: El endpoint `/api/metrics/cohortes` retorna cohortes con huecos en fechas (2024-01, 2024-08, 2024-09...).

**Qué hacer**:
1. Abrí `motoshop-app/api/src/motoshop_api/metrics/repo.py`
2. Buscá la función `get_cohortes()`
3. Verificá la query SQL que agrupa por mes de primera compra
4. Posible bug: hay filtros excluyendo meses sin datos
5. Verificá que la query retorne TODOS los meses, incluso si tienen 0 clientes

**Criterio de aceptación**:
- Endpoint retorna todos los meses sin huecos
- Si un mes no tiene cohortes, retorna array vacío para ese mes

**Commit**: `fix(fase-2): COHORTES sin huecos en fechas`

---

## TAREA 2.3: COHORTES - Fix cálculo recurrencia (2h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: Cohortes muestran datos raros: 1 cliente, 100% recurrencia.

**Qué hacer**:
1. En la misma función `get_cohortes()` o `get_cohortes_detail()`
2. Verificá el cálculo de recurrencia:
   - Recurrencia = (Clientes que compraron 2+ veces) / (Total clientes en cohorte)
3. Si solo hay 1 cliente y compró 2+ veces → 100% (correcto pero misleading)
4. Agregá contexto: si muestra < 5, agregar nota "muestra pequeña"

**Criterio de aceptación**:
- Recurrencia calculada correctamente
- Si muestra < 5, frontend puede mostrar nota "muestra pequeña"

**Commit**: `fix(fase-2): COHORTES recurrencia calculada correctamente`

---

## TAREA 2.4: DORMIDOS - Eliminar LIMIT 50 (2h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: El endpoint `/api/metrics/dormidos` solo retorna 50 productos cuando hay más.

**Qué hacer**:
1. Abrí `motoshop-app/api/src/motoshop_api/metrics/repo.py`
2. Buscá la función `get_dormidos()`
3. Verificá si hay `LIMIT 50` en la query SQL
4. Eliminá el límite o aumentalo a 500+
5. Agregá paginación si es necesario

**Query actual** (probablemente):
```python
query = """
SELECT * FROM mart_productos_dormidos
WHERE dias_sin_venta > 90
LIMIT 50
"""
```

**Query corregida**:
```python
query = """
SELECT * FROM mart_productos_dormidos
WHERE dias_sin_venta > 90
ORDER BY dias_sin_venta DESC
LIMIT 500
"""
```

**Criterio de aceptación**:
- Endpoint retorna 500+ productos si existen
- Frontend puede mostrar todos los productos

**Commit**: `fix(fase-2): DORMIDOS retorna todos los productos (sin límite 50)`

---

# FASE 3: (Semanas 3-4) - 0h

**Nota**: En Fase 3 no tenés tareas asignadas. Dev Frontend 1 y 2 trabajan en enhancements UX.

**Tu rol en Fase 3**:
- Soporte a devs frontend si necesitan endpoints adicionales
- Revisar PRs si es necesario
- Preparar documentación técnica

---

## ENTREGABLES FINALES

Cuando termines todas las tareas:
1. Todos los commits pusheados a `main`
2. Servidor reiniciado: `.\start_api.ps1`
3. Mensaje en Slack: "Dev Backend 1 completó todas las tareas (14h)"
4. Si terminás antes del deadline, avisá para reasignar tareas

## DEPENDENCIAS Y BLOQUEOS

**No tenés dependencias de otros devs**. Sos el único que trabaja en backend.

**Regla**: Si una query SQL no funciona, verificá directamente en Databricks antes de culpar al código.

## CÓMO VERIFICAR QUE TODO FUNCIONA

```powershell
# En PC Windows
cd motoshop-app
.\check_health.ps1
# Debe mostrar: API: OK, DB: OK

# Probá todos los endpoints
curl http://localhost:8000/api/alerts/actions/me?date_from=2026-01-01&date_to=2026-12-31
curl http://localhost:8000/api/metrics/inventory-summary
curl http://localhost:8000/api/metrics/sales-trend?periods=12
curl http://localhost:8000/api/metrics/cohortes
curl http://localhost:8000/api/metrics/dormidos
```

**Deadline final**: Martes EOD Semana 2 (antes de Demo Fase 2 el miércoles)
```

---

## RESUMEN DE DEPENDENCIAS ENTRE DEVS

| Dev | Tarea | Depende de | Handoff |
|-----|-------|------------|---------|
| Dev Frontend 1 | 3.2 VENTAS toggles | Dev Backend 1 endpoints | Si no está listo, usar mock |
| Dev Frontend 1 | 3.3 VENDEDORES toggles | Dev Backend 1 parámetros | Si no está listo, usar mock |
| Dev Frontend 2 | 3.1 INICIO gráfica | Dev Backend 1 parámetro `?year=` | Si no está listo, usar mock |
| Dev Frontend 2 | 3.2 DORMIDOS ordenar | Dev Backend 1 campos adicionales | Si no está listo, usar mock |

**Regla general**: Si una dependencia no está lista después de 2 días, escalá en daily standup.

---

## CRONOGRAMA VISUAL

```
Semana 1 (Fase 1 - Bugs críticos):
├─ Dev Frontend 1: PLAN COMPRAS + ALERTAS (8h)
├─ Dev Frontend 2: (sin tareas)
└─ Dev Backend 1: ACCIONES + INVENTARIO (5h)

Semana 2 (Fase 2 - Data quality):
├─ Dev Frontend 1: (sin tareas)
├─ Dev Frontend 2: FORECAST buscador (4h)
└─ Dev Backend 1: VENTAS + COHORTES + DORMIDOS (9h)

Semanas 3-4 (Fase 3 - Enhancements):
├─ Dev Frontend 1: INICIO + VENTAS + VENDEDORES + ABC (19h)
├─ Dev Frontend 2: INICIO gráfica + DORMIDOS + FORECAST + DRIFT (18h)
└─ Dev Backend 1: (sin tareas, soporte)
```

---

**Éxito!** 🚀
