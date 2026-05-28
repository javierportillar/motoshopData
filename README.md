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
│   └── backup_mysql.sh          Backup mysqldump (verificación crítica F0)
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

Ver el cabecero de [SEGUIMIENTO.md](SEGUIMIENTO.md) para fase activa, próximo gate y avance global.
