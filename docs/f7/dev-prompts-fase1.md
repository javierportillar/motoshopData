# Prompts para Devs - F7 Frontend Fixes v1 (Fase 1)

**Fecha**: 2026-05-31  
**Uso**: Copiar y pegar cada prompt al dev correspondiente

---

## PROMPT 1: Dev Frontend 1

```
Sos Dev Frontend 1 del proyecto MotoShop. Tu rol es arreglar bugs críticos en el frontend de Next.js/React.

## CONTEXTO DEL PROYECTO

MotoShop es una PWA de análisis de ventas e inventario para una tienda de repuestos de motos. El stack es:
- Frontend: Next.js 14 + React 18 + TypeScript + Tailwind CSS
- UI Components: Design system propio en `motoshop-app/web/components/ui/`
- API: FastAPI corriendo en PC Windows (no necesitás acceso, consumís endpoints remotos)
- Datos: Databricks (backend ya maneja queries)

## TU MISIÓN - FASE 1: BUGS CRÍTICOS (Semana 1)

Tenés 8 horas para arreglar 4 bugs críticos que bloquean el lanzamiento de v1.

### TAREA 1: PLAN COMPRAS - Fix filtros ABC (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: Los filtros ABC (A, B, C) no hacen nada. Cuando el usuario selecciona "A", la tabla no se filtra.

**Qué hacer**:
1. Abrí el archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el filtro ABC (probablemente `abcFilter`)
3. Verificá que el `filter()` se aplique correctamente sobre los datos
4. Asegurate que al cambiar el filtro, la tabla se re-renderice con datos filtrados

**Criterio de aceptación**:
- Al hacer click en "A", solo se muestran productos con clasificación ABC = "A"
- Al hacer click en "B", solo se muestran productos con clasificación ABC = "B"
- Al hacer click en "C", solo se muestran productos con clasificación ABC = "C"
- Al hacer click en "Todas", se muestran todos los productos

**Cómo verificar**:
```bash
cd motoshop-app/web
npm run dev
# Navegá a /plan-compras y probá los filtros
```

---

### TAREA 2: PLAN COMPRAS - Fix filtros urgencia (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: Los filtros de urgencia (alta, media, baja) no muestran resultados. Cuando el usuario selecciona "alta", la tabla queda vacía.

**Qué hacer**:
1. En el mismo archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el filtro de urgencia (probablemente `urgencyFilter`)
3. Verificá que el `filter()` compare correctamente los valores
4. Posible bug: el backend retorna "alta" pero el frontend compara con "Alta" (case sensitivity)

**Criterio de aceptación**:
- Al hacer click en "alta", solo se muestran productos con urgencia = "alta"
- Al hacer click en "media", solo se muestran productos con urgencia = "media"
- Al hacer click en "baja", solo se muestran productos con urgencia = "baja"
- Al hacer click en "Todas", se muestran todos los productos

---

### TAREA 3: PLAN COMPRAS - Fix toggle dormidos (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/plan-compras/page.tsx`

**Problema**: El toggle "Solo dormidos" / "Incluir dormidos" no filtra la tabla.

**Qué hacer**:
1. En el mismo archivo `plan-compras/page.tsx`
2. Buscá el `useState` que maneja el toggle (probablemente `onlyDormidos`)
3. Verificá que el `filter()` filtre por campo `dormido` (boolean o string)
4. Posible bug: el campo se llama `is_dormido` pero el frontend busca `dormido`

**Criterio de aceptación**:
- Al activar "Solo dormidos", solo se muestran productos con `dormido = true`
- Al desactivar, se muestran todos los productos
- El toggle debe ser visualmente claro (activo/inactivo)

---

### TAREA 4: ALERTAS - Fix filtro urgencia (2h)

**Archivo**: `motoshop-app/web/app/(authenticated)/alerts/page.tsx`

**Problema**: Solo se muestran alertas ALTA. Los filtros Media y Baja no muestran nada.

**Qué hacer**:
1. Abrí el archivo `alerts/page.tsx`
2. Buscá cómo se llama al endpoint `/api/alerts/stockout?urgency={urgency}`
3. Verificá que el parámetro `urgency` se pase correctamente
4. Posible bug: el frontend hardcodea `urgency=alta` y no cambia con el filtro

**Criterio de aceptación**:
- Al hacer click en "Alta", se muestran solo alertas de urgencia alta
- Al hacer click en "Media", se muestran solo alertas de urgencia media
- Al hacer click en "Baja", se muestran solo alertas de urgencia baja
- Al hacer click en "Todas", se muestran todas las alertas
- Los contadores al lado de cada filtro deben actualizarse

