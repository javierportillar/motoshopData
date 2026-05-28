# MotoShop · Transformación digital

Aplicación práctica del marco conceptual de **Big Data y Transformación Digital del Negocio** (Maestría UAO 2025-2) sobre la BD real `motoshop2024` (MySQL 5.0, sgHermes). Dos tracks paralelos:

- **Track A · Analítico** — Databricks Lakehouse medallion (bronze→silver→gold) + ML.
- **Track T · Transaccional** — FastAPI + PWA Next.js para consulta remota.

> Fase activa, decisiones, KPIs y verificaciones críticas viven en [SEGUIMIENTO.md](SEGUIMIENTO.md).

---

## Documentación de referencia

| Archivo | Para qué |
|---------|---------|
| [PLAN.md](PLAN.md) | Fuente de verdad: arquitectura, fases, stack, KPIs, VPC/BMC. |
| [SEGUIMIENTO.md](SEGUIMIENTO.md) | Estado vivo: checklist de la fase activa, bitácora, riesgos. |
| [PENDIENTES.md](PENDIENTES.md) | Lo que tiene que hacer Javier entre sesiones del agente. |
| [docs/handoff-f1.md](docs/handoff-f1.md) | **Empezá aquí si vas a desarrollar Fase 1.** Pre-flight, roles, flujo de trabajo. |
| [docs/plan-f1.md](docs/plan-f1.md) | Plan operativo detallado de Fase 1 (sprints, archivos, KPIs, riesgos). |
| [docs/plan-f1-fix1.md](docs/plan-f1-fix1.md) | **Plan F1-FIX1 · Remediación post-auditoría.** Mientras no cierre, F1 sigue 🟡. |
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
| Databricks Job | ✅ | 3x/día (12PM, 8PM, 2AM) |
| Health check | ✅ | Cada 5 min (invisible) |
| 12 tablas Bronze | ✅ | 79,132 filas |
| API: 4 endpoints | ✅ | login, products, stock, sales |
| Tests | ✅ | 22 passing, 85% cobertura |

### Automatización

| Tarea | Horario | Descripción |
|-------|---------|-------------|
| `MotoShop_Dump_Midday` | 12:00 PM | MySQL → Parquet → UC Volume |
| `MotoShop_Dump_Evening` | 8:00 PM | MySQL → Parquet → UC Volume |
| `MotoShop_Dump_Night` | 2:00 AM | MySQL → Parquet → UC Volume |
| `MotoShop_HealthCheck` | Cada 5 min | Verifica MySQL + API + Túnel |

### Para arrancar todo en el PC

```powershell
powershell -ExecutionPolicy Bypass -File infra\start_motoshop.ps1
```

### Para probar la demo en el celular

1. Apaga WiFi (solo 4G)
2. Ve a `https://api.fragloesja.uk/demo`
3. Haz clic en "Entrar" → "Buscar productos" → "Ver stock" → "Ver ventas"
