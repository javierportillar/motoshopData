# motoshop-api

API FastAPI de MotoShop (Track T). Corre junto al MySQL en el PC; se expone vía túnel Cloudflare.

## Requisitos

- Python 3.11+
- `pip` o `uv`
- MySQL 5.0 corriendo en el PC

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

## Endpoints disponibles

| Método | Ruta | Descripción | Auth |
|--------|------|-------------|------|
| GET | `/health` | Health check | No |
| GET | `/demo` | Página de demo para celular | No |
| POST | `/auth/login` | Login con username/password | No |
| POST | `/auth/refresh` | Renovar tokens | No |
| GET | `/products?q=&limit=&offset=` | Buscar productos con paginación | Sí |
| GET | `/products/{sku}/stock` | Ver stock de un SKU por bodega | Sí |
| GET | `/sales/recent?since=&limit=` | Ventas recientes | Sí |

## Demo page (para celular)

```
https://api.fragloesja.uk/demo
```

Página interactiva para probar la API desde un celular en 4G.

> **Credenciales rotadas durante F7:** las contraseñas se entregan por canal seguro al equipo. No versionar secrets.

## Tests

```bash
pytest                    # correr todos
pytest --cov              # con cobertura
pytest -m "not integration"  # solo unit tests
```

## Lint y formato

```bash
ruff check .
ruff format .
```

## Estado por fase

| Fase | Estado |
|------|--------|
| F0 | scaffold + `/health` |
| F1 | 4 endpoints + JWT + rate limiting + logging + demo page |
| F2+ | ver `PLAN.md` |

## Automatización

La API se ejecuta automáticamente via Task Scheduler:
- `start_motoshop.ps1` — arranca API + túnel
- `check_health.ps1` — verifica cada 5 min
- Logs en `logs/`
