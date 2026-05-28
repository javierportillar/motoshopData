# Plan F1-FIX2 · Cierre limpio de F1

> Sprint correctivo final de F1. Cubre **solo** las 2 carencias menores que quedaron tras F1-FIX1 y que bloquean el cierre limpio del gate. Una vez que este sprint termine, F1 ✅ y F2 abre.
>
> **Antecedentes:** [`docs/plan-f1-fix1.md`](plan-f1-fix1.md) resolvió 11 de 13 ítems. Los 2 restantes son:
>
> 1. ❌ **Capturar las 3 evidencias faltantes** (V6 paginación, V7 schema drift, C-1 stock real). Los notebooks fueron reescritos pero no hay constancia versionada de su ejecución.
> 2. ❌ **Actualizar SEGUIMIENTO §F1** con el estado real post-FIX1 (V6/V7 a ✅, KPIs medidos, nota de sesión).

---

## 1 · Lo que NO entra en este sprint

### C-5 / B-3 · Credenciales en README *(deferido indefinidamente)*

[`motoshop-app/api/README.md`](../motoshop-app/api/README.md) líneas 46-53 siguen documentando `admin/FG28`, `vendedor1/FG28`, `gerente1/FG28`.

**Decisión humana 2026-05-28 (Sesión 16):** las credenciales se mantienen así "hasta nuevo aviso". Se sube de categoría como **R2 · deuda extendida** en SEGUIMIENTO §Tablero de riesgos vivos, con el mismo modelo que R1 (passwords MySQL en historial).

**Triggers de re-evaluación obligatorios:**
- Si la API se mueve a otra red más expuesta.
- Si se introduce algún rol con permisos de escritura (cualquier `POST/PUT/PATCH/DELETE` no metadata).
- Si la PWA pasa a usuarios externos al equipo.
- Si los logs del túnel Cloudflare muestran tráfico sospechoso.

Cualquiera de los 4 → rotación obligatoria + limpieza README + revisión de accesos previos. Hasta entonces: **no se toca** y se considera deuda consciente.

---

## 2 · Sprint F1-FIX2 · 3 tareas

### Tarea 1 · Evidencia V6 — paginación de tablas grandes

**Por qué:** [`notebooks/bronze/04_check_large_tables.py`](../notebooks/bronze/04_check_large_tables.py) fue reescrito en F1-FIX1.A-1 con paginación real (row_number + chunks + union + verify count == total). Falta ejecutarlo y capturar el output.

**Pre-requisitos:**
- `motoshop.bronze.detfventas` y `motoshop.bronze.detcompras` ya materializados para `ingest_date = '2026-05-28'`.

**Pasos para el ejecutor:**

1. En Databricks: abrir `notebooks/bronze/04_check_large_tables.py`.
2. Setear widget `ingest_date = 2026-05-28`.
3. Run all.
4. Copiar el output de las celdas (las que imprimen `detfventas: total=X, distinct=Y, chunks=Z` y el VEREDICTO final).
5. Pegar en `notebooks/bronze/_runs/v6_pagination_2026-05-28.md` con esta plantilla:

```markdown
# V6 · Paginación de tablas grandes — 2026-05-28

Notebook: `notebooks/bronze/04_check_large_tables.py`
Ejecutado: 2026-05-28 HH:MM
ingest_date: 2026-05-28
Chunk size: 5000

## detfventas
- total: 27,747
- distinct_after_pagination: 27,747
- chunks: 6
- status: OK

## detcompras
- total: 11,623
- distinct_after_pagination: 11,623
- chunks: 3
- status: OK

## Veredicto V6
✅ OK — paginación cubre el total sin duplicados ni huecos para ambas tablas.
```

> Si el output real no es exactamente esto (los conteos pueden variar por nuevas ventas), reportar los números reales y ajustar.

**Acceptance criteria:**
- El archivo existe y muestra **distinct_after_pagination == total** para ambas tablas con N > 0.
- El status es OK para ambas. Si alguno es FAIL, F1-FIX2 no cierra hasta resolver.

---

### Tarea 2 · Evidencia V7 — schema drift entre 2 ingest_dates

**Por qué:** [`notebooks/bronze/05_schema_drift.py`](../notebooks/bronze/05_schema_drift.py) fue reescrito en F1-FIX1.A-2 para comparar esquemas entre 2 fechas. Pero los widgets default son `ingest_date_a = ingest_date_b = 2026-05-28` — si se ejecuta así, compara la misma fecha contra sí misma y pasa trivialmente. Hay que ejecutarlo con **2 fechas reales y distintas**.