**Cómo verificar**:
```bash
# En otra terminal, verificá que el backend retorne datos para cada urgencia
curl http://localhost:8000/api/alerts/stockout?urgency=alta
curl http://localhost:8000/api/alerts/stockout?urgency=media
curl http://localhost:8000/api/alerts/stockout?urgency=baja
```

---

## ENTREGABLES

Cuando termines cada tarea:
1. Commit con mensaje: `fix(fase-1): {nombre tarea}`
2. Ejemplo: `fix(fase-1): PLAN COMPRAS filtros ABC funcionando`
3. Push a la rama `main`

## CÓMO VERIFICAR QUE TODO FUNCIONA

```bash
cd motoshop-app/web
npm run dev
# Navegá a:
# - /plan-compras → probá los 3 filtros (ABC, urgencia, dormidos)
# - /alerts → probá los 3 filtros de urgencia
```

## PREGUNTAS

Si tenés dudas, preguntá antes de implementar. No asumas nada.

**Deadline**: Miércoles 10:00 AM (Demo Fase 1 con stakeholder)
```

---

## PROMPT 2: Dev Frontend 2

```
Sos Dev Frontend 2 del proyecto MotoShop. Tu rol es arreglar bugs en el frontend de Next.js/React, específicamente en el módulo de Forecast.

## CONTEXTO DEL PROYECTO

MotoShop es una PWA de análisis de ventas e inventario para una tienda de repuestos de motos. El stack es:
- Frontend: Next.js 14 + React 18 + TypeScript + Tailwind CSS
- UI Components: Design system propio en `motoshop-app/web/components/ui/`
- API: FastAPI corriendo en PC Windows (no necesitás acceso, consumís endpoints remotos)
- Datos: Databricks (backend ya maneja queries)

## TU MISIÓN - FASE 2: BUGS + DATA QUALITY (Semana 2)

Tenés 4 horas para arreglar 1 bug crítico en Forecast.

### TAREA 1: FORECAST - Reemplazar MOCK_SUGGESTIONS (4h)

**Archivo**: `motoshop-app/web/app/(authenticated)/forecast/page.tsx`

**Problema**: El buscador de SKU usa sugerencias hardcodeadas (`MOCK_SUGGESTIONS`) en lugar de buscar en el backend. Por eso solo muestra 5-10 opciones cuando hay cientos de productos.

**Qué hacer**:
1. Abrí el archivo `forecast/page.tsx`
2. Buscá el array `MOCK_SUGGESTIONS` (probablemente al inicio del archivo)
3. Reemplazalo con una llamada al endpoint `/api/products?q={query}&limit=20`
4. Usá el hook `useProducts` que ya existe en `lib/api/hooks.ts`
5. Filtrá los resultados para mostrar solo SKUs que tienen forecast disponible

**Código de referencia** (ya existe en `products/page.tsx`):
```typescript
import { useProducts } from '@/lib/api/hooks';

const { data, error } = useProducts(query, 20, 0);
```

**Lógica sugerida**:
```typescript
// Cuando el usuario escribe en el buscador
const [query, setQuery] = useState('');
const { data: products } = useProducts(query, 20, 0);

// Filtrar solo productos con forecast
const suggestions = products?.items.filter(p => p.has_forecast) || [];
```

**Criterio de aceptación**:
- Al escribir "MOTS" en el buscador, sugiere todos los SKUs que empiezan con "MOTS"
- Al escribir "1234", sugiere todos los SKUs que contienen "1234"
- Si un SKU no tiene forecast, muestra mensaje "Sin predicción disponible"
- Las sugerencias se actualizan en tiempo real mientras el usuario escribe

**Cómo verificar**:
```bash
cd motoshop-app/web
npm run dev
# Navegá a /forecast
# Escribí "MOTS" en el buscador → deben aparecer 20+ sugerencias
# Escribí un SKU específico → debe mostrar la predicción
```

**Endpoint de referencia**:
```bash
curl "http://localhost:8000/api/products?q=MOTS&limit=20&offset=0"
```

---

## ENTREGABLES

Cuando termines:
1. Commit con mensaje: `fix(fase-2): FORECAST buscador usa backend en lugar de mocks`
2. Push a la rama `main`

## PREGUNTAS

Si tenés dudas, preguntá antes de implementar. No asumas nada.

