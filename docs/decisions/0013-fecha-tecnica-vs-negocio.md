# ADR-0013 · `ingest_date` (técnica) vs `business_date` (de negocio)

- **Estado:** **Accepted** — 2026-05-29 (humano aprobó opción C sin ajustes)
- **Fecha:** 2026-05-29
- **Bloquea:** F2-A (Silver) y reportes históricos en F3
- **Decide:** Humano

## Contexto

El pipeline actual particiona Bronze por `ingest_date` (fecha en la que corrió el dump). Esto plantea un problema cuando el dump NO corre a tiempo:

- **PC apagado el 28, dump corre el 29** → movimientos del 28 quedan etiquetados `ingest_date=2026-05-29`. Pierde trazabilidad histórica.
- **Sin internet 3 días seguidos** → 3 días sin partición, luego un dump masivo con la fecha del día actual.
- **Reportes "ventas del 28 mayo"** → si Silver agrupa por `ingest_date`, dará info incorrecta.
- **Reportes "stock actual"** → no afecta (basta con el último `ingest_date` disponible).

La pregunta: ¿incorporamos una columna `business_date` (derivada de la fecha real del documento en sgHermes) y en qué capa?

## Hallazgos del sondeo (2026-05-29)

> Sondeo ejecutado con `infra/explore_business_dates.py`. Evidencia completa: [`notebooks/bronze/_runs/business_date_survey_2026-05-29.md`](../../notebooks/bronze/_runs/business_date_survey_2026-05-29.md). Survey completo de 170 tablas: [`full_schema_survey_2026-05-29.md`](../../notebooks/bronze/_runs/full_schema_survey_2026-05-29.md).

### Realidad por tabla core (12 de F1)

| Tabla | Columna business_date | Tipo | Calidad | Aplica |
|-------|------------------------|------|---------|--------|
| **facventas** | `fecfven` | datetime | ⚠️ MAX=`9876-01-01` (data sucia, 1 fila futurística) | ✅ Sí |
| **detfventas** | (sin fecha propia útil) | — | `serfec` varchar vacío | ❌ Derivar del header vía `numfven` |
| **productos** | (sin fecha de operación) | — | `fecapa` es fecha de creación (SCD) | ❌ Dimensional |
| **auxinventario** | `docfec` | datetime | OK, rango 2025-01 a 2026-05 | ✅ Sí |
| **bodegas** | — | — | Sin columnas de fecha | ❌ Dimensional |
| **terceros** | (3 fechas SCD) | date | `fecnac` / `feccrea` / `feccup` — todas dimensionales | ❌ Dimensional |
| **compras** | `feccom` | datetime | OK | ✅ Sí |
| **detcompras** | (sin fecha propia útil) | — | `serfec` varchar vacío | ❌ Derivar del header vía `numcom` |
| **sucursales** | — | — | Sin columnas de fecha | ❌ Dimensional |
| **formapago** | — | — | Sin columnas de fecha | ❌ Dimensional |
| **subproduct** | — | — | Sin columnas de fecha | ❌ Dimensional |
| **preciosxpro** | — | — | Sin columnas de fecha | ❌ Dimensional |

**Tablas con business_date directa:** 3 (`facventas`, `auxinventario`, `compras`).
**Tablas con business_date derivada del header:** 2 (`detfventas` ← `facventas`, `detcompras` ← `compras`).
**Tablas dimensionales (sin business_date):** 7 (`productos`, `bodegas`, `terceros`, `sucursales`, `formapago`, `subproduct`, `preciosxpro`).

### Observaciones críticas

1. **Nombre de columna NO es uniforme.** sgHermes usa `fecfven`, `feccom`, `docfec` para fecha de operación. NO existe un `fecdoc` consistente como `infollm.md` sugería.
2. **Detalle no tiene fecha propia.** Tanto `detfventas` como `detcompras` heredan la fecha de su cabecera. Hay que hacer JOIN al cargar Silver.
3. **Data sucia conocida:** `facventas.fecfven` tiene una fila con `MAX=9876-01-01` (claramente input incorrecto del usuario en sgHermes). Hay que sanear en Silver.
4. **Placeholders constantes:** `compras.horini`/`horfin` = `2000-01-01 00:00:00` siempre. `facventas.perdes`/`perhas` = `2010-01-01`. Son default no usados, ignorables.

---

## Opciones consideradas

### Opción A · Status quo (solo `ingest_date`)

Bronze y Silver siguen particionando solo por `ingest_date`. Sin `business_date`.

**Pros:**
- Cero trabajo.
- Bronze permanece minimal.

**Contras:**
- Silver agregará por `ingest_date`. Reportes "ventas del 28 mayo" mostrarán solo lo que se ingesta ese día — si el PC estuvo apagado, los datos del 28 estarán etiquetados como "ventas del 29".
- F3 dashboards históricos serán confusos.
- Aceptar deuda silenciosa que F3 va a sufrir.

**Cuándo conviene:** si MotoShop nunca va a generar reportes históricos por día (lo cual contradice el plan).

---

### Opción B · Bronze con doble fecha

Bronze almacena AMBAS columnas: `ingest_date` (técnica) Y `business_date` (derivada de la columna de fecha de operación, distinta por tabla).

