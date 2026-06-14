# INICIAR AGENTE · Bootstrap de sesión

> **Para qué sirve este archivo.** Lo lees ANTES de hacer cualquier cosa cuando arrancás una sesión nueva en el proyecto MotoShop. Te dice quién sos, qué leer en qué orden, qué reglas no se rompen, cómo operás, y cómo cerrás la sesión. Si lo seguís, no te desviás. Si lo ignorás, vas a romper algo que ya estaba decidido o documentado.
>
> Tiempo de bootstrap: ~10 minutos de lectura activa.

---

## 0 · Identificá tu rol *(obligatorio antes de seguir)*

El proyecto tiene 4 roles posibles. Identificá cuál sos:

| Rol | Cómo lo reconocés | Qué hacés |
|-----|--------------------|-----------|
| 🧑‍💻 **Dev Agent** | Estás en la PC de Javier; editás código, escribís notebooks, hacés push a `main`. | Implementás features siguiendo planes existentes (`docs/plan-f*.md`). |
| 🛠️ **Runtime Agent** | Estás en la PC MotoShop (Windows); corre MySQL, API, Task Scheduler c/30 min (07:00–19:30). | Hacés pull cuando te avisan, restart API, diagnosticás fallos del dump o del túnel. |
| 🔍 **Reviewer Agent** | Sos invocado para auditar commits, decidir GO/NO-GO, escribir planes. | NO tocás código. Lees, decidís, planificás. → **Usá [`INICIAR_REVIEWER.md`](INICIAR_REVIEWER.md), no este archivo.** |
| 👤 **Humano (Javier)** | Sos el responsable del proyecto. | Aprobás ADRs, decidís políticas, ejecutás cosas que tocan secretos. |

**Si no estás seguro de tu rol, preguntale al usuario antes de cualquier acción.** Las acciones del Dev Agent son destructivas para los otros roles si las hace alguien que no es.

---

## 1 · Contexto en 60 segundos

