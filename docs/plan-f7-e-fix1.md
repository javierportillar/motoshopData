# Plan F7-E-FIX1 · Workflow Databricks · 3 tasks fallando

- **Fecha apertura:** 2026-05-31 (Sesión 63)
- **Estado:** 🟡 ABIERTA
- **Duración estimada:** Dev W (o Dev D) 30 min · Wall-clock 30-45 min con verificación.
- **Bloqueante:** balde B snapshots históricos no se acumula mientras workflow falle.

---

## 1 · Hallazgo

3 tasks de `motoshop_full_workflow` (ID `272152121206178`) fallan en cada corrida:

| Task | Notebook | Hipótesis |
|------|----------|-----------|
| `gold_drift` | `25_drift_monitor.py` | Schema mismatch — tabla `gold.alertas_drift` creada manualmente por Dev W |
| `gold_rotacion_promedio` | `18_mart_rotacion_promedio.py` | Schema mismatch — tabla creada manual sin `PARTITIONED BY` |
| `gold_abc_xyz` | `19_mart_abc_xyz.py` | Mismo patrón que rotación |

**Causa raíz probable:** Dev D y Dev W ejecutaron los notebooks manualmente en Databricks SQL Warehouse antes de que el workflow corriera. Esto creó las tablas con un schema posiblemente distinto al `CREATE TABLE IF NOT EXISTS` que tienen los notebooks (especialmente `PARTITIONED BY (business_date)` en D4 y D5).

**No es bug de código.** Es inconsistencia operativa entre estado actual de Databricks y schema esperado por notebooks.

---

## 1.5 · Refinamiento post-screenshots workflow (Sesión 63b)

Tras revisar las capturas del workflow en Databricks UI, refinamos la hipótesis:

### Root cause real son SOLO 2 jobs (no 3)

| Task | Estado real | Acción |
|------|-------------|--------|
| `gold_rotacion_promedio` | 🔴 Failed en 2m 27s (durante INSERT OVERWRITE) | **Fix directo** — schema mismatch confirmado |
| `gold_drift` | 🔴 Failed en 7s (error inmediato) | **Fix directo** — causa distinta a rotación |
| `gold_abc_xyz` | ⏸️ Upstream failed en 0s | **NO necesita fix propio** — cuando rotación pase, abc_xyz pasa solo en next run |

### Bug adicional detectado en DAG del workflow

`gold_drift` solo depende de `gold_validate` en `infra/create_full_workflow.py` línea 131:

```python
("gold_drift", "gold/25_drift_monitor", ["gold_validate"])
```

Pero el notebook `25_drift_monitor.py` **lee de `motoshop.gold.forecast_baseline_sku`** que se actualiza en `gold_baseline` (línea 116-117).

**Conceptualmente, `gold_drift` debería depender también de `gold_baseline`** (o mejor: solo de `gold_baseline` ya que es su fuente real de data). En este run específico todos los upstream están en verde así que no afecta — pero corregir el DAG previene timing bugs futuros.

### Plan refinado para Dev W

1. Concentrarse en `gold_rotacion_promedio` y `gold_drift` (no en abc_xyz).
2. Después del fix, re-correr workflow → abc_xyz debería pasar solo.
3. Bonus opcional: agregar `gold_baseline` como dependencia explícita de `gold_drift` en el workflow.

---

## 2 · Impacto

| Aspecto | Status |
|---------|--------|
| Dashboards F7 PWA con datos actuales | ✅ Funcionan (las tablas existen, dashboards leen lo que hay) |
| Snapshots históricos balde B | 🔴 No se acumulan automáticamente cada noche |
| R-V2-16 (snapshots históricos 30 días) | Bloqueado hasta que el workflow corra clean |
| Defensa académica | 🟡 Defendible con deuda documentada, pero mejor cerrarla antes |
| V2 producción seria | 🔴 Non-negotiable: workflow tiene que correr clean |

---

## 3 · Diagnóstico (Paso 1)

Antes de cualquier fix, **confirmar la causa real** mirando logs de Databricks UI.

Para cada task fallida:
1. Abrir Databricks UI → `Workflows` → `motoshop_full_workflow`
2. Click en último Run con failures
3. Click en cada task (`gold_drift`, `gold_rotacion_promedio`, `gold_abc_xyz`)
4. Copiar el **stacktrace exacto**

Reportar los 3 errores en SEGUIMIENTO.md para que el Revisor pueda confirmar o descartar la hipótesis de schema mismatch.

---

## 4 · Fix según diagnóstico

### Hipótesis A · Schema mismatch (más probable)

