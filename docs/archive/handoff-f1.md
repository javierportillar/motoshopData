# Handoff F1 · Por dónde empezar si vas a desarrollar la Fase 1

> Si acabás de hacer pull del repo y vas a implementar F1, **empezá por este archivo**. Te ahorra leer los otros 7 docs en desorden.

---

## 1 · Contexto en 30 segundos

- **MotoShop** = tienda de repuestos con BD `motoshop2024` (MySQL 5.0, MyISAM, sgHermes) en un PC Windows local.
- **F0 ✅** está cerrado: tenés el workspace Databricks, el UC Volume `motoshop.bronze._landing`, un SQL Warehouse Serverless con auto-stop 10 min, un túnel Cloudflare exponiendo la API, usuarios MySQL read-only y backups.
- **F1** = ingestar 12 tablas a Bronze + API FastAPI con auth JWT + 3 endpoints de lectura. Detalle completo en [`docs/plan-f1.md`](plan-f1.md).
- **Vos sos el ejecutor.** Implementás código, corrés tests, hacés commits a `main`.
- **El "revisor"** (otra sesión de Claude) audita los commits, da GO/NO-GO en cada cierre de sprint, no toca código.

---

## 2 · Roles claros

| Rol | Quién | Qué hace |
|-----|-------|----------|
| **Ejecutor** | Vos (esta sesión / agente local) | Escribe código, corre tests, hace commits a `main`, captura evidencia |
| **Humano-PC owner** | Javier | Aprueba ADRs nuevos, ejecuta cosas que tocan datos sensibles (rotación de credenciales si hiciera falta, etc.), valida demos |
| **Revisor** | Otra sesión Claude | Audita commits, marca verificaciones críticas, da GO/NO-GO de gate |

En F0 el revisor y el ejecutor a veces fueron el mismo. En F1 se separan: vos implementás, el revisor audita.

---

## 3 · Pre-flight check (correr antes de tocar nada)

Verificá que estos elementos del entorno existen. Si falta alguno, **parar y consultar** — no improvisar.

### 3.1 · Repo y herramientas
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
git pull origin main
git status        # debe estar limpio
python --version  # 3.11+
node --version    # 18.18+
```

### 3.2 · Variables de entorno

| Archivo | Debe tener | Cómo verificar |
|---------|------------|----------------|
| `.env` (raíz) | `MYSQL_*`, `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_VOLUME_PATH` | `python infra/test_mysql_connectivity.py` devuelve `SELECT 1 -> 1` |
| `motoshop-app/api/.env` | `MYSQL_*` con usuario `api_read` | `cd motoshop-app/api && pytest` verde |
| `motoshop-app/web/.env.local` | `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` | `npm run dev` arranca sin errores |

### 3.3 · Entorno Databricks
```powershell
.\.venv-infra\Scripts\Activate.ps1
python infra\create_uc_volume.py       # debe decir "Ya existía"
python infra\create_sql_warehouse.py   # debe decir "Verificación crítica #4 OK"
```

### 3.4 · Túnel Cloudflare
```powershell
curl https://api.fragloesja.uk/health
# → {"status":"ok","version":"0.0.0","env":"dev"}
```

Si todo lo de arriba pasa, podés arrancar Sprint F1-A. Si algo falla, **paralo y reportá al humano-PC owner**.

---

## 4 · Flujo de trabajo por sprint

### 4.1 · Antes de empezar un sprint
1. Releé la sección correspondiente de [`docs/plan-f1.md`](plan-f1.md) (Sprint F1-A, F1-B o F1-C).
2. Confirmá los archivos que vas a crear/modificar.
3. Confirmá las verificaciones críticas (V1..V7) que el sprint cierra.

### 4.2 · Durante el sprint
- **Una decisión técnica nueva** (no listada en ADR-0011) → **parar y consultar** con el humano-PC owner. No implementarla sin ADR.
- **Un riesgo se materializa** → moverlo a `SEGUIMIENTO.md §Tablero de riesgos vivos` y seguir si tenés mitigación.
- **Tests fallan** → no commitees código con tests rojos. Arreglar primero.
- **Pre-commit hooks fallan** → arreglar el problema; no usar `--no-verify`.
- **Encontrás algo raro en los datos** (volúmenes inesperados, charset, datetimes inválidos) → documentar en el `_runs/` correspondiente, no esconder.

### 4.3 · Política de commits
- **Push directo a `main`.** No hay branches ni PRs en F1 (decisión humana 2026-05-28).
- **Mensaje convencional + prefijo de fase:** `feat(F1-A): ingesta bronze de las 12 tablas` / `fix(F1-B): redact authorization header en logs` / `chore(F1): documentar esquema bronze`.
- **NO commits destructivos** (`git reset --hard`, `git push --force`, `DROP TABLE`) sin OK explícito del humano-PC owner.
- **NO secretos en commits.** Antes de cada commit, `git diff --cached | grep -iE "password|token|secret|JWT_SECRET"` debe estar vacío. La lección de F0 #5 sigue valiendo.

### 4.4 · Al cerrar el sprint
1. Capturar evidencia en `notebooks/<bronze|api>/_runs/<sprint>_<fecha>.md` con outputs reales (no descripción).
2. Actualizar `SEGUIMIENTO.md`:
   - Marcar entregables del sprint a ✅.
   - Marcar V1..V7 del sprint a ✅ (con referencia al archivo de evidencia).
   - Rellenar la métrica medida en la tabla de KPIs.
   - Añadir nota de sesión `### YYYY-MM-DD — Sprint F1-X · …` con **Hecho / Aprendido / Abierto / Próximo paso**.
