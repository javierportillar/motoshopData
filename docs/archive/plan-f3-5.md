# Plan F3.5 · Hardening Silver — corrección de transformación `fact_ventas` / `fact_ventas_detalle`

- **Fecha apertura:** 2026-05-29 (Sesión 35)
- **Origen:** hallazgo del revisor durante la planificación de F4. Ver `SEGUIMIENTO.md` §Nota Sesión 35 y el resumen abajo (§1).
- **Modo:** secuencial · **1 dev (Dev A · Track A · Silver)**. Track T NO toca nada en este sprint.
- **Duración estimada:** 1 sesión corta (2-4 h de Dev A + revisión).
- **Estado:** 🟡 ABIERTA.

---

## 1 · Por qué existe F3.5 (la falla)

Durante la planificación de F4, antes de proponer agentes y tareas, el revisor verificó el volumen real de histórico disponible en sgHermes para decidir si Prophet/LightGBM eran viables. Hallazgo bloqueante:

| Capa | Tabla | Filas reales | Fuente |
|------|-------|--------------|--------|
| Bronze (proxy sgHermes) | `facventas` | **6,340** (desde 2024-01-11) | `notebooks/bronze/_runs/business_date_survey_2026-05-29.md:9` |
| Bronze | `detfventas` | **27,775** | mismo, línea 18 |
| Bronze | `auxinventario` | **26,174** | mismo, línea 28 |
| **Silver** | `fact_ventas` | **15** ❌ | `notebooks/silver/_runs/v3_reconciliation_2026-05-29.md:148` |
| **Silver** | `fact_ventas_detalle` | **58** ❌ | mismo, línea 149 |
| Silver | `fact_inventario` | 26,174 ✅ | mismo, línea 152 |

**`fact_inventario` pasa de bronze a silver sin perder filas. `fact_ventas` colapsa 6,340 → 15 (99.76% de pérdida) y `fact_ventas_detalle` 27,775 → 58 (99.79% de pérdida).** Eso NO es un dataset demo limitado como dijimos en F2 y F3 — **es un bug de transformación**.

**Implicaciones del bug que ya escribimos como verde y no lo eran:**

1. **V3 de F2 (reconciliación silver↔bronze) pasó por accidente.** La query compara "último mes con datos" — como el silver ya está filtrado, queda 1 sola factura por $99,200 y cuadra 0.0% trivialmente. La validación no inspecciona el universo, inspecciona un subset reducido por el propio bug.
2. **V6 de F3 (reconciliación PWA↔Databricks SQL) tampoco prueba nada.** Cuadra 0% porque ambos lados leen del mismo silver roto. Si silver tuviera 1 fila o 6,340, el match seguiría siendo 0%.
3. **Marts gold operan sobre 15 facturas** (mart_ventas_diarias_sku: 57 filas; mart_rotacion_abc: 7 productos únicos; mart_cohortes_clientes: 1 cliente real CONSUMIDOR FINAL). Datos académicamente vacíos.
4. **F4 sobre este silver es inviable.** Prophet/LightGBM con 15 facturas en 17 meses no produce nada útil. Pero el bronze REAL tiene volumen suficiente para forecasting honesto.

**Corrección de la auditoría Sesión 33:** la observación O2 que firmé como "dataset demo limitado, limitación reconocida, no bug" estaba **equivocada**. Era un bug. F3 no se debió cerrar verde sin resolver esto. Se documenta en el cierre de F3.5.

---

## 2 · Hipótesis de causa raíz (a verificar)

Posibles causas del filtro destructivo en `notebooks/silver/10_fact_ventas.py` y `11_fact_ventas_detalle.py`:

1. **`WHERE estfven = 'A'` demasiado restrictivo** — facturas activas en sgHermes pueden tener estados `A`, `F` (facturada), `C` (contado), etc. Si el filtro descarta todo menos `A`, descarta histórico real.
2. **JOIN con `dim_tiempo` con rango limitado** — si `dim_tiempo` solo cubre el último mes, el INNER JOIN actúa como filtro implícito.
3. **`business_date` derivado de columna con outliers** — `facventas.fecfven` reporta MAX=9876-01-01 (un outlier evidente). Si el código filtra `fecfven >= 'YYYY-MM-DD'` con fecha mal calculada (e.g. usa MAX dinámico que arrastra el outlier), todo el histórico anterior se cae.
4. **WHERE de `nit_cliente IS NOT NULL`** o similar — `detfventas` puede tener filas con cliente vacío en sgHermes histórico.
5. **JOIN con `detfventas.num_documento`** con tipo incompatible o trim mal hecho — el detalle existe pero no matchea con la cabecera.

Dev A debe diagnosticar cuál de estas (o una combinación) está causando la pérdida.

---

