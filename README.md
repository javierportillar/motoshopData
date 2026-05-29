# MotoShop · Transformación digital

Aplicación práctica del marco conceptual de **Big Data y Transformación Digital del Negocio** (Maestría UAO 2025-2) sobre la BD real `motoshop2024` (MySQL 5.0, sgHermes). Dos tracks paralelos:

- **Track A · Analítico** — Databricks Lakehouse medallion (bronze→silver→gold) + ML.
- **Track T · Transaccional** — FastAPI + PWA Next.js para consulta remota.

> Fase activa, decisiones, KPIs y verificaciones críticas viven en [SEGUIMIENTO.md](SEGUIMIENTO.md).

---

## Documentación de referencia

| Archivo | Para qué |
|---------|---------|
| [INICIAR_AGENTE.md](INICIAR_AGENTE.md) | **🚀 Bootstrap de sesión.** Si arrancás como Dev Agent o Runtime Agent, leelo PRIMERO. Identifica tu rol, qué leer, qué reglas no romper. |
| [INICIAR_REVIEWER.md](INICIAR_REVIEWER.md) | **🔍 Bootstrap del rol auditor.** Si te van a usar como Reviewer Agent (auditar commits, GO/NO-GO, escribir planes), empezá acá. NO se mezcla con `INICIAR_AGENTE.md`. |
| [docs/contexto-proyecto.md](docs/contexto-proyecto.md) | **🧭 Snapshot del proyecto a hoy.** Empieza aquí si volvés al repo después de tiempo o necesitás contexto completo en 5 minutos. |
| [PLAN.md](PLAN.md) | Fuente de verdad: arquitectura, fases, stack, KPIs, VPC/BMC. |
| [SEGUIMIENTO.md](SEGUIMIENTO.md) | Estado vivo: checklist de la fase activa, bitácora, riesgos. |
| [PENDIENTES.md](PENDIENTES.md) | Lo que tiene que hacer Javier entre sesiones del agente. |
| [docs/handoff-f1.md](docs/handoff-f1.md) | **Empezá aquí si vas a desarrollar Fase 1.** Pre-flight, roles, flujo de trabajo. |
| [docs/plan-f1.md](docs/plan-f1.md) | Plan operativo detallado de Fase 1 (sprints, archivos, KPIs, riesgos). |
| [docs/plan-f1-fix1.md](docs/plan-f1-fix1.md) | Plan F1-FIX1 · Remediación post-auditoría F1. Resolvió 11/13 ítems. |
| [docs/plan-f1-fix2.md](docs/plan-f1-fix2.md) | Plan F1-FIX2 · Cierre limpio de F1 (3 evidencias + sync SEGUIMIENTO). |
| [docs/plan-f1-hardening.md](docs/plan-f1-hardening.md) | Plan F1.5 · Hardening pre-F2 (R3 idempotencia + R-X2 cache /stock). |
| [docs/plan-f1-9.md](docs/plan-f1-9.md) | Plan F1.9 · Robustez del pipeline pre-F2 (sondeo BD + lag monitor + Task Scheduler robusto + ADR-0013 fechas). |
| [docs/plan-f2.md](docs/plan-f2.md) | **Plan F2 · Silver + PWA MVP** (3 sprints: Silver, PWA login+búsqueda, PWA stock+offline). |
| [docs/plan-f2-fix1.md](docs/plan-f2-fix1.md) | **Plan F2-FIX1 · Cierre real F2.** Remedia NO-GO de F2 A/B/C con Dev A y Dev T en paralelo. |
| [infollm.md](infollm.md) | Conexión a la BD y esquema general. |
| [AGENT_PROMPT.md](AGENT_PROMPT.md) | Instrucciones del agente de IA que asiste el desarrollo. |
| [docs/decisions/](docs/decisions/README.md) | ADRs — bitácora detallada de cada decisión arquitectural. |

---

## Estructura del repo (monorepo)

```
motoshopData/
├── PLAN.md                      Plan maestro
├── SEGUIMIENTO.md               Estado vivo
├── infollm.md                   Conexión BD + esquema
├── AGENT_PROMPT.md              Briefing del agente
├── pyproject.toml               Track A · Python (tests, lint)
├── .env.example                 Plantilla de variables de entorno
│
├── docs/
│   └── decisions/               ADRs (Architecture Decision Records)
│
├── notebooks/                   Track A · Notebooks Databricks
│   ├── bronze/
│   ├── silver/
│   └── gold/
│
├── src/motoshop/                Track A · Código Python reutilizable
├── tests/                       Track A · Tests locales de transformaciones
│
├── infra/                       Scripts de infraestructura
│   ├── backup_mysql.sh          Backup mysqldump (bash · verificación crítica F0)
│   ├── backup_mysql.ps1         Backup mysqldump (PowerShell · Windows)
│   └── create_users.sql.example Plantilla de creación de usuarios MySQL read-only
│
└── motoshop-app/                Track T · API + PWA
    ├── api/                     FastAPI (Python)
    └── web/                     Next.js 14 + PWA (TypeScript)
```

Decisión de monorepo documentada en [ADR-0009](docs/decisions/0009-monorepo-vs-two-repos.md).

---

## Setup local (fase 0)

```bash
# Track A — Python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
pytest

# Track T — API
cd motoshop-app/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn motoshop_api.main:app --reload --port 8000

# Track T — Web
cd motoshop-app/web
npm install
cp .env.local.example .env.local
npm run dev
```

---

## Reglas no negociables

1. **sgHermes es intocable** — sin cambios de schema, datos ni permisos del MySQL operativo.
2. **Credenciales fuera de Git** — siempre `.env`; nunca hardcoded.
3. **Toda cifra mostrada al usuario debe cuadrar con sgHermes** dentro de la tolerancia documentada.
4. **Modelo que no supera al baseline no se libera** — preferimos el baseline conocido.
5. **Predicciones son sugerencias revisables**, no decisiones autónomas (hasta F6).

Lista completa en [AGENT_PROMPT.md](AGENT_PROMPT.md) §3.

---

## Estado actual

```
F0 ✅  F1 ✅  F2 🟡  F3 ⬜  F4 ⬜  F5 ⬜  F6 ⬜
```

**Fase 1 completada.** Ver [SEGUIMIENTO.md](SEGUIMIENTO.md) para detalles.

### Lo que funciona

| Componente | Status | URL |
|------------|--------|-----|
| API FastAPI | ✅ | `http://localhost:8000` |
| Túnel Cloudflare | ✅ | `https://api.fragloesja.uk` |
| Demo page | ✅ | `https://api.fragloesja.uk/demo` |
| Dump pipeline | ✅ | c/30 min (07:00–19:30 COL) + catch-up |
| Health check | ✅ | Cada 5 min (invisible) |
| 12 tablas Bronze | ✅ | 79,132 filas |
| API: 4 endpoints | ✅ | login, products, stock, sales |
| Tests | ✅ | 22 passing, 85% cobertura |

### Automatización

| Tarea | Horario | Descripción |
|-------|---------|-------------|
| `MotoShop_Dump` | c/30 min (07:00–19:30 COL) + retry 10min×3 | MySQL → Parquet → UC Volume con catch-up |
| `MotoShop_HealthCheck` | Cada 5 min | Verifica MySQL + API + Túnel |

### Para arrancar todo en el PC

```powershell
powershell -ExecutionPolicy Bypass -File infra\start_motoshop.ps1
```

### Para probar la demo en el celular

1. Apaga WiFi (solo 4G)
2. Ve a `https://api.fragloesja.uk/demo`
3. Haz clic en "Entrar" → "Buscar productos" → "Ver stock" → "Ver ventas"