3. Commit final del sprint + push.
4. Notificar al revisor para gate del sprint.

---

## 5 · Cómo escalar bloqueadores

| Tipo | Acción |
|------|--------|
| Decisión técnica fuera de ADR-0011 | Parar, redactar opciones, esperar OK del humano-PC owner. Documentar como D12+ y ADR-0012+. |
| Necesitás rotar credenciales o tocar sgHermes | Parar; el humano lo hace. |
| Tests rojos que no entendés | Documentar en `SEGUIMIENTO.md §Bloqueadores actuales`, no inventar. |
| Algo del entorno se rompió (Tunnel, Warehouse, Volume) | Re-correr los scripts de `infra/` antes que reinventar. |
| Encontrás bug en F0 (rare) | Documentar como riesgo vivo en SEGUIMIENTO; si bloquea F1, ping al revisor para reabrir gate. |

---

## 6 · Definición de "F1 cerrado" (gate del revisor)

Lo decide el revisor leyendo el repo, no vos. Pero esto es lo que va a buscar:

- ✅ Las 7 verificaciones críticas V1..V7 en SEGUIMIENTO marcadas ✅ con **archivo de evidencia versionado**.
- ✅ KPIs F1 medidos con cifra real (no "estimado"):
  - Tiempo ingesta diaria total.
  - Latencia `/products/{sku}/stock` p95.
  - 5 corridas seguidas exitosas.
  - Cobertura tests `auth/` + `products/` > 70%.
- ✅ Hito F1 demo: vendedor abre la PWA desde 4G, login, busca SKU, ve stock. Evidencia en `notebooks/api/_runs/sprint_f1c_demo.md` con screenshots o curl outputs reales.
- ✅ `git status` limpio, `main` pusheado.
- ✅ Sin ⚠️ ni 🔴 en SEGUIMIENTO §F1 entregables/verificaciones.

Si todo pasa: el revisor cambia F0 ✅ / F1 ✅ / F2 🟡 en SEGUIMIENTO. Si algo queda ⚠️ o 🔴: F1 no cierra, se replanifica.

---

## 7 · Docs que debés leer (en este orden, una sola vez al empezar)

1. **Este archivo** ([`docs/handoff-f1.md`](handoff-f1.md)) — entendiste el handoff.
2. **[`docs/plan-f1.md`](plan-f1.md)** — el plan operativo completo de los 3 sprints.
3. **[`docs/decisions/0011-stack-f1.md`](decisions/0011-stack-f1.md)** — las 10 decisiones técnicas que rigen F1.
4. **[`SEGUIMIENTO.md`](../SEGUIMIENTO.md)** §Fase 1 — entregables, V1..V7, KPIs, riesgos.
5. **[`AGENT_PROMPT.md`](../AGENT_PROMPT.md)** §3 (Reglas de oro), §5 (Estándares técnicos), §8 (Lo que no hacés sin preguntar).

Los demás (PLAN.md, ADRs 0001–0010, infollm.md) son útiles como referencia pero no obligatorios para arrancar F1-A.

---

## 8 · Cuándo me pings al revisor

- Antes de mergear nada destructivo (`git reset --hard`, `DROP`, `TRUNCATE`).
- Cuando cerrás un sprint (gate intermedio).
- Cuando un riesgo se materializa de forma severa (downtime, datos corruptos, security).
- Para cerrar F1 (gate final).

Para todo lo demás, **adelante**. La planificación está hecha para que avances sin parar a preguntar cada hora.