## 3 · Alcance y NO alcance

### Alcance (qué SÍ toca F3.5)

- `notebooks/silver/10_fact_ventas.py` — fix de filtro/JOIN
- `notebooks/silver/11_fact_ventas_detalle.py` — fix de filtro/JOIN
- `notebooks/silver/06_dim_tiempo.py` — si la causa raíz es rango limitado, ampliar a histórico completo (2024-01 → hoy + 90 días buffer)
- `notebooks/silver/31_reconciliation.py` — **rediseñar V3** para validar el universo completo, no un subset
- `notebooks/silver/_runs/v_fix1_*.md` y siguientes — evidencia versionada del fix
- Re-correr silver completo (10, 11, 20, 30, 31, 32)
- Re-correr **todos los marts gold** (10-14, 20, 30) con dataset corregido
- Re-correr V6 de F3 (PWA↔SQL) con dataset corregido
- Actualizar `SEGUIMIENTO.md` + `PENDIENTES.md` + `docs/contexto-proyecto.md`

### NO alcance (qué NO toca F3.5)

- `notebooks/bronze/**` (bronze ya está bien, el bug es río abajo)
- `notebooks/silver/01..05_dim_*.py` (dimensiones funcionan)
- `notebooks/silver/12_fact_compras.py`, `13_fact_compras_detalle.py`, `14_fact_inventario.py` — verificar conteo de control pero NO modificar a menos que se detecte el mismo patrón (alta probabilidad de que `fact_compras` tenga el mismo bug → ver Sprint §5 paso 3)
- `motoshop-app/api/**` (la API queda intacta — los endpoints `/metrics/*` automáticamente reflejan el silver corregido)
- `motoshop-app/web/**` (la PWA queda intacta)
- F4 — se pospone hasta que F3.5 cierre verde

---

## 4 · Decisiones técnicas (DT-F3.5)

**DT-F3.5-1 · Filtros de negocio explícitos y documentados.** Si después del fix queremos seguir filtrando por `estfven IN ('A', ...)`, el filtro tiene que estar en ADR-0017 (a crear) con justificación de negocio (qué significa cada estado en sgHermes). Sin ADR, no se filtra.

**DT-F3.5-2 · Rango de `dim_tiempo` cubre histórico completo + buffer.** `dim_tiempo` arranca en `MIN(fecfven)` de bronze (probablemente 2024-01-01) y termina en `today() + 90 días`. Si la causa raíz era rango limitado, esto la resuelve definitivamente.

**DT-F3.5-3 · Outliers de fecha se filtran explícitamente, no implícitamente.** El MAX=9876-01-01 de `facventas.fecfven` debe excluirse con `WHERE fecfven < '2100-01-01'` documentado en el notebook, no por accidente vía rango.

**DT-F3.5-4 · V3 rediseñada valida el universo, no el subset.** La nueva V3 compara:
- Conteo total: `COUNT(bronze.facventas WHERE filtros documentados) == COUNT(silver.fact_ventas)` con tolerancia 0 filas.
- Suma total: `SUM(bronze.facventas.totfven WHERE filtros documentados) == SUM(silver.fact_ventas.total_factura)` con tolerancia < 0.5%.
- Conteo por año-mes: distribución bronze == distribución silver para cada (year, month) en el rango.
- Top 10 SKUs por ventas: lista bronze == lista silver (en orden).

**DT-F3.5-5 · Quality_run incluye regla CRITICAL `silver_completeness`.** Nueva regla que falla si `COUNT(silver.fact_ventas) < 0.99 * COUNT(bronze.facventas WHERE filtros)`. Previene regresiones futuras.

---

## 5 · Sprint (1 dev, secuencial)

### Paso 1 · Diagnóstico (~30 min)

- Dev A lee `10_fact_ventas.py` y `11_fact_ventas_detalle.py` actuales.
- Identifica TODOS los filtros y JOINs.
- Ejecuta en Databricks SQL la query de bronze sin filtros: `SELECT COUNT(*), MIN(fecfven), MAX(fecfven) FROM bronze.facventas` → confirma 6,340.
- Para cada filtro candidato, mide cuánto descarta:
  - `WHERE estfven = 'A'` → ¿cuántas quedan?
  - `WHERE estfven IN ('A','F')` → ¿cuántas quedan?
  - `WHERE fecfven < '2100-01-01'` → ¿cuántas quedan?
  - `INNER JOIN dim_tiempo` → ¿cuántas quedan? (revelará si dim_tiempo limita)
- **Entregable:** `notebooks/silver/_runs/diagnostico_f3_5_2026-05-29.md` con el desglose factura-por-filtro y la causa raíz identificada.

### Paso 2 · Fix de `10_fact_ventas.py` (~45 min)

