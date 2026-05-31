# ADR-0022 · Mantener 1 workflow unificado en Databricks (vs separar bronze/silver/gold)

- **Fecha:** 2026-05-30 (Sesión 53)
- **Status:** Accepted
- **Deciders:** Revisor (basado en propuesta Dev W) + decisión humana implícita al aprobar audit cierre F7

---

## 1 · Contexto

Durante F7-E el Dev W (Runtime Windows) operó el `motoshop_full_workflow` (job único Databricks Workflows ID `272152121206178`) y detectó que cuando alguna task de gold falla (classifier, drift), todo el run se marca FAILED aunque bronze y silver hayan terminado OK. Propuso explícitamente una decisión arquitectónica al revisor:

> ¿Tiene sentido tener 1 solo job (`motoshop_full_workflow`) que va de bronze → silver → gold + classifier + drift + snapshots? O conviene separar:
> - **Job Bronze** (ingesta)
> - **Job Silver** (dims + facts + calidad)
> - **Job Gold** (marts + classifier + drift + snapshots)

Después de arreglar los 4 bugs reales en Ciclo 4 (commit `a61ab1f`), Dev W actualizó su pregunta con una propuesta concreta: **mantener 1 job unificado** con justificación.

---

## 2 · Decisión

✅ **Mantener 1 workflow unificado** (`motoshop_full_workflow`) con schedule único 19:00 COL.

### Argumentos a favor (aprobados)

| # | Argumento Dev W | Aceptación del revisor |
|---|------------------|------------------------|
| 1 | Ya no hay bugs conocidos → debería pasar todas las noches | ✅ Confirmado después del fix `a61ab1f` |
| 2 | Un solo schedule = un lugar para monitorear | ✅ Simplicidad operativa real |
| 3 | Tasks de silver corren en paralelo entre sí | ✅ Técnicamente correcto: el paralelismo viene de dependencias en el DAG, NO de separar jobs |
| 4 | Si gold falla, silver YA se actualizó | ✅ Riesgo asimétrico hacia lo barato — la API sigue sirviendo datos frescos de silver |
| 5 | Mantener 3 jobs = 3× infra | ✅ Verdadero costo de coordinación + alertas + dependencias inter-job |
| 6 | Para demo académica, simplicidad pesa más | ✅ Para defensa: "1 schedule, 1 job, fácil de explicar" |

### Razones técnicas adicionales del revisor

- **Databricks Workflows soporta task-level retry y task-level dependencies.** El paralelismo no se gana separando jobs — se gana con un buen DAG dentro de un solo job.
- **Un único entry point para el humano (Javier) y para Dev W.** Un solo "Run now" para reprocesar TODO el pipeline desde cero si hace falta.
- **Costo de coordinación entre jobs es real:** orchestration externa, alertas distintas, dependencias entre runs que pueden divergir.

---

## 3 · Alternativas descartadas

### Alternativa A · Separar en 3 jobs (Bronze · Silver · Gold)

**Pros:**
- SLAs distintos por capa
- Alertas a audiencias distintas (data eng vs business)
- Roll-back independiente
- Reintentos diferenciados

**Contras:**
- 3× infra (scripts, schedules, alertas, deps inter-job)
- Dependencias entre jobs introducen latencia adicional
- Humano (Javier) y Dev W tienen que coordinar 3 puntos en vez de 1
- Beneficios de SLAs distintos no son necesarios mientras el negocio sea académico / 1 tienda

**Veredicto:** descartada para el alcance académico actual. Diferida a **F8 / post-curso** si MotoShop crece a producción real con SLAs distintos por capa.

### Alternativa B · 2 jobs (Pipeline batch + ML/Snapshots)

**Pros:** menos infra que la A.
**Contras:** el corte conceptual es artificial — ML lee de gold y snapshots leen de marts. Separarlos invita complejidad de coordinación.
**Veredicto:** descartada.

---

## 4 · Consecuencias

### Positivas

- 1 schedule, 1 lugar de monitoreo, 1 entry point.
- Si gold falla, silver ya está fresco — la API sigue sirviendo datos correctos.
- Defensa académica simple: "todo el pipeline corre en 1 workflow gestionado en Databricks".

### Negativas (aceptadas como deuda diferida)

- Si gold falla, todo el run se marca FAILED aunque silver haya pasado — confuso visualmente, pero no afecta servicio.
- No hay alertas distintas por capa.
- Imposible reintentar solo gold sin re-correr todo (workaround: ejecutar gold tasks manualmente desde la UI).

### Deuda técnica creada

- **F8 / post-curso · si MotoShop pasa a producción real:** separar en 2-3 jobs con SLAs distintos. Esta ADR queda como ratificación temporal, no permanente.

---

## 5 · Acciones derivadas (a ejecutar)

1. ✅ Documentar esta decisión como ADR aceptado (este archivo).
2. 🟡 Dev W elimina job legacy `Motoshop Bronze Ingestion` (ID `810345190577693`) que quedó de F2 y nunca se usó después de la migración a `motoshop_full_workflow`.
3. 🟡 Dev D agrega las tasks D4 (rotación promedio) y D5 (ABC×XYZ) al **mismo** `motoshop_full_workflow`, no a un job separado.
4. 🟡 Actualizar `SEGUIMIENTO.md` § estado global con cierre F7 + esta decisión.

---

## 6 · Related artifacts

- Propuesta original Dev W: commit `45fc06c` en `PENDIENTES.md`
- Fix de los bugs que motivó la propuesta: commit `a61ab1f`
- Workflow actual: `infra/create_full_workflow.py` (ID `272152121206178`)
- Job legacy a eliminar: `Motoshop Bronze Ingestion` (ID `810345190577693`)