**Pre-requisitos:**
- Necesitamos 2 `ingest_date`s materializadas. Hoy solo hay `2026-05-28`.

**Pasos para el ejecutor:**

1. En el PC Windows, generar una segunda fecha forzando el argumento del dump:
   ```powershell
   cd C:\Users\MotoShop\Documents\javidevmoto
   .\.venv-infra\Scripts\Activate.ps1
   python infra\dump_to_cloud.py --tables-core --ingest-date 2026-05-29
   ```
   Esto sube los Parquet al UC Volume bajo `ingest_date=2026-05-29` (la data es la misma del 28, lo que se compara es el esquema).

2. En Databricks: ejecutar `notebooks/bronze/02_ingest_all_bronze.py` con widget `ingest_date = 2026-05-29` para materializar la partición.

3. Ejecutar `notebooks/bronze/05_schema_drift.py` con widgets:
   - `ingest_date_a = 2026-05-28`
   - `ingest_date_b = 2026-05-29`

4. Pegar el output en `notebooks/bronze/_runs/v7_drift_2026-05-28.md`:

```markdown
# V7 · Schema drift entre 2 ingest_dates — 2026-05-28

Notebook: `notebooks/bronze/05_schema_drift.py`
Ejecutado: 2026-05-28 HH:MM
ingest_date_a: 2026-05-28
ingest_date_b: 2026-05-29 (dump forzado con `--ingest-date`, misma data, propósito: validar drift)

## Resultados
Tablas estables: 12/12
  OK bodegas
  OK sucursales
  OK formapago
  OK subproduct
  OK productos
  OK preciosxpro
  OK terceros
  OK auxinventario
  OK facventas
  OK detfventas
  OK compras
  OK detcompras

Sin drift detectado.

## Veredicto V7
✅ OK — esquema estable entre las 2 ingest_dates.
```

**Acceptance criteria:**
- El archivo muestra **2 fechas distintas** en `ingest_date_a` y `ingest_date_b` (si son iguales, V7 sigue 🔴).
- Las 12 tablas en estado `OK`. Si hay drift, el ejecutor debe documentarlo (no es necesariamente FAIL de F1 — puede ser sgHermes que cambió un campo — pero requiere análisis).

> **Nota:** la partición `2026-05-29` queda en bronze como artefacto del test. Puede borrarse luego con `DELETE FROM motoshop.bronze.<tabla> WHERE ingest_date='2026-05-29'` o dejarse. No afecta producción.

---

### Tarea 3 · Evidencia C-1 — stock real vs SQL directo

**Por qué:** la auditoría F1-FIX1 confirmó (vía `errores.txt`) que `MOTS1297` devuelve `total=691.0`. Falta documentarlo en un archivo limpio en `_runs/` que demuestre el cuadre 1:1 con MySQL.

**Pasos para el ejecutor:**

1. En el PC Windows:
   ```powershell
   # API
   $token = (Invoke-RestMethod -Uri http://localhost:8000/auth/login -Method POST -ContentType "application/json" -Body '{"username":"admin","password":"<password actual>"}').access_token
   Invoke-RestMethod -Uri "http://localhost:8000/products/MOTS1297/stock" -Headers @{"Authorization"="Bearer $token"} | ConvertTo-Json -Depth 4
   ```

2. SQL directo contra MySQL:
   ```powershell
   python -c "
   import mysql.connector
   conn = mysql.connector.connect(host='localhost', port=3306, user='api_read', password='<pwd>', database='motoshop2024', charset='utf8')
   c = conn.cursor()
   c.execute(\"SELECT codprod, COUNT(*) as cnt, SUM(valor3) as total FROM auxinventario WHERE codprod='MOTS1297'\")
   for r in c.fetchall(): print(r)
   conn.close()
   "
   ```

3. Pegar ambos outputs en `notebooks/api/_runs/c1_stock_real_2026-05-28.md`:

