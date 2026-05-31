# MotoShop F7 — Auditoría de producción

**Fecha:** 2026-05-31
**Auditor:** Revisor (contexto fresco, sin influencia del agente que ejecutó F7)
**Método:** Login real (admin/FG28) → curl directo a 31 endpoints → SQL directo contra Databricks SQL Warehouse → lectura cruzada de código repo
**Producción:** `https://app.fragloesja.uk` (Vercel) → `https://api.fragloesja.uk` (CNAME a Render)
**Commits auditados:** `9efa10a` (HEAD `main`, sin commits sin pushear)

---

## Veredicto

**F7 NO está terminado.** De 31 endpoints en producción:

- **10 devuelven HTTP 500** (Internal Server Error)
- **1 devuelve HTTP 422** (contract mismatch frontend↔backend)
- **1 devuelve HTTP 503** (architectural mismatch — products solo en Windows on-premise)
- **1 devuelve HTTP 404** (path inexistente)
- **18 devuelven HTTP 200** — pero 5 de ellos tienen calidad de datos rota o features incompletas

Cero de los 26 bugs reportados por el usuario fue verificado en producción antes de cerrar el commit. El commit log muestra "feat: X funcionando" sin evidencia. Repite el patrón F2-V3 / F3-V6.

---

## 1. Bugs backend — 500 (SQL roto, no cosmético)

### 1.1 SQL Bug — DORMIDOS `/api/metrics/dormidos` → 500

**Síntoma:** "Error al cargar — no se pudieron obtener datos de productos dormidos"

**Causa raíz (CONFIRMADA via SQL directo a Databricks):**

```
[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with name `d`.`ultima_venta` cannot be resolved.
Did you mean one of the following? [`v`.`ultima_venta`, `c`.`ultima_compra`, `d`.`ultima_fecha_venta`, `d`.`dias_sin_venta`, `d`.`cod_bodega`]
```

La columna se llama **`ultima_fecha_venta`**, NO `ultima_venta`.

**Archivo:** `motoshop-app/api/src/motoshop_api/metrics/repo.py`
**Líneas afectadas:** 701, 702 (y por COALESCE en 728)

**Fix:**

```python
# ANTES (línea 701-702):
COALESCE(CAST(v.ultima_venta AS STRING), CAST(d.ultima_venta AS STRING)) AS ultima_venta,
DATEDIFF(CURRENT_DATE, COALESCE(v.ultima_venta, d.ultima_venta)) AS dias_sin_venta

# DESPUÉS:
COALESCE(CAST(v.ultima_venta AS STRING), CAST(d.ultima_fecha_venta AS STRING)) AS ultima_venta,
DATEDIFF(CURRENT_DATE, COALESCE(v.ultima_venta, d.ultima_fecha_venta)) AS dias_sin_venta
```

**Criterio de aceptación:**
```bash
curl -H "Authorization: Bearer $TOK" "https://api.fragloesja.uk/api/metrics/dormidos?limit=500" | jq '.total'
# DEBE devolver entero > 100, no "Internal Server Error"
```

**Quién:** Dev A2 backend
**Estimado:** 15 min (cambio de 2 líneas + commit + verificar curl)

---

### 1.2 SQL Bug — COHORTES `/api/metrics/cohortes` → 500

**Síntoma:** "Error al cargar datos de cohortes"

**Causa raíz (CONFIRMADA):** El SQL en sí funciona (lo corrí directo, devuelve filas). El crash es en **post-procesamiento Python**.

`get_cohortes()` (línea 799-824) llama `_fill_month_gaps(rows)` (línea 734-797) que inyecta entradas con `tasa_recurrencia: None`. Luego construye `CohorteItem(**r)`. El schema Pydantic `CohorteItem` probablemente declara `tasa_recurrencia: float` (no opcional). Pydantic lanza ValidationError → FastAPI devuelve 500.

**Verificación pendiente:** revisar `motoshop-app/api/src/motoshop_api/metrics/schemas.py` para confirmar tipo de `CohorteItem.tasa_recurrencia`.

**Fix:**

Opción A (recomendada) — hacer el campo opcional en schema:
```python
class CohorteItem(BaseModel):
    cohorte_mes: str
    mes_observacion: str
    num_clientes: int
    ticket_promedio: float
    tasa_recurrencia: float | None = None  # <-- antes era float
    muestra_pequena: bool | None = None
```

