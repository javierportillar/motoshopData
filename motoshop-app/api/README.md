# motoshop-api

API FastAPI de MotoShop (Track T). Corre junto al MySQL en el PC; se expone vía túnel remoto (P2 pendiente).

## Requisitos

- Python 3.11+
- `pip` o `uv`

## Setup local

```bash
cd motoshop-app/api
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env          # rellenar valores reales
```

## Correr en dev

```bash
uvicorn motoshop_api.main:app --reload --port 8000
```

- `GET /health` → `{ "status": "ok", "version": "...", "env": "dev" }`
- `GET /docs` → OpenAPI interactivo

## Tests

```bash
pytest
```

## Lint y formato

```bash
ruff check .
ruff format .
```

## Estado por fase

| Fase | Estado |
|------|--------|
| F0   | scaffold + `/health` |
| F1   | endpoints de lectura + JWT + rate limiting |
| F2+  | ver `PLAN.md` |