**Deadline**: Lunes EOD (antes de Fase 2 demo el miércoles)
```

---

## PROMPT 3: Dev Backend 1

```
Sos Dev Backend 1 del proyecto MotoShop. Tu rol es arreglar bugs críticos en el backend FastAPI que corre en un PC Windows.

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

## TU MISIÓN - FASE 1: BUGS CRÍTICOS (Semana 1)

Tenés 5 horas para arreglar 2 bugs críticos.

### TAREA 1: ACCIONES - Debug endpoint vacío (3h)

**Archivo**: `motoshop-app/api/src/motoshop_api/alerts/repo.py` (o similar)

**Problema**: El endpoint `/api/alerts/actions/me` retorna array vacío `[]` incluso cuando el usuario ha gestionado alertas.

**Qué hacer**:
1. Abrí el archivo que maneja alertas (buscá `get_my_actions` o similar)
2. Verificá la query SQL que obtiene las acciones del usuario
3. Posibles bugs:
   - El `user_id` no se pasa correctamente a la query
   - La tabla `alert_actions` no tiene datos (verificá con query directa)
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
- El frontend muestra EmptyState si array está vacío

**Cómo verificar**:
```powershell
# En PC Windows
cd motoshop-app
.\start_api.ps1

# En otra terminal
curl http://localhost:8000/api/alerts/actions/me?date_from=2026-01-01&date_to=2026-12-31
# Debe retornar array con acciones o []
```

**Query de debug** (si tenés acceso a Databricks):
```sql
SELECT * FROM app_alert_actions WHERE user_id = 'test_user' LIMIT 10;
```

---

### TAREA 2: INVENTARIO - Fix "SIN NOMBRE" en bodegas (2h)

**Archivo**: `motoshop-app/api/src/motoshop_api/metrics/repo.py`

**Problema**: El endpoint `/api/metrics/inventory-summary` retorna bodegas con nombre "SIN NOMBRE" en lugar del nombre real.

**Qué hacer**:
1. Abrí `motoshop-app/api/src/motoshop_api/metrics/repo.py`
2. Buscá la función `get_inventory_summary()`
3. Verificá la query SQL que obtiene stock por bodega
4. Posible bug: el JOIN con tabla de bodegas está mal o falta
5. Agregá fallback: si nombre es NULL, mostrar "Bodega {id}"

**Query actual** (probablemente algo así):
```python
query = """
SELECT 
    bodega_id,
    SUM(stock) as stock_total,
    SUM(valor) as valor_total
FROM mart_inventario_actual
GROUP BY bodega_id
"""
```

**Query corregida** (con JOIN):
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
- El endpoint retorna bodegas con nombre real (ej: "Bodega Central", "Bodega Norte")
- Si la bodega no tiene nombre en `dim_bodegas`, muestra "Bodega {id}"
- El frontend muestra nombres correctos en `/dashboards/inventario`

**Cómo verificar**:
```powershell
# En PC Windows
curl http://localhost:8000/api/metrics/inventory-summary
# Debe retornar:
# {
#   "bodegas": [
#     {"bodega_id": 1, "nombre": "Bodega Central", "stock": 4024, "valor": 123456},
#     ...
#   ]
# }
```

---

## ENTREGABLES

Cuando termines cada tarea:
1. Commit con mensaje: `fix(fase-1): {nombre tarea}`
2. Ejemplo: `fix(fase-1): ACCIONES endpoint retorna datos correctamente`
3. Push a la rama `main`
4. Reiniciá el servidor: `.\start_api.ps1`

## CÓMO VERIFICAR QUE TODO FUNCIONA

```powershell
# En PC Windows
cd motoshop-app
.\check_health.ps1
# Debe mostrar: API: OK, DB: OK

# Probá los endpoints
curl http://localhost:8000/api/alerts/actions/me?date_from=2026-01-01&date_to=2026-12-31
curl http://localhost:8000/api/metrics/inventory-summary
```

## PREGUNTAS

Si tenés dudas, preguntá antes de implementar. No asumas nada.

**Deadline**: Martes EOD (antes de Demo Fase 1 el miércoles)
```

---

## NOTAS FINALES

1. **Cada dev recibe solo su prompt** (no los de los otros devs)
2. **Daily standup**: 9:00 AM todos los días (15 min)
3. **Bloqueos**: Si un dev se traba más de 30 min, debe escalar en el daily
4. **Commits**: Cada tarea = 1 commit con mensaje claro
5. **Demo**: Miércoles 10:00 AM con stakeholder

**Éxito!** 🚀