Si el error contiene algo como:
- `Table is not partitioned`
- `Column types do not match`
- `Cannot apply INSERT OVERWRITE PARTITION on non-partitioned table`
- `Schema mismatch detected`

**Fix:** DROP las tablas afectadas para que el workflow las recree con schema correcto.

```sql
-- En Databricks SQL Warehouse
DROP TABLE IF EXISTS motoshop.gold.mart_rotacion_sku;
DROP TABLE IF EXISTS motoshop.gold.mart_abc_xyz;
DROP TABLE IF EXISTS motoshop.gold.alertas_drift;
```

Verificar drop OK:
```sql
SHOW TABLES IN motoshop.gold LIKE 'mart_rotacion%';
SHOW TABLES IN motoshop.gold LIKE 'mart_abc_xyz%';
SHOW TABLES IN motoshop.gold LIKE 'alertas_drift%';
-- Cada uno debería devolver 0 filas
```

### Hipótesis B · Data vacía en upstream (drift)

Si `gold_drift` falla con NPE o `week_end NULL`, es porque `gold.forecast_baseline_sku` está vacía.

Verificar:
```sql
SELECT COUNT(*), MIN(business_date), MAX(business_date)
FROM motoshop.gold.forecast_baseline_sku;
```

Si está vacía, hay que correr el baseline primero. Pero esto ya debería estar OK porque hay dashboards funcionando — verificar antes de asumir.

### Hipótesis C · Otra causa

Si los logs muestran un error distinto, reportar al Revisor para diagnóstico ad-hoc.

---

## 5 · Re-ejecución y verificación (Paso 3)

Después de aplicar el fix:

1. Databricks UI → `motoshop_full_workflow` → **Run now**
2. Esperar a que las 31 tasks terminen (~5-15 min según complejidad)
3. Verificar las 3 que fallaban ahora pasen verde
4. Verificar que las tablas se recrearon:

```sql
SELECT COUNT(*) FROM motoshop.gold.mart_rotacion_sku WHERE business_date = CURRENT_DATE();
SELECT COUNT(*) FROM motoshop.gold.mart_abc_xyz WHERE business_date = CURRENT_DATE();
SELECT COUNT(*) FROM motoshop.gold.alertas_drift;
```

Esperar:
- `mart_rotacion_sku`: ~4,840 filas para CURRENT_DATE
- `mart_abc_xyz`: ~1,172 filas para CURRENT_DATE
- `alertas_drift`: 0+ filas (depende si hay drift detectado esta semana)

---

## 6 · V críticas (gate de cierre F7-E-FIX1)

| ID | Verificación | Pass criterion |
|----|--------------|---------------|
| V-FIX1-1 | Stacktraces reportados | 3 errores claros en SEGUIMIENTO antes de aplicar fix |
| V-FIX1-2 | Fix aplicado | Tablas dropeadas + workflow re-corrido OK |
| V-FIX1-3 | Workflow corre 31/31 tasks OK | Último Run muestra todo verde |
| V-FIX1-4 | Tablas re-pobladas con schema correcto | DESCRIBE muestra `PARTITIONED BY business_date` |
| V-FIX1-5 | Smoke endpoints F7-D siguen 200 | drift-summary, forecast-categoria, plan-compras |
| V-FIX1-6 | Cron 19:00 COL UNPAUSED | Próxima corrida nocturna ya configurada |

**Gate:** todas PASS → F7-E-FIX1 ✅ → workflow listo para acumular snapshots históricos.

---

## 7 · Riesgos

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| R-FIX1-1 | DROP TABLE elimina data útil que ya estaba en producción | Verificar con SELECT antes de DROP que las tablas tienen pocas filas (1-3 inserts manuales recientes). Backup conceptual no necesario. |
| R-FIX1-2 | Después del fix, otra task del workflow falla por causa distinta | Plan-B: aceptar deuda y documentar en E5 con honestidad. |
| R-FIX1-3 | Hipótesis A incorrecta, la causa real es otra | Diagnóstico previo (Paso 1) lo confirma o descarta. NO aplicar fix sin diagnóstico. |

---

## 8 · Handoff Dev W

Ver `PENDIENTES.md` Sesión 63 § "Handoff Dev W · F7-E-FIX1".

---

## 9 · Cuándo cierra

Cuando Dev W reporte 🟢 en SEGUIMIENTO confirmando que workflow corre 31/31 tasks verde + smoke endpoints OK + cron UNPAUSED:

1. Revisor (yo) audita V-FIX1-1 a V-FIX1-6
2. Si PASS → cierra F7-E-FIX1 oficialmente
3. Update `SEGUIMIENTO.md` cabecera con F7 100% sin deudas operativas
4. Arrancar E5 memoria final