```markdown
# C-1 · Stock real desde auxinventario — 2026-05-28

SKU de prueba: **MOTS1297** ("ACEITE CASTROS 20 W 50")

## Respuesta de la API
```json
{
  "sku": "MOTS1297",
  "nomprod": "ACEITE CASTROS 20 W 50",
  "total": 691.0,
  "by_bodega": [...]
}
```

## SQL directo en MySQL
```sql
SELECT codprod, COUNT(*) as cnt, SUM(valor3) as total
FROM auxinventario
WHERE codprod = 'MOTS1297';
```
Resultado: `('MOTS1297', 640, 691.0)`

## Cuadre
- API total: **691.0**
- SQL SUM(valor3): **691.0**
- ✅ Cuadran 1:1 → Regla de Oro #3 cumplida para este SKU.

## Nota
La columna `auxinventario.codbod` está vacía en la BD actual, por lo que el desglose por bodega usa `coalesce('SIN_BODEGA')`. Esto es limitación de los datos fuente, no del código. Documentado en docstring de `stock/repo.py`.
```

**Acceptance criteria:**
- El archivo muestra un SKU con N > 0.
- API total == SQL SUM(valor3). Si no cuadran, NO se cierra C-1.
- (Opcional pero recomendado) repetir con 1 SKU adicional para robustecer.

---

### Tarea 4 · Actualizar SEGUIMIENTO.md §F1

**Por qué:** el ejecutor cerró el sprint pero no tocó SEGUIMIENTO. Hoy sigue diciendo F1 🟡 con V6/V7 🔴.

**Cambios concretos:**

1. **Cabecera global:**
   ```
   F0 ✅  F1 ✅  F2 🟡  F3 ⬜  F4 ⬜  F5 ⬜  F6 ⬜
   ```
   y `Fase activa: Fase 2 · Silver + PWA MVP`.

2. **Verificaciones críticas F1:**
   - V1 ✅ (ya estaba).
   - V2 ⚠️ con referencia a R3 (deuda aceptada).
   - V3 ✅ (ya estaba).
   - V4 ✅ — **cambiar de ⚠️ a ✅** (timing-safe implementado en B-4, test `test_login_timing_is_similar` passing).
   - V5 ✅ (ya estaba).
   - V6 ✅ — **cambiar de 🔴 a ✅** con referencia a `_runs/v6_pagination_2026-05-28.md`.
   - V7 ✅ — **cambiar de 🔴 a ✅** con referencia a `_runs/v7_drift_2026-05-28.md`.

3. **Entregables Track A:**
   - 04 y 05 a ✅ (reescritos en F1-FIX1).
   - K-3 ✅ con `_runs/k3_five_runs_2026-05-28.md`.

4. **Entregables Track T:**
   - Stock 🔴 → ✅ con referencia a `_runs/c1_stock_real_2026-05-28.md`.
   - Rate limit 🔴 → ✅ (10/min implementado).
   - Tests ⚠️ → ✅ con cobertura 79%.
   - **README con credenciales sigue 🔴** — explícito, con nota: *"Deuda extendida aceptada (R2). No se corrige por decisión humana 2026-05-28 (Sesión 16). Triggers de re-evaluación en R2."*

5. **Tabla de KPIs F1:**
   - Tiempo ingesta diaria: ✅ 31-37s en 5 corridas.
   - **Latencia `/stock` p95: ⚠️ 781ms (>500ms)** — no cumple meta. Mitigación: cache en memoria (R-X2) a abordar en F2 si la PWA lo demanda.
   - 5 corridas: ✅ 5/5.
   - Cobertura tests: ✅ 79% global, 89-90% por módulo.

6. **Tablero de riesgos vivos — actualizar R2:**
   - Estado: 🟡 → 🟡 **Aceptado · deuda extendida**.
   - Decisión humana 2026-05-28 (Sesión 16): no se corrige hasta nuevo aviso. Triggers de re-evaluación obligatoria (los 4 listados arriba).

7. **Bloqueadores actuales:**
   - "Sin bloqueadores. F1 cerrada con deuda R1+R2 documentada. Pendiente conectar repo a workspace Databricks y CI básico (diferibles a F2)."

8. **Lecciones de cierre F1** (sección nueva al final de §Fase 1):
   - Atestación ≠ evidencia (lección heredada de F0, reconfirmada en F1).
   - Tests que aceptan errores no son tests; FakeRepos + dependency_overrides son la solución estructural.
   - Una decisión humana de aceptar deuda debe quedar con triggers de re-evaluación explícitos, no abierta.
   - El revisor y el ejecutor deben estar separados; un mismo agente cerrando su propio trabajo no caza errores propios.

9. **Nota de Sesión 16:**