Opción B — en `_fill_month_gaps`, llenar con `0.0` en vez de `None`:
```python
"tasa_recurrencia": 0.0,  # en vez de None
```

Recomiendo A porque `None` semánticamente significa "no medible" (cohorte sin clientes ese mes), no "0% recurrencia".

**Criterio de aceptación:**
```bash
curl -H "Authorization: Bearer $TOK" "https://api.fragloesja.uk/api/metrics/cohortes" | jq '.cohortes | length'
# DEBE devolver > 30, no "Internal Server Error"
```

**Quién:** Dev A2 backend
**Estimado:** 20 min

---

### 1.3 SQL Bug — SALES_TREND / SALES_DAILY / SALES_MONTHLY → 500

**Síntoma:** Tendencia mensual en INICIO no renderiza. Toggles "Diaria" y "Mensual" en VENTAS crashean.

**Causa raíz (CONFIRMADA via SDK directo):**

```
AttributeError: 'dict' object has no attribute 'as_dict'
```

`databricks-sdk` upgrade rompió el contrato de `parameters=`. Antes aceptaba `list[dict]`; ahora exige objetos tipados `StatementParameterListItem`.

**Archivo:** `motoshop-app/api/src/motoshop_api/metrics/repo.py`
**Método:** `_query()` línea 1146-1167

**Fix:**

```python
# ANTES:
def _query(self, sql: str, parameters: list[dict] = None) -> list[dict]:
    result = self._w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=self._wh_id,
        wait_timeout="50s",
        parameters=parameters or [],
    )

# DESPUÉS (importar el tipo correcto):
from databricks.sdk.service.sql import StatementParameterListItem

def _query(self, sql: str, parameters: list[dict] = None) -> list[dict]:
    typed_params = [
        StatementParameterListItem(
            name=p["name"],
            value=p["value"]["stringValue"] if "stringValue" in p["value"] else str(p["value"].get("intValue")),
            type=p.get("type", "STRING"),
        )
        for p in (parameters or [])
    ]
    result = self._w.statement_execution.execute_statement(
        statement=sql,
        warehouse_id=self._wh_id,
        wait_timeout="50s",
        parameters=typed_params,
    )
```

Verificar versión del SDK con `uv pip list | rg databricks-sdk`. Si está pineado en pyproject.toml a un rango que rompe, **DOWNGRADE temporal a la versión que funcionaba** (probablemente `<0.40.0`), y abrir issue para migrar al schema nuevo.

**Endpoints afectados (todos un solo fix):**
- `/api/metrics/sales-trend` (3 variantes: default, ?year=2025, ?year=2024)
- `/api/metrics/sales-daily?days=N`
- `/api/metrics/sales-monthly`
- DORMIDOS (también pasa `:limit`, `:offset`) — fix 1.1 + este se resuelven juntos

**Criterio de aceptación:**
```bash
for p in sales-trend "sales-trend?year=2025" "sales-daily?days=7" "sales-monthly"; do
  curl -s -o /dev/null -w "$p: %{http_code}\n" -H "Authorization: Bearer $TOK" \
    "https://api.fragloesja.uk/api/metrics/$p"
done
# DEBE devolver 200 en todos
```

**Quién:** Dev A2 backend
**Estimado:** 1.5h (cambio de tipo + tests locales + deploy + verificación)

---

### 1.4 RECOMMENDATIONS `/api/metrics/recommendations` → 500

**Síntoma:** Página `/acciones` vacía — "No dice nada"

**Causa raíz (CONFIRMADA):** El endpoint llama internamente `repo.get_dormidos(...)` → que crashea con bug 1.1. Cascada de error.

**Fix:** Se resuelve al cerrar bug 1.1 (dormidos).

**Criterio de aceptación:**
```bash
curl -H "Authorization: Bearer $TOK" "https://api.fragloesja.uk/api/metrics/recommendations" | jq '.total'
# DEBE devolver entero > 0
```

---

## 2. Bugs backend — Contract mismatch

### 2.1 VENDEDORES `period=monthly` → 422

**Síntoma:** "Karol sola durante mucho tiempo, después aparece Francisco" — la página llama 3 queries en paralelo con `period=month`, `historical`, `6months`, y el toggle UI manda otro valor que falla.

**Causa raíz (CONFIRMADA):**
```
{"detail":[{"type":"literal_error","loc":["query","period"],
"msg":"Input should be 'month', 'historical' or '6months'","input":"monthly"}]}
```