- Aplicar el fix mínimo necesario (no refactor) para que el universo cuadre.
- Documentar en comentarios del notebook qué filtros quedan y por qué (con referencia a DT-F3.5-1).
- Si la causa es `dim_tiempo` corta, ampliar `06_dim_tiempo.py` primero (DT-F3.5-2).
- Excluir outliers de fecha explícitamente (DT-F3.5-3).
- Ejecutar el notebook end-to-end en Databricks SQL.

### Paso 3 · Fix de `11_fact_ventas_detalle.py` (~30 min)

- Mismo patrón que paso 2.
- **Verificar también `12_fact_compras.py` y `13_fact_compras_detalle.py`** — si tienen el mismo filtro destructivo, aplicar el mismo fix.

### Paso 4 · V3 rediseñada (~30 min)

- Reescribir `31_reconciliation.py` siguiendo DT-F3.5-4 (4 validaciones: total, suma, por mes, top SKUs).
- Ejecutar y capturar resultado en `notebooks/silver/_runs/v3_fix_reconciliation_2026-05-29.md`.

### Paso 5 · Regla CRITICAL en quality_run (~15 min)

- Agregar a `20_quality_run.py` la regla `silver_completeness` (DT-F3.5-5).
- Ejecutar y confirmar que pasa con el silver corregido (sin la regla pasaría también el silver roto).

### Paso 6 · Re-correr gold + marts (~30 min)

- Ejecutar en orden: `notebooks/gold/10..14` → `20_quality_gold.py` → `30_validate_gold.py`.
- Capturar evidencia en `notebooks/gold/_runs/run_gold_fix_<timestamp>.md`.

### Paso 7 · Re-validar V6 PWA↔SQL (~20 min)

- Ejecutar el mismo procedimiento V6 de F3 contra el silver/gold corregido.
- Esperar que la PWA muestre **más datos reales**, no $99,200 trivial.
- Capturar en `motoshop-app/web/_runs/v6_pwa_dashboard_match_fix.md`.

### Paso 8 · Docs (~30 min)

- ADR-0017 si DT-F3.5-1 implica filtros de negocio que necesitan justificación documental.
- Actualizar `SEGUIMIENTO.md` con nota Sesión 35 (cierre F3.5).
- Actualizar `docs/contexto-proyecto.md` §15 con cifras reales del histórico (no "dataset demo").
- Actualizar `PENDIENTES.md` con cierre F3.5 + reapertura de planificación F4.

### Paso 9 · Commit + push

```
fix(F3.5-silver): corrige filtro destructivo en fact_ventas - recupera 6325 facturas perdidas
```

---

## 6 · V críticas (gates para cerrar F3.5)

| ID | Verificación | Pass criterion | Evidencia |
|----|--------------|---------------|-----------|
| **V-fix1** | Universo silver == universo bronze (facturas) | `COUNT(fact_ventas) == COUNT(facventas filtrado)` con tolerancia 0 filas | `_runs/v3_fix_reconciliation_2026-05-29.md` |
| **V-fix2** | Universo silver == universo bronze (detalle) | `COUNT(fact_ventas_detalle) == COUNT(detfventas filtrado)` con tolerancia 0 filas | mismo |
| **V-fix3** | Suma total cuadra | `SUM(silver.total_factura) == SUM(bronze.totfven)` con dif < 0.5% | mismo |
| **V-fix4** | Distribución mensual cuadra | Cada (year, month) en bronze == silver en conteo y suma | mismo |
| **V-fix5** | Quality_run nueva regla pasa | `silver_completeness` CRITICAL = OK | `_runs/run_silver_<timestamp>.md` |
| **V-fix6** | Marts gold re-corridos OK | 57/57 statements gold completados sin error | `notebooks/gold/_runs/run_gold_fix_<timestamp>.md` |
| **V-fix7** | V6 PWA↔SQL re-validada con datos reales | 5/5 KPIs cuadran 0% y los valores son materialmente distintos a los del run trivial ($99,200) | `motoshop-app/web/_runs/v6_pwa_dashboard_match_fix.md` |
| **V-fix8** | Mismo fix aplicado a `fact_compras` si aplica | Bronze.compras (762) == Silver.fact_compras o JUSTIFICAR diferencia | parte de V-fix1 ampliada |

**Gate de cierre:** V-fix1 a V-fix7 deben ser PASS. V-fix8 puede ser PASS o "no aplicable con justificación".

---

## 7 · Riesgos