```markdown
### 2026-05-28 — Sesión 16 · F1 cerrada vía F1-FIX2 (con R2 como deuda extendida)

- **Hecho:**
  - ✅ V6 cerrada con evidencia real en `_runs/v6_pagination_2026-05-28.md` (detfventas 27,747 y detcompras 11,623 paginados sin duplicados ni huecos).
  - ✅ V7 cerrada con evidencia real en `_runs/v7_drift_2026-05-28.md` (2 ingest_dates comparadas, 12/12 estables).
  - ✅ C-1 demostrado con evidencia en `_runs/c1_stock_real_2026-05-28.md` (MOTS1297: API=691, SQL=691).
  - ✅ V4 a ✅ tras confirmar timing-safe + test passing.
  - ✅ SEGUIMIENTO sincronizado con realidad: F1 ✅, KPIs reales (K-1 781ms no cumple), F2 🟡.
  - ✅ R2 (credenciales API en README) marcada como deuda extendida con triggers de re-evaluación explícitos.
- **Aprendido:**
  - 11 de 13 ítems de F1-FIX1 se resolvieron; los 2 restantes eran de captura+sync, no de implementación.
  - El plan F1-FIX2 enfocado y corto evitó re-mezclar todo el alcance de F1.
- **Abierto:**
  - R1 (passwords MySQL en historial) — deuda residual.
  - R2 (credenciales API en README) — deuda extendida, NO se corrige hasta nuevo aviso.
  - R3 (idempotencia kill-y-retry) — deuda residual.
  - R4 (Workflow Databricks) — eliminado, schedule en Task Scheduler.
  - KPI K-1 latencia /stock 781ms > 500ms — mitigar con R-X2 (cache memoria) en F2 si la PWA lo demanda.
- **Próximo paso:**
  - F2 · Silver + PWA MVP. Plan detallado por escribir.
```

**Acceptance criteria:**
- Cabecera global muestra `F1 ✅`.
- Las 7 verificaciones críticas con estado real (V2 ⚠️, V6/V7 ✅).
- KPI K-1 con cifra real (no oculto).
- R2 con nota de "deuda extendida" + 4 triggers de re-evaluación.
- Nota de Sesión 16.

---

## 3 · Cierre y handoff

Cuando las 4 tareas terminen:

1. **Ejecutor** commitea y pushea con mensaje:
   ```
   docs(F1-FIX2): cerrar F1 con evidencias V6/V7/C-1 y SEGUIMIENTO sincronizado
   ```
2. **Ejecutor** notifica al revisor.
3. **Revisor** audita en ≤15 min:
   - Existen los 3 archivos en `_runs/`.
   - V6 muestra `distinct == total > 0`.
   - V7 muestra **2 ingest_dates distintas** y 12 tablas estables.
   - C-1 muestra API == SQL.
   - SEGUIMIENTO muestra F1 ✅ con KPI K-1 cifra real y R2 con triggers.
4. Si todo cumple: **GO a F2** confirmado por el revisor.
5. Si algo falla: F1-FIX3 con el ítem específico (no rehacemos todo).

---

## 4 · Lo que abre tras el cierre

Una vez F1 ✅, se planifica F2 · Silver + PWA MVP. Sketch:

- **Track A:** silver con `fact_ventas`, `fact_compras`, `fact_inventario` + dimensiones, casteos formales (TZ, decimales), reglas de calidad (DLT/expectations), linaje Unity Catalog.
- **Track T:** PWA Next.js con login, búsqueda de productos, ficha SKU con stock por bodega, modo offline básico (PWA manifest + service worker), ventas recientes, instalable en móvil.

El plan detallado de F2 se escribe en sesión separada con su propio ADR (DT-F2) si hay decisiones técnicas nuevas (probablemente: estrategia silver schema evolution, librería PWA, formato de service worker, fetch wrapper para JWT).

---

## 5 · Referencias

- Plan F1 original: [`plan-f1.md`](plan-f1.md).
- Plan F1-FIX1 (resolvió 11/13): [`plan-f1-fix1.md`](plan-f1-fix1.md).
- Auditoría que originó F1-FIX1 (Sesión 14): [SEGUIMIENTO Notas de sesión](../SEGUIMIENTO.md#notas-de-sesión).
- Tablero de riesgos vivos: [SEGUIMIENTO](../SEGUIMIENTO.md#tablero-de-riesgos-vivos).