Backend valida con `Literal["month", "historical", "6months"]` (router.py línea 240).
La página `vendedores/page.tsx` línea 131-133 envía `"month"`, `"historical"`, `"6months"` — correcto.
Pero el botón de toggle UI manda `"monthly"` en algún punto (hay que rastrear el setter `setTab`).

**Verificación pendiente:** revisar `setTab` en `vendedores/page.tsx` para identificar dónde se manda "monthly".

**Fix:** unificar el alfabeto. Recomiendo cambiar backend a aceptar también `"monthly"` como alias o cambiar el componente UI para enviar `"month"`.

**Quién:** Dev T2 frontend (UI envía valor inválido) + verificar backend
**Estimado:** 30 min

---

## 3. Bugs arquitectura — Endpoints inexistentes en cloud

### 3.1 PRODUCT_VH10025 → 503

**Síntoma:** Click en "Ver SKU" desde Alertas → redirige a `/products/VH10025` → "producto no encontrado"

**Causa raíz (CONFIRMADA):**
```json
{"detail":"Funcionalidad no disponible en cloud. Requiere el sistema operativo encendido.
Predicciones y alertas están disponibles 24/7.","status":"degraded"}
```

Render expone `/api/products/*` como degradado a propósito (sólo Windows on-premise tiene MySQL). La PWA está apuntando a Render via `api.fragloesja.uk`. Cuando Alertas linkea a `/products/:sku`, el backend cloud responde 503.

**Fix — dos opciones:**

A. Hacer fallback **desde la PWA al Windows API** cuando Render devuelve 503 (cliente intenta `cloud-api.fragloesja.uk` → si 503, intenta `windows-api.fragloesja.uk`). Esto es lo que documenta el roadmap híbrido (F6-D).

B. Quitar el link "Ver SKU" desde Alertas si estamos en cloud-only. Simpler pero pierde funcionalidad.

**Decisión arquitectural:** lo dejo para Revisor + humano. Sospecho que A es lo correcto, pero requiere que Windows esté disponible (Dev W instale auto-pull).

**Quién:** Dev T frontend (decisión A) o Dev T2 (decisión B)
**Estimado:** 2h (A) / 15 min (B)

---

### 3.2 STOCK_VH10025 → 404

Mismo problema. `/api/stock/:sku` también es Windows-only.

---

## 4. Bugs backend — Calidad de datos (200 pero contenido roto)

### 4.1 INVENTARIO — "SIN NOMBRE 4024 100%"

**Síntoma:** Stock por bodega muestra solo "SIN NOMBRE" con 100%.

**Causa raíz (CONFIRMADA via SQL directo):**

La query devuelve UNA sola fila: `cod_bodega=""`, `nom_bodega="SIN NOMBRE"`, `cantidad=4024, rows=4829`. O sea **TODOS los 4,829 productos en `mart_inventario_actual` tienen `cod_bodega=''` y `nom_bodega=''` (cadena vacía, no NULL)**.

El COALESCE del fix `4e1e8c4` no funciona porque COALESCE no atrapa `""`. Pero más importante: **los datos están mal en el mart**.

**Fix de dos capas:**

a. **Inmediato (cosmético — backend):** cambiar línea 630-631 de `inventory-summary`:
```sql
-- ANTES:
COALESCE(nom_bodega, CONCAT('Bodega ', cod_bodega)) AS nom_bodega
-- DESPUÉS:
COALESCE(NULLIF(nom_bodega, ''), NULLIF(CONCAT('Bodega ', cod_bodega), 'Bodega '), 'Sin clasificar') AS nom_bodega
```

b. **Real (data — notebook silver/gold):** investigar por qué `dim_bodega` o el join no está poblando estos campos. Probable que el silver `dim_bodega` tenga la info pero el join con `mart_inventario_actual` la pierda, O que bronze venga con strings vacíos del MySQL.

**Quién:** (a) Dev A2 backend, (b) Dev D Databricks
**Estimado:** (a) 10 min · (b) 1-2h investigación

---

### 4.2 VENDEDORES — Entry con NIT vacío

**Síntoma:** "Después de un tiempo aparece otro vendedor (Francisco)". Realmente: en histórico aparecen 3 entries: KAROL (6,311 facturas), `""` con 27 facturas $3.66M, FRANCISCO con 1 factura $42k.