**Implementación:**
- Modificar `dump_to_cloud.py` para derivar `business_date` por tabla durante el dump.
- Particionar Bronze por `business_date` (o doble partición).
- Reescribir bronze actual (reproceso de 5+ corridas ya ingestadas).

**Pros:**
- Bronze "verdadero desde el origen".
- Silver no necesita lógica de derivación.

**Contras:**
- Cambio estructural en Bronze (viola la teoría medallion de "espejo inmutable").
- Reescribir Bronze actual + reprocesar particiones existentes (efort grande).
- Lógica de derivar `business_date` distinta por tabla en el dump → más complejidad en el script local.
- Las tablas dimensionales no tienen business_date → asimetría incómoda en el esquema.

**Cuándo conviene:** si querés que Bronze refleje fielmente la verdad temporal de sgHermes y no te importa la asimetría.

---

### Opción C · Bronze simple, Silver con `business_date` *(recomendada)*

Bronze sigue particionado solo por `ingest_date` (como hoy). Silver, al transformar, deriva `business_date` desde la columna correspondiente de cada tabla de hechos. Tablas dimensionales no usan `business_date`.

**Implementación en F2-A:**
- Silver `fact_ventas`: agrega columna `business_date = DATE(fecfven)` con sanitization (`WHERE fecfven < '2099-01-01'`).
- Silver `fact_compras`: `business_date = DATE(feccom)`.
- Silver `fact_inventario`: `business_date = DATE(docfec)`.
- Tablas detalle (`fact_ventas_detalle`, `fact_compras_detalle`): hereda `business_date` del JOIN con su cabecera.
- Silver dimensiones: sin `business_date`.
- Particionar Silver por `business_date` (efficiency en queries diarias).

**Pros:**
- Bronze permanece simple e inmutable — alineado con principio medallion (ADR-0001).
- Silver concentra toda la lógica semántica del negocio.
- Trabajo nuevo solamente (5-10 líneas de SQL/PySpark por fact). No reprocesamos Bronze.
- Dimensiones no se contaminan con fechas que no tienen.
- Data sucia (`fecfven > 2099`) se sanea en Silver con expectations DLT.
- Cuando F3 quiera "ventas del 28", lee Silver por `business_date='2026-05-28'`, sin importar cuándo se ingestó.

**Contras:**
- Cualquier consulta directa contra Bronze que necesite filtrar por fecha de negocio (raro) tiene que hacer la derivación manualmente.

**Cuándo conviene:** prácticamente siempre. Es el patrón recomendado por Databricks y la mayoría de implementaciones medallion serias.

---

## Recomendación

**Opción C.**

Razones:
1. Es **consistente con ADR-0001** (Bronze como espejo inmutable).
2. **Cero re-trabajo** sobre datos ya ingestados.
3. La lógica de business_date está donde tiene que estar: en la capa que entiende el negocio (Silver).
4. Trabajo incremental: F2-A ya iba a hacer casting en Silver de cualquier manera; sumar `business_date` derivada es ~5 líneas extra por fact table.
5. Permite manejar la data sucia (`fecfven` futurística, `serfec` vacío) en Silver con reglas de calidad explícitas en lugar de contaminar Bronze.

## Consecuencias si se acepta C

### F2-A (cuando se implemente Silver)
- `fact_ventas` con columna `business_date` derivada de `fecfven` + sanitization.
- `fact_compras` con `business_date` derivada de `feccom`.
- `fact_inventario` con `business_date` derivada de `docfec`.
- `fact_ventas_detalle`, `fact_compras_detalle`: heredan vía JOIN.
- Particionar Silver por `business_date` para queries diarias eficientes.

### F3 (Gold + Dashboards)
- KPIs por business_date — "ventas del 28 mayo" da el número correcto sin importar cuándo se ingestó.
- Comparativas mes anterior, año anterior, etc.

### Reglas de calidad a aplicar en Silver
- `fact_ventas`: filter `business_date < CURRENT_DATE + 1` (descartar fechas futuristas, captura el bug `9876-01-01`).
- `fact_ventas`: filter `business_date > '2020-01-01'` (descartar placeholders).
- Documentar las reglas en el notebook silver con expectations.

### Lo que NO cambia
- Bronze sigue como está.
- `dump_to_cloud.py` sigue como está.
- Pipeline existente sigue corriendo.

---

## Decisión humana · 2026-05-29

- [ ] A · Status quo
- [ ] B · Bronze con doble fecha
- [x] **C · Silver con business_date** ⭐ aprobada sin ajustes
- [ ] Otra

ADR pasa a `Accepted`. F1.9 cierra. F2 abre. El plan `docs/plan-f2.md` (Sesión 23) incorpora la lógica de business_date en Silver desde el primer commit.

---

## Referencias

- ADR-0001 (medallion architecture): [`0001-medallion-architecture.md`](0001-medallion-architecture.md).
- Plan F1.9 que originó este ADR: [`../plan-f1-9.md`](../plan-f1-9.md).
- Sondeo: [`business_date_survey_2026-05-29.md`](../../notebooks/bronze/_runs/business_date_survey_2026-05-29.md).
- Survey completo de la BD (170 tablas): [`full_schema_survey_2026-05-29.md`](../../notebooks/bronze/_runs/full_schema_survey_2026-05-29.md) — útil para F2/F3 cuando se sumen más tablas.
