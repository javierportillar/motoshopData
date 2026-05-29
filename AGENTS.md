# AGENTS.md — MotoShop repo guidance for AI agents

## Quick orientation

Monorepo with two independent tracks. **Track A** (Databricks Lakehouse) and **Track T** (FastAPI + Next.js PWA). Each has its own `pyproject.toml` and venv.

```
javidevmoto/
├── infra/                  Scripts de infraestructura (Python + PowerShell)
├── notebooks/bronze/       Databricks notebooks (Track A)
├── src/motoshop/           Python reutilizable (Track A, future)
├── tests/                  Tests Track A
├── motoshop-app/
│   ├── api/                FastAPI (Track T) — its OWN pyproject.toml + venv
│   └── web/                Next.js 14 PWA (TypeScript)
├── docs/decisions/         ADRs
├── SEGUIMIENTO.md          Estado vivo del proyecto
└── PLAN.md                 Fuente de verdad: arquitectura, fases, stack
```

## Commands that matter

### Track A (root)
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .
pytest
```

### Track A infra (separate venv for dump scripts)
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto
python -m venv .venv-infra
.\.venv-infra\Scripts\Activate.ps1
pip install -r infra/requirements.txt
```

### Track T — API
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -m "not integration" -v
```

### Track T — Web
```powershell
cd C:\Users\MotoShop\Documents\javidevmoto\motoshop-app\web
npm install
npm run dev
```

### Lint / format
```powershell
ruff check .          # lint
ruff format .         # format
# Both tracks use ruff with line-length=100, target py311
```

## Critical gotchas

- **MySQL 5.0 does NOT support `utf8mb4`.** Use `charset="utf8"` in mysql-connector. This is already handled in `dump_to_cloud.py` and the API engine.
- **Three separate Python environments:** root `.venv` (Track A), `.venv-infra` (dump scripts), `motoshop-app/api/.venv` (API). Don't mix them up.
- **`_staging/` is gitignored.** It's the local staging area for Parquet files before upload to Databricks UC Volume.
- **`users.yaml` is gitignored.** Contains real credentials. Never commit it.
- **`.env` is gitignored.** Contains MySQL passwords, Databricks PAT, Cloudflare tokens. `.env.example` is versioned.
- **Task Scheduler runs on Windows.** The dump pipeline is `infra/run_dump.ps1` → `dump_to_cloud.py`. Not Databricks Workflows.
- **sgHermes MySQL is read-only.** Users `analytics`, `api_read`, `javier` are all `@localhost` with SELECT-only permissions.

## Testing quirks

- API tests use `app.dependency_overrides` + `FakeRepos` for unit tests (no MySQL needed).
- Integration tests are marked `@pytest.mark.integration` — skip with `pytest -m "not integration"`.
- `conftest.py` sets `JWT_SECRET` and `ENV=test` as env vars BEFORE any imports. Don't reorder.
- Rate limiter storage is cleared between tests via `_reset_rate_limiter` fixture.

## File reading order (for new sessions)

1. `SEGUIMIENTO.md` — current state, active phase, risks
2. `PLAN.md` — architecture, phases, stack decisions
3. `docs/plan-f1-9.md` (or current phase plan) — if working on a specific phase
4. `AGENT_PROMPT.md` — full methodology and rules

## Commit conventions

Prefix with phase and type: `feat(F1.9):`, `docs(F1-FIX2):`, `fix(API):`. Spanish messages OK.

## 12 core tables (F1 Bronze)

`facventas`, `detfventas`, `productos`, `auxinventario`, `bodegas`, `terceros`, `compras`, `detcompras`, `sucursales`, `formapago`, `subproduct`, `preciosxpro`

Full schema survey of all 170 tables: `notebooks/bronze/_runs/full_schema_survey_2026-05-29.md`
