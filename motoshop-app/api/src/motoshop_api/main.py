"""Punto de entrada de la API FastAPI de MotoShop."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from motoshop_api import __version__
from motoshop_api.auth.router import router as auth_router
from motoshop_api.auth.users import load_users
from motoshop_api.config import settings
from motoshop_api.logging import RequestIDMiddleware, setup_logging
from motoshop_api.products.router import router as products_router
from motoshop_api.sales.router import router as sales_router
from motoshop_api.stock.router import router as stock_router
from motoshop_api.health.router import router as health_router
from motoshop_api.metrics.router import router as metrics_router
from motoshop_api.push.router import router as push_router
from motoshop_api.forecast.router import router as forecast_router
from motoshop_api.alerts.router import router as alerts_router
from motoshop_api.app_writes.router import router as app_writes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Carga usuarios al iniciar la API."""
    setup_logging()
    log = structlog.get_logger("motoshop")
    users_path = Path(settings.users_file_path)
    if not users_path.is_absolute():
        users_path = Path(__file__).resolve().parent.parent.parent / users_path
    if users_path.exists():
        users = load_users(users_path)
        log.info("users_loaded", count=len(users))
    else:
        log.warning("users_file_not_found", path=str(users_path))
    yield


app = FastAPI(
    title="MotoShop API",
    version=__version__,
    description="API de consulta remota para MotoShop (Track T). Lectura en F1-F4, escritura app_* desde F5.",
    lifespan=lifespan,
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Request ID + PII redaction
app.add_middleware(RequestIDMiddleware)

# Routers
app.include_router(auth_router)
app.include_router(products_router)
app.include_router(stock_router)
app.include_router(sales_router)
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(push_router)
app.include_router(forecast_router)
app.include_router(alerts_router)
app.include_router(app_writes_router)


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Endpoint de salud usado por el túnel y el monitoreo."""
    return HealthResponse(status="ok", version=__version__, env=settings.env)


@app.get("/demo", response_class=HTMLResponse, tags=["meta"])
def demo():
    """Página de demo interactiva para probar la API desde el celular."""
    html_path = Path(__file__).parent / "demo.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