**Causa raíz (CONFIRMADA):** `silver.fact_ventas` tiene 27 facturas con `nit_vendedor=''` y `nombre_vendedor=''`. Data sucia en bronze.

**Fix sugerido — backend:**
```sql
WHERE nit_vendedor IS NOT NULL AND nit_vendedor != ''
```
en `get_vendedores_summary` (línea 866).

Pero esto OCULTA un problema real. Mejor:
- Backend: agrupar las "sin vendedor" como categoría aparte ("Sin asignar") en vez de filtrar
- Investigar en bronze por qué hay 27 facturas sin vendedor (¿bug en POS? ¿registros antiguos?)

**Quién:** Dev A2 backend (display)
**Estimado:** 30 min

---

### 4.3 ALERTAS — 46 alta / 0 media / 0 baja

**Síntoma:** Todas las alertas son "alta", no hay distribución.

**Causa raíz (CONFIRMADA via SQL):**
```sql
SELECT urgencia, COUNT(*) FROM motoshop.gold.alertas_quiebre GROUP BY urgencia
-- Devuelve: alta=46
```

NO hay registros con `urgencia='media'` ni `'baja'`. La distribución se hace en el notebook `12_mart_alertas_quiebre` (o similar). Probablemente la lógica de clasificación tiene un bug: `if dias_hasta_quiebre <= 0: 'alta'` solo, sin rama `media`/`baja`.

**Fix:** revisar el notebook Databricks que construye `alertas_quiebre` y agregar lógica:
- `alta`: dias_hasta_quiebre ≤ 3
- `media`: dias_hasta_quiebre 4-7
- `baja`: dias_hasta_quiebre 8-14

**Quién:** Dev D Databricks
**Estimado:** 1h (revisar notebook + commit + re-correr task on-demand)

---

### 4.4 DRIFT — alertas_drift vacío (activas 0, cargas 0)

**Síntoma:** "activas 0, cargas 0, THOLD 30% — no entiendo"

**Causa raíz (CONFIRMADA):** `motoshop.gold.alertas_drift` tiene **0 filas**. El notebook que la puebla no corrió, o corrió pero no encontró drift, O la tabla nunca se inicializó con datos demo.

**Fix:**
- Inmediato: el frontend debe mostrar un empty-state honesto: "No se ha detectado drift en las últimas mediciones. La tabla se actualiza cada semana." Plus glossary.
- Real: revisar workflow Databricks → task que poblaba `alertas_drift`. Posible que sea uno de los 3 tasks fallando del F7-E-FIX1.

**Quién:** Dev D (data) + Dev T2 (UX empty state)
**Estimado:** 2h total

---

### 4.5 FORECAST — Solo 2 categorías visibles

**Síntoma:** "Veo muy pocas opciones para estimar"

**Causa raíz (CONFIRMADA via SQL):**

Datos en `gold.forecast_categoria`:
- IV2 → 636 filas, max business_date 2026-05-28 ✅
- IV4 → 11 filas, max 2026-05-16 ✅
- SIN_GRUPO → 38 filas, max **2025-09-30** ❌ (datos viejos)

La query filtra `business_date >= DATE_SUB(CURRENT_DATE(), 30)`. SIN_GRUPO no entra porque sus últimos datos son de hace 8 meses.

**ADEMÁS:** el usuario espera "buscador de SKUs" pero la página es **forecast por CATEGORÍA**, no por SKU. **Mismatch conceptual entre lo que dice el commit `8fca15e FORECAST buscador usa backend en vez de mocks` y lo que el usuario espera.**

**Decisión necesaria del humano:** ¿Mantener forecast por categoría (ADR-0020) o agregar forecast por SKU (vuelve al problema F4-FIX1 — sparse demand)?

Si se mantiene por categoría, hay que:
1. Renombrar la página "Forecast por categoría" para que no confunda
2. Documentar las 3 categorías y por qué solo 2 son recientes
3. Quitar el buscador (no aplica) y poner dropdown con las 3 categorías

**Quién:** Decisión arquitectural — Revisor + humano
**Estimado:** 1h (rediseño UX) + 30 min implementación

---

### 4.6 COHORTES — 1 cliente por cohorte, 100% recurrencia

**Síntoma:** "Solo sale 1 cliente, ticket promedio y recurrencia 100%"

**Causa raíz (CONFIRMADA via SQL):**