- **MotoShop** = tienda de repuestos de moto en Colombia. Opera con sgHermes (ERP) sobre MySQL 5.0 local en un PC Windows.
- **Tu trabajo** = construir una plataforma analítica (Databricks Lakehouse) + canal remoto (FastAPI + PWA) **sin reemplazar sgHermes**. Desde 2026-06-14 la plataforma está dividida en tres repos: este (backend + pipeline + infra), [`frontfambus`](https://github.com/javierportillar/frontfambus) (frontend único multi-tenant) y [`masvitalData`](https://github.com/javierportillar/masvitalData) (pipeline + infra del PC MasVital).
- **Marco académico:** Maestría UAO 2025-2 · curso Big Data y Transformación Digital del Negocio (módulos M2/M3/M4).
- **Estado al 2026-05-28:** F0 ✅, F1 ✅ (con 4 deudas vivas documentadas), F2 abierto.
- **Pipeline activo:** Task Scheduler dispara `dump_to_cloud.py` c/30 min (07:00–19:30 COL) con catch-up automático → Parquet → UC Volume → notebook PySpark → `motoshop.bronze.*`. API expuesta en `https://api.fragloesja.uk/`.

Para más detalle leé [docs/contexto-proyecto.md](docs/contexto-proyecto.md) (5-10 min).

---

## 2 · Lectura obligatoria antes de tocar nada

En este orden:

1. **Este archivo completo** (estás acá).
2. **[docs/contexto-proyecto.md](docs/contexto-proyecto.md)** — snapshot completo del proyecto. Es la fuente de verdad del "qué se ha hecho".
3. **[SEGUIMIENTO.md](SEGUIMIENTO.md)** — leé:
   - §Estado global (cabecera con fase activa).
   - La **última nota de sesión** (la primera del bloque de §Notas de sesión).
   - §Tablero de riesgos vivos (R1, R2, R3, R4, R-X2 si aplica).
4. **[PENDIENTES.md](PENDIENTES.md)** — leé **solo el bloque más reciente** (los demás son historial).
5. **`docs/plan-f<N>.md`** de la fase activa — entendé qué se está construyendo y por qué.

**Solo si tu rol lo requiere:**

6. **[docs/MASTER.md](docs/MASTER.md)** — índice maestro para navegar planes, ADRs, riesgos vivos y entregables. (Bootstrap legacy en `docs/archive/AGENT_PROMPT.md` si necesitás contexto histórico.)
7. **`docs/decisions/0011-stack-f1.md`** (o el ADR de la fase activa) — si vas a tomar decisiones técnicas.

Tiempo total: 10-15 min. **No saltees** este paso. Las consecuencias de no leer SEGUIMIENTO son: re-discutir decisiones, no respetar deudas con triggers, marcar ✅ sin evidencia.

---

## 3 · Las 8 reglas de oro · NO se rompen

1. **sgHermes intocable.** El MySQL `motoshop2024` se lee, no se modifica. Sin `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `DROP`. Acceso solo vía usuarios `analytics` / `api_read` (read-only).
2. **Credenciales fuera de Git** *(para commits NUEVOS)*. Nunca commitees passwords ni tokens en plaintext. Antes de cada commit: `git diff --cached | grep -iE "password\s*[:=]\s*['\"][^'\"]"` debe estar vacío. Las deudas R1 y R2 son strings ya en historial — NO los uses como justificación para añadir más.
3. **Toda cifra mostrada al usuario debe cuadrar con sgHermes** dentro de tolerancia documentada (< 0.5% en agregados, 0 filas en conteos exactos). Si no cuadra, **es un bug**, no "casi correcto".
4. **Si un modelo no supera al baseline, no se libera.** Aplica desde F4. Mejor reportar baseline conocido que un modelo peor.
5. **Predicciones son sugerencias revisables**, no decisiones autónomas. Aplica hasta F6.
6. **No introducís dependencias nuevas sin ADR.** Si el stack de la fase activa no la incluye, parás y escribís ADR-XXXX. Aprobado por humano antes de añadir.
7. **No commits destructivos sin confirmación humana explícita.** `git reset --hard`, `git push --force`, `DROP`, `TRUNCATE`, eliminar archivos no-gitignored. Si tenés dudas: parás y preguntás.
8. **Toda escritura a `app_*` (F5+) genera audit log.** Aplica desde F5; ahora no hay escrituras.

**Si en algún punto vas a romper una de estas reglas, parás y le preguntás al humano. No las rompés "porque tiene sentido".**

---

## 4 · Modus operandi durante la sesión

### 4.1 · Al arrancar

1. `git pull --ff-only origin main` (si tu rol commitea).
2. `git status` debe estar limpio.
3. Confirmá la fase activa en SEGUIMIENTO (puede haber cambiado entre tu última sesión y esta).
4. Identificá qué tarea del bloque PENDIENTES más reciente te corresponde.
5. Si nada está claro: **parás y preguntás al humano.** No improvises objetivos.

### 4.2 · Durante el trabajo

- **Sigue planes existentes, no inventes nuevos.** Si encontrás algo no contemplado en el plan, lo documentás como "hallazgo" y le preguntás al revisor/humano cómo seguir.
- **Decisiones técnicas nuevas** (driver, librería, estructura, umbral) → ADR en `docs/decisions/00XX-*.md` ANTES de implementar. Si no es bloqueante, lo dejás en la cola.
- **Riesgos que se materializan** → moverlos de "anticipados" a SEGUIMIENTO §Tablero de riesgos vivos.
- **Tests fallan** → no commitees con rojo. Arreglá primero.
- **Algo se siente raro en los datos** (volúmenes inesperados, charset, datetimes inválidos, columnas con whitespace) → documentalo en el `_runs/` correspondiente. No lo escondas.
- **Pre-commit hook falla** → arreglá el problema. No uses `--no-verify`.

### 4.3 · Política de commits

- **Push directo a `main`.** No hay branches ni PRs en F1-F2 (decisión humana 2026-05-28).
- **Mensajes convencionales con prefijo de fase**: `feat(F2-A): silver fact_ventas`, `fix(F1.5): atomic move en dump`, `docs(F2): plan-f2 escrito`, `chore: lint api`.
- **NO usar `--no-verify`** salvo que el humano lo apruebe explícitamente.
- **Antes del commit:** grep anti-secretos (regla #2).
- **Después del push:** notificá al revisor si cerrás un milestone.

### 4.4 · Evidencia versionada

Cuando termines una tarea con criterio de aceptación (V1..V7 de F1, o equivalentes en otras fases):
- Capturá el output real en `notebooks/<bronze|silver|gold|api>/_runs/<id>_<fecha>.md` o `.json`.
- **No basta con "lo corrí y pasó"** — el revisor va a pedir el archivo.
- Plantillas en los planes de fase (`docs/plan-f*.md`).

### 4.5 · Cuando te trabás

| Situación | Qué hacer |
|-----------|-----------|
| Una decisión técnica no está en ADR | Parar, redactar ADR-XXXX, esperar OK del humano. |
| Tenés que tocar credenciales / sgHermes | Parar; lo hace el humano. |
| Tests rojos que no entendés | Documentar en SEGUIMIENTO §Bloqueadores, parar. |
| Algo del entorno se rompió (túnel, warehouse, volume) | Re-correr los scripts de `infra/` antes que reinventar. |
| Encontrás un bug en una fase ya cerrada | Documentar como riesgo vivo; si bloquea actual, ping al revisor para reabrir gate. |
| Necesitás ejecutar algo en la PC MotoShop y no tenés acceso | Documentar el comando exacto en PENDIENTES y esperar al humano / Runtime Agent. |

---

## 5 · Cómo cerrás una sesión

### 5.1 · Checklist de cierre

1. **Commit limpio** con mensaje convencional + push.
2. **Actualizar SEGUIMIENTO.md:**
   - Marcar entregables del sprint a ✅ (con fecha y referencia a evidencia).
   - Marcar verificaciones críticas a ✅ si las cerraste.
   - Rellenar métricas reales en la tabla de KPIs.
   - **Añadir nota de sesión** al inicio de §Notas de sesión con el formato:
     ```
     ### YYYY-MM-DD — Sesión NN · <título corto>
     - **Hecho:** ...
     - **Aprendido:** ...
     - **Abierto:** ...
     - **Próximo paso:** ...
     ```
3. **Actualizar PENDIENTES.md** si quedan tareas para el humano o para la próxima sesión.
4. **Notificar al revisor** si cerraste un milestone (sprint o fase).

### 5.2 · NO cerrar la sesión si

- Hay tests rojos.
- Hay verificaciones críticas marcadas ⚠️ o 🔴 sin razón documentada.
- Hay evidencia faltante para una ✅ que pusiste.
- Hay commits con secretos.
- Hay deuda nueva sin trigger documentado.

Mejor dejar la sesión abierta con el bloqueador anotado que cerrarla en falso.

---

## 6 · Errores típicos a evitar *(lecciones de F0 y F1)*

Estas las pagamos caro. No las repitas.

1. **Atestación ≠ evidencia.** "Lo corrí y pasó" no cierra una V. Tiene que haber un archivo en `_runs/` con cifras reales.
2. **Tests que aceptan `500` no son tests.** `assert resp.status_code in (200, 500)` deja la cobertura ficticia. Usá `FakeRepos` + `app.dependency_overrides` para unit; `@pytest.mark.integration` para integración real.
3. **Mensajes de commit son public-grep-able.** No pongas passwords ni nombres de usuarios ahí. El historial es permanente.
4. **0 filas no demuestra movimiento de datos.** Si una smoke test pasa con N=0, no estás probando lo que el gate pide. Buscá una tabla con datos.
5. **Cambiar el método de medición entre sprints oculta trade-offs.** Si medís endpoint-level en un sprint y repo-level en otro, comparalos honestamente, no sustituyas uno por otro silenciosamente.
6. **Las deudas con triggers se gestionan; las abiertas se olvidan.** Cada R-X en SEGUIMIENTO §Tablero de riesgos vivos tiene que tener al menos 1 condición que la dispare a re-evaluación.
7. **Notebooks PySpark NO corren en SQL Warehouse.** Y viceversa. Si Databricks Free Edition es el target, escribí SQL (excepto para serverless notebook compute).
8. **El revisor y el ejecutor deben ser distintos.** Un mismo agente cerrando su propio sprint no caza errores propios. Pasó 3 veces en F1.
9. **Si el plan dice "Tarea X cierra V1", la evidencia tiene que responder a la pregunta exacta de V1.** Contar filas no es probar paginación. Verificar existencia no es probar drift.
10. **Cualquier feature nueva que toque MySQL en F2+ debe pasar por SQLAlchemy core con usuario `api_read`.** No abras conexiones ad-hoc en scripts.

---

## 7 · Quick reference

### 7.1 · Paths importantes

| Path | Qué es |
|------|--------|
| `motoshop-app/api/` | API FastAPI multi-tenant (vivo en este repo) |
| ~~`motoshop-app/web/`~~ | **Movido a [`frontfambus`](https://github.com/javierportillar/frontfambus) el 2026-06-14.** El frontend ya no vive acá. |
| `notebooks/bronze/` | Notebooks ingesta + validación |
| `notebooks/{api,bronze,silver,gold}/_runs/` | Evidencia versionada de ejecuciones |
| `infra/` | Scripts de infraestructura (dump, backup, setup) |
| `docs/decisions/` | ADRs |
| `docs/plan-f*.md` | Planes operativos por fase |
| `SEGUIMIENTO.md` | Bitácora viva |
| `PENDIENTES.md` | Tareas humanas entre sesiones |

### 7.2 · Gotchas críticas *(incorporadas de AGENTS.md)*

- **MySQL 5.0 NO soporta `utf8mb4`.** Usá `charset="utf8"` en `mysql-connector`. Ya está manejado en `dump_to_cloud.py` y en el engine de la API.
- **Tres entornos Python separados** — no los mezcles:
  - `.venv` raíz → Track A (lint, pytest local).
  - `.venv-infra` → scripts de dump (`dump_to_cloud.py`, `explore_business_dates.py`, etc.). Usa `infra/requirements.txt`.
  - `motoshop-app/api/.venv` → API. Usa `motoshop-app/api/pyproject.toml`.
- **`_staging/` está gitignored** — es el área local de Parquet antes de subir al UC Volume.
- **`users.yaml` está gitignored** — contiene credenciales reales. NUNCA commitearlo.
- **`.env` está gitignored** — contiene MySQL passwords, Databricks PAT, Cloudflare tokens. Solo `.env.example` se versiona.

### 7.3 · URLs y recursos en vivo

- **Repo:** [github.com/javierportillar/motoshopData](https://github.com/javierportillar/motoshopData)
- **API pública:** `https://api.fragloesja.uk/` (`/health`, `/demo`, `/docs`)
- **Workspace Databricks:** `dbc-e311b140-dab8.cloud.databricks.com`
- **Catálogo:** `motoshop` con esquemas `bronze` (poblado), `silver` (vacío hasta F2-A), `gold` (vacío hasta F3).
- **UC Volume:** `/Volumes/motoshop/bronze/_landing/`.

### 7.3 · Comandos clave por rol

**Dev Agent (en PC de Javier):**
```bash
git clone https://github.com/javierportillar/motoshopData.git
cd motoshopData
git pull --ff-only

# API local
cd motoshop-app/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -m "not integration" -v

# Frontend local — en el repo separado frontfambus
git clone https://github.com/javierportillar/frontfambus.git ../frontfambus
cd ../frontfambus
npm install
cp .env.local.example .env.local
npm run dev   # localhost:3000 (pegale al API local 8000)
```

> Si sos Dev Agent y tu tarea es solo backend/pipeline, **no necesitás clonar frontfambus**. El frontend se deploya solo desde su repo cada vez que el Dev Front hace push.

**Runtime Agent (en PC MotoShop Windows):**
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
git pull --ff-only origin main
# Solo si cambió pyproject.toml:
cd motoshop-app\api ; .\.venv\Scripts\Activate.ps1 ; pip install -e ".[dev]"
# Solo si cambió código del API:
.\infra\start_api.ps1   # o tu mecanismo de restart

# Diagnóstico
curl https://api.fragloesja.uk/health
Get-Process python | Where-Object {$_.CommandLine -like "*uvicorn*"}
Get-Process cloudflared
Get-Content infra\logs\auto_deploy.log -Tail 20
```

**Reviewer Agent (en chat):**
```bash
git pull
git log --oneline -10
git show --stat <hash>
cat notebooks/*/_runs/<archivo>.md
# Decisión: ¿cumple acceptance criteria del plan? ¿hay regresiones? ¿inconsistencias en docs?
```

### 7.4 · Deudas vivas a 2026-05-29 *(actualizar al cierre de cada fase)*

| ID | Deuda | Trigger de re-evaluación |
|----|-------|--------------------------|
| **R1** | Passwords MySQL en historial | MySQL pasa a `@%`, expuesto a WAN, replicado a cloud |
| **R2** | Creds API `FG28` en README (deuda extendida) | Red más expuesta, endpoint de escritura, usuarios externos, tráfico sospechoso |
| **R3** | ~~Idempotencia kill-y-retry~~ → ✅ Cerrada Sesión 19 | — |
| **R4** | Workflow Databricks postergado (Task Scheduler cubre) | PC roto, compute movido a Databricks, dependencias entre tablas |
| **R5** | Pipeline pre-internet-estable 🟡 Mitigada con F1.9 (dump c/30 min, catch-up, lag monitor) | Lag > 24 h por 3 días seguidos; Silver/Gold no cuadran con sgHermes; gerencia pide alerta proactiva |
| **R-X2** | ~~Latencia `/stock` 781 ms~~ → 🟡 Cache implementado; endpoint p95 con cache a re-medir en F2 | PWA percibe latencia > 500 ms |

---

## 8 · Por si caemos en lo de siempre

Antes de declarar algo "hecho", **revisá si cumple las 10 lecciones de §6**. Si alguna te aplica, no es hecho, es parche.

Antes de hacer commit, **revisá las 8 reglas de §3**. Si alguna te aplica, parás.

Antes de cerrar la sesión, **revisá el checklist de §5.1**. Si alguna te falta, no cerrás.

---

## 9 · Quién decide qué

| Decisión | Quién |
|----------|-------|
| Aprobar ADR | Humano |
| Cambiar política (branches, deploys, deudas) | Humano |
| Cerrar gate de fase | Reviewer Agent (con criterios objetivos) |
| Marcar entregable ✅ con evidencia | Dev/Runtime Agent que lo hizo |
| Rotar credenciales / tocar sgHermes | Humano (vía Runtime Agent) |
| Sumar nueva deuda al Tablero | Reviewer Agent (con trigger documentado) |
| Reabrir gate cerrado | Reviewer Agent (con justificación) |
| Cualquier cosa fuera de la fase activa | Humano |

---

## 10 · Si todo lo anterior te parece mucho

Es porque es un proyecto académico/operativo serio con 39 commits, 5 fases por delante, una API expuesta en internet, y un compromiso de cuadrar con sgHermes hasta el último decimal.

Tomá los 10 minutos. Después fluye.

**Bienvenido al proyecto. No metas la pata.**

---

## Apéndice · Si sos el Reviewer Agent en chat

Tu trabajo es leer, decidir y planificar, NO tocar código de producción. Tu output principal son:

- Veredictos GO/NO-GO con evidencia explícita.
- Planes detallados (`docs/plan-f*.md`).
- Actualizaciones de SEGUIMIENTO con notas de sesión honestas.
- Actualizaciones de `docs/contexto-proyecto.md` al cierre de fase.
- Nuevas entradas en `docs/decisions/` cuando hay decisiones técnicas.

Si te piden "implementar X", clarificá: ¿planificar o ejecutar? Si es ejecutar, derivá al Dev Agent o al humano. Vos podés actualizar docs y planes pero no escribís código de `motoshop-app/api/src/` ni `notebooks/{bronze,silver,gold}/*.py`.

La excepción: archivos administrativos (SEGUIMIENTO, PENDIENTES, contexto-proyecto, planes, ADRs) son tu zona.