| ID | Riesgo | Mitigación |
|----|--------|-----------|
| **R-F3.5-1** | El fix expone que `dim_tercero` también está incompleto (solo 161 clientes en silver, pero bronze pueda tener más) | Verificar como subtarea del paso 1 con `SELECT COUNT(DISTINCT nit_cliente) FROM bronze.facventas` — si no cuadra, ampliar alcance. |
| **R-F3.5-2** | El fix expone bugs adicionales en quality_run que no fallaban porque el universo era trivial | Aceptable — preferimos descubrirlos ahora que en F4 |
| **R-F3.5-3** | Re-correr marts con 6,340 facturas excede el budget de SQL Warehouse Free Edition | Improbable (6K filas no es volumen alto), pero si pasa: documentar y ajustar particionado |
| **R-F3.5-4** | Hay decisiones de negocio reales detrás del filtro (e.g. la tienda quería excluir notas crédito) que el revisor no conoce | Por eso DT-F3.5-1 exige ADR — si Dev A descubre justificación de negocio legítima, la documenta en ADR-0017 y el filtro queda |

---

## 8 · Prompt para Dev A · Sprint F3.5

```
Soy Dev A · Track A · Sprint F3.5 del proyecto MotoShop.

PRE-FLIGHT obligatorio:
1. cd /Users/javierportillarosero/Documents/personal/dataEmpresas/motoshopData
2. git pull --ff-only origin main
3. Leé INICIAR_AGENTE.md completo (rol = Dev Agent · Track A)
4. Leé docs/plan-f3-5.md COMPLETO (es corto, todo en una sola lectura)
5. Leé notebooks/silver/_runs/v3_reconciliation_2026-05-29.md líneas 140-200
   para entender el estado actual roto
6. Leé notebooks/bronze/_runs/business_date_survey_2026-05-29.md líneas 1-30
   para confirmar los volúmenes reales de bronze

MI MISIÓN:
Hay un bug en notebooks/silver/10_fact_ventas.py y 11_fact_ventas_detalle.py
que descarta 99.76% del histórico real de facturas (silver tiene 15 filas
cuando bronze tiene 6,340). Diagnosticar la causa raíz, arreglar, re-correr
silver+gold+marts, re-validar V3 y V6 con dataset real.

ENTREGABLES (en orden):
1. notebooks/silver/_runs/diagnostico_f3_5_2026-05-29.md — desglose
   factura-por-filtro identificando la causa raíz exacta
2. Fix de 10_fact_ventas.py + 11_fact_ventas_detalle.py
3. Si aplica: fix de 06_dim_tiempo.py (DT-F3.5-2) y 12_fact_compras.py
4. Rediseño de 31_reconciliation.py siguiendo DT-F3.5-4
5. Nueva regla CRITICAL silver_completeness en 20_quality_run.py
6. Re-corrida completa silver + gold + marts
7. Evidencias en _runs/ por cada V-fix (1 a 7)
8. ADR-0017 si los filtros de negocio que dejo necesitan justificación
9. Actualizar SEGUIMIENTO.md (mi sección) + PENDIENTES.md (mi sección)

LO QUE NO TOCO:
- notebooks/bronze/** (bronze está OK)
- motoshop-app/api/** ni motoshop-app/web/** (Track T no participa)
- Credenciales / users.yaml / .env

CIERRE:
Cuando todas las V-fix pasen, hago commit con prefijo fix(F3.5-silver): ...
y push. Después escribo en SEGUIMIENTO.md una nota de cierre honesta
que el revisor master pueda auditar.

ARRANQUE:
Empezá por el Paso 1 (Diagnóstico) del plan §5. NO toques código antes
de tener el diagnóstico escrito en diagnostico_f3_5_2026-05-29.md.
```

---

## 9 · Próximo paso del revisor (después de F3.5)

1. Auditar F3.5 con los 6 checks de INICIAR_REVIEWER.md.
2. Si pasa: cerrar F3.5 verde, actualizar cabecera global SEGUIMIENTO con `F3.5 ✅`, y proceder a planificación F4 con dataset real (6,340 facturas + 17 meses).
3. Si falla: F3.5-FIX1 (mismo patrón que F1-FIX1, F2-FIX1).

---

## 10 · Lección honesta de proceso

La auditoría de F3 (Sesión 33) marcó O2 como "dataset demo limitado, limitación reconocida, no bug" y firmé verde con esa observación diferida a F6. **El revisor (yo) no verificó el universo bronze vs silver explícitamente.** Si lo hubiera hecho, F3 cerraba rojo y F3.5 nacía ahí, no después.

**Acción correctiva para próximas auditorías:** agregar al check #2 de INICIAR_REVIEWER.md §3.2 "Cuadre de cifras" una sub-validación explícita: para cada tabla fact_*, comparar `COUNT(silver) vs COUNT(bronze con filtros documentados)` antes de aceptar el gate de cuadre como verde. Si la diferencia es > 1%, NO-GO automático.

Se incorpora en la próxima edición de INICIAR_REVIEWER.md (parte del cierre de F3.5).