`mart_cohortes_clientes` agrupa por `nit_cliente`. La mayoría de las cohortes tienen exactamente **1 cliente** (uno que compró por primera vez ese mes y volvió). Eso da `tasa_recurrencia = 1.0` (100%) cuando ese único cliente compra de nuevo.

Esto NO es bug — es **dispersión real del dataset**. Una tienda chica con pocos clientes recurrentes únicos.

**Fix:** UX honesto. El frontend debe:
- Mostrar el flag `muestra_pequena` (ya viene del backend cuando `num_clientes < 5`)
- Empty-state explicativo: "Cohortes con menos de 5 clientes tienen estadística no significativa. Esto refleja un dataset pequeño, no un error."

**Quién:** Dev T2 frontend
**Estimado:** 30 min

---

## 5. Bugs frontend

### 5.1 HOME — Loop de re-render

**Síntoma:** "Se queda cargando y no sale nada en inicio, bueno cargó pero se está renderizando varias veces — vacío → data → vacío → data"

**Causa raíz (HIPÓTESIS — necesita confirmación en console):**

Tres factores en cadena en `app/(authenticated)/page.tsx` y `lib/auth/store`:

1. **Zustand persist hidratación**: `useAuthStore((s) => s.role)` retorna `undefined` en server, luego rehidrata en cliente → re-render. (Patrón clásico Next.js + Zustand persist.)
2. **5 hooks SWR en paralelo** (`useSalesSummary`, `useInventorySummary`, `useAlerts`, `useDormidos`, `useSalesTrend`) — cada uno entra/sale de `isLoading`. La línea 28-29 evalúa OR de los 5 isLoadings, así que cualquiera que entre a loading vuelve a mostrar el skeleton.
3. **`useDormidos` y `useSalesTrend` crashean con 500** — SWR setea `error`, `isLoading: false`. Pero la página NO chequea esos errores, solo `sales.error` (línea 56). Entonces dormidos.data queda undefined permanentemente → componente parpadea.

**Fix:**

a. **Persistencia auth**: añadir guard `hasHydrated` en `useAuthStore` para no renderizar nada hasta que el store esté hidratado.

```tsx
const hasHydrated = useAuthStore.persist?.hasHydrated();
if (!hasHydrated) return <SkeletonHome />;
```

b. **Estabilizar loading**: cambiar el OR a AND? No — preferir mostrar lo que SÍ tiene data y mostrar skeleton solo para las cards que faltan. Loading global es peor UX.

c. **Manejar errors silenciosos**: para dormidos / trend que crashean, mostrar fallback en la card específica, no romper toda la página.

**Quién:** Dev T2 frontend
**Estimado:** 1.5h

---

### 5.2 VENTAS — "Application error: a client-side exception has occurred"

**Síntoma:** Página de Ventas crashea con error de cliente.

**Causa raíz (HIPÓTESIS — necesita console):**

`dashboards/ventas/page.tsx` líneas 97-99:
```tsx
const d = sales.data!;
const dd = salesDaily.data!;
const dh = salesHistorical.data!;
```

Los `!` (non-null assertions) son peligrosos. `salesDaily.data` es undefined porque `/api/metrics/sales-daily` devuelve 500 (bug 1.3). El guard de la línea 82 solo chequea el data del tab activo (por default "mensual"), no los otros dos. Cuando `useSalesTrend(9)` también falla (bug 1.3), `trend.error` se setea pero el código no lo maneja.

**Cadena exacta de crash:** default tab "mensual" → guard pasa porque `sales.data` existe → llega a render → `renderMensual()` accede a `d.top_skus.length`, etc. (esto SÍ funciona porque `sales.data` está bien). Hasta acá no debería crashear.

**Posible crash adicional:** el `<SalesTrendChart>` recibe array vacío (`trend.data?.items.map ?? []`). Si recharts/recharts-like espera al menos 1 item → throw.

**Acción inmediata:** verificar console de browser. Abrir DevTools → Console → click en error stack para ver la línea exacta.

**Fix general:**

1. Resolver bug 1.3 (sales-trend, sales-daily, sales-monthly 500) → desaparecen los `undefined`.
2. Reemplazar `!` por guards explícitos: `if (!d) return <ErrorState />`.
3. SalesTrendChart debe manejar `data.length === 0` sin crashear.

**Quién:** Dev T2 frontend (después de bug 1.3 resuelto)
**Estimado:** 1h

---

### 5.3 INICIO — KPIs no clickeables (FALSO POSITIVO)

**Síntoma:** "Ya no me lleva a ninguna pagina si presiono en valor inventario"

**Realidad (CONFIRMADA via lectura de código):** Los 4 KPIs SÍ están envueltos en `<Link>`. Líneas 87, 103, 119, 135 de `app/(authenticated)/page.tsx`. El commit `b8be0e1 INICIO KPIs clickeables` está implementado.

**Pero:** cuando el usuario hace click en "Valor inventario" y abre `/dashboards/inventario`, esa página existe y carga el endpoint que SÍ funciona (inventory-summary 200). El problema puede ser:

a. El click DSP carga la página pero como muestra "SIN NOMBRE 100%" el usuario asume que "no hay info" y vuelve.
b. El click se perdió porque el `<Card hover>` consume el evento sin propagarlo al Link (verificar handleClick).
c. El usuario está viendo cache vieja desde antes del commit b8be0e1.

**Acción inmediata:** abrir DevTools → click en "Valor inventario" → verificar si navega a `/dashboards/inventario`. Si navega, no es bug — es expectativa.

**Si NO navega:** revisar si `<Card>` tiene su propio `onClick` interceptando.

**Quién:** Dev T2 verificación
**Estimado:** 15 min

---

### 5.4 INICIO — Tendencia sin comparativa año anterior

**Síntoma pedido por usuario:** "Me gustaría que también se vea la gráfica de tendencia del año anterior, en un solo grafo con diferentes colores."

**Realidad:** No implementado. `SalesTrendChart` recibe UNA serie (`valor`). No soporta 2 series.

**Fix:**

1. Backend: endpoint `/api/metrics/sales-trend?year=YYYY` ya existe (cuando resuelva el bug 1.3). Hay que llamarlo 2 veces (actual + anterior) y devolver `items_actual[]` + `items_anterior[]`.
2. Frontend: refactorear `SalesTrendChart` para aceptar opcional `compareData` y renderizar 2 series con colores distintos.

**Quién:** Dev A2 + Dev T2 (coordinados)
**Estimado:** 3h (backend 1h + frontend 2h)

---

### 5.5 PLAN COMPRAS — Filtros no filtran

**Síntoma:** "Filtros ABC A/B/C no hacen nada. Cuando filtro por Alta/Media/Baja no aparece nada. Cuando oprimo solo dormidos no hace nada."

**Causa raíz (HIPÓTESIS):**

El backend NO filtra. Los filtros son **client-side** (`filterAbc`, `filterUrgencia`, `filterDormido` en estado React, líneas 21-23 de `plan-compras/page.tsx`). Hay que ver dónde se aplica el filter sobre `data.items`.

Hechos:
- API devuelve items con `urgencia: null` en TODOS (verificado en respuesta). Si filtras por `urgencia == "alta"` → array vacío.
- API devuelve items con `abc: "A"` y `abc: "B"` mezclados (vi ambos en respuesta).
- `dormido` viene `true` o `false` correctamente.

**Por qué Alta/Media/Baja vacía:** porque `urgencia` viene `null` para casi todos (data quality bug — la columna `al.urgencia` viene de `alertas_quiebre`, que como vimos en bug 4.3 solo tiene "alta" para SKUs específicos; los demás vienen del LEFT JOIN con NULL).

**Por qué ABC A no filtra:** porque hay items duplicados con distintos ABC (vi el mismo SKU `91204-GBG-850S` con abc=A y abc=B en la misma respuesta — eso es un bug separado de duplicación por LEFT JOIN con `mart_rotacion_abc`).

**Fix:**

a. **Backend:** desduplicar `plan-compras` en SQL (`SELECT DISTINCT` o `GROUP BY sku`).
b. **Backend:** propagar `urgencia` correctamente desde alertas (después de bug 4.3 resuelto).
c. **Frontend:** verificar lógica de filtro client-side. Probablemente OK, pero confirmar.

**Quién:** Dev A2 backend (a, b) + Dev T2 verificación (c)
**Estimado:** 1.5h backend + 30 min frontend

---

### 5.6 FORECAST — Buscador con poquísimas opciones

Ver bug 4.5. La página es por categoría, no por SKU. El "buscador" como concepto no aplica. Hay que rediseñar la página.

---

## 6. Bugs pedagógicos (usuario explícito: "no entiendo")

Estos NO son bugs técnicos pero el usuario los marcó. Cada uno requiere copy explicativo en la página.

| Bug | Página | Acción |
|---|---|---|
| 6.1 ABC sin explicación | `/dashboards/abc` | Agregar tooltip con: "Análisis ABC = clasificación de productos por ingreso. A=80% de las ventas / B=15% / C=5%. Usá A para garantizar stock, C para liquidar." |
| 6.2 Forecast 7/14/30 ambiguo | `/forecast` | Aclarar si es horizonte acumulado o ventana. Mostrar como "demanda esperada en los próximos 7 días", etc. |
| 6.3 Drift sin glosario | `/drift` | Agregar leyenda: "Drift = desviación entre lo predicho y lo real. WAPE >30% = re-entrenar modelo. Activas = pasaron threshold ahora. Resueltas = volvieron a rango." |
| 6.4 Cohortes confuso | `/cohortes` | Empty-state cuando muestra_pequena=true: "Cohortes con <5 clientes son no significativas. Datos disponibles desde 2024-01." |

**Quién:** Dev T2 frontend
**Estimado:** 2h total (30 min cada uno)

---

## Resumen ejecutivo

### Por severidad

**P0 — Rompe demo (10 bugs):** 1.1, 1.2, 1.3 (3 sub-bugs), 1.4, 4.1, 5.1, 5.2, 5.5 (filtros vacíos)
**P1 — Datos mal (5 bugs):** 4.1, 4.2, 4.3, 4.4, 4.5
**P2 — Features faltantes (3 bugs):** 5.4 (comparativa año), 4.5 (rediseño forecast), 3.1 (fallback productos)
**P3 — Pedagógico (4 bugs):** 6.1, 6.2, 6.3, 6.4

### Plan en olas

**Ola 1 — Backend SQL (Dev A2)** · 3h
- Bug 1.3: typed parameters SDK → resuelve sales-trend, sales-daily, sales-monthly, + parte de dormidos
- Bug 1.1: column name dormidos → resuelve dormidos + recommendations (cascada)
- Bug 1.2: cohortes Pydantic schema

**Ola 2 — Datos y queries (Dev A2 + Dev D)** · 4h
- Bug 4.1: nom_bodega cosmético inmediato (backend) + investigación notebook (Dev D)
- Bug 4.2: filtro NIT vacío vendedores
- Bug 4.3: notebook alertas_quiebre — agregar lógica media/baja (Dev D)
- Bug 4.4: investigar por qué alertas_drift vacío (Dev D)
- Bug 5.5: desduplicar plan-compras + propagar urgencia

**Ola 3 — Frontend** · 5h
- Bug 5.1: home re-render (Zustand hydration guard + per-card error states)
- Bug 5.2: ventas crash (después de Ola 1)
- Bug 2.1: vendedores contract mismatch
- Bug 4.6: cohortes empty-state honesto
- Bug 4.5: rediseño forecast por categoría
- Bug 6.x: copy pedagógico (4 dashboards)

**Ola 4 — Arquitectura** · 2h
- Bug 3.1: fallback PWA Windows API o quitar link

**Total estimado:** ~14 horas de trabajo (3 devs en paralelo: ~5h reales).

### Discipline fix (ESTO ES CRÍTICO)

Cada bug se cierra solo cuando:

1. Commit con el fix
2. **Curl directo a producción** con el comando en `criterio de aceptación` que devuelve 200 + estructura esperada
3. Captura del response en el PR description o commit body

Esto NO se hizo en F7. Por eso 10 endpoints están en 500 con commits que dicen "funcionando".

---

## Datos auditados

- `docs/audit/raw_responses.json` — 31 endpoints con status, time, body completo
- Queries SQL directas a Databricks confirmando 7 root causes
- Lectura de:
  - `motoshop-app/api/src/motoshop_api/metrics/repo.py` (1181 líneas)
  - `motoshop-app/api/src/motoshop_api/metrics/router.py` (369 líneas)
  - `motoshop-app/web/app/(authenticated)/page.tsx` (383 líneas)
  - `motoshop-app/web/app/(authenticated)/dashboards/ventas/page.tsx` (323 líneas)
  - `motoshop-app/web/app/(authenticated)/layout.tsx` (37 líneas)
  - `motoshop-app/web/lib/api/hooks.ts` (relevant slice)

**Auditor sign-off:** Revisor — 2026-05-31
