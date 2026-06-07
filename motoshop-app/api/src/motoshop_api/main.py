"""Punto de entrada de la API FastAPI de MotoShop."""

from __future__ import annotations

import os
import socket
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy.exc
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
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
from motoshop_api.admin.router import router as admin_router
from motoshop_api.alerts.router import router as alerts_router
from motoshop_api.app_writes.router import router as app_writes_router
from motoshop_api.purchase_plans.router import router as purchase_plans_router


def _is_localhost() -> bool:
    """Detecta si la máquina actual es localhost."""
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return ip.startswith("127.") or ip == "::1" or hostname in ("localhost", "127.0.0.1")
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: valida ENV guardrail, carga usuarios, asegura embeddings."""
    setup_logging()
    log = structlog.get_logger("motoshop")

    # ── ENV guardrail (R16) ──────────────────────────────────────────
    if settings.env == "test":
        allow_test = os.getenv("ALLOW_TEST_ENV_IN_PROD") == "true"
        if not _is_localhost() and not allow_test:
            raise RuntimeError(
                "ENV=test detected on a non-localhost host. "
                "Set ALLOW_TEST_ENV_IN_PROD=true to override (NOT RECOMMENDED)."
            )
    log.info("env_guardrail_ok", env=settings.env)

    # ── Cargar usuarios ──────────────────────────────────────────────
    users_path = Path(settings.users_file_path)
    if not users_path.is_absolute():
        users_path = Path(__file__).resolve().parent.parent.parent / users_path
    if users_path.exists():
        users = load_users(users_path)
        log.info("users_loaded", count=len(users))
    else:
        log.warning("users_file_not_found", path=str(users_path))
    yield
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

# ── MySQL offline → 503 graceful (mitigación SPOF Windows, F6-D) ──────
@app.exception_handler(sqlalchemy.exc.OperationalError)
async def mysql_offline_handler(request: Request, _exc: sqlalchemy.exc.OperationalError) -> JSONResponse:
    """Endpoints que dependen de MySQL devuelven 503 elegante cuando la PC está apagada."""
    logger = structlog.get_logger("motoshop")
    logger.warning("mysql_unavailable", path=str(request.url.path))
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Funcionalidad no disponible en cloud. "
                "Requiere el sistema operativo encendido. "
                "Predicciones y alertas están disponibles 24/7."
            ),
            "status": "degraded",
            "available_endpoints": ["/health", "/api/auth/*", "/api/alerts/*", "/api/forecast/*", "/api/metrics/*", "/api/products/*", "/api/purchase-plans/*"],
        },
    )

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

# Routers — todos bajo /api (estándar REST)
app.include_router(auth_router, prefix="/api")
app.include_router(products_router, prefix="/api")
app.include_router(stock_router, prefix="/api")
app.include_router(sales_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")
app.include_router(push_router, prefix="/api")
app.include_router(forecast_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(app_writes_router, prefix="/api")
app.include_router(purchase_plans_router, prefix="/api")


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Endpoint de salud usado por el túnel y el monitoreo."""
    return HealthResponse(status="ok", version=__version__, env=settings.env)


@app.head("/health", tags=["meta"])
def health_head() -> Response:
    """HEAD para monitoreo externo (UptimeRobot, Render health check)."""
    return Response(status_code=200)


@app.get("/demo", response_class=HTMLResponse, tags=["meta"])
def demo():
    """Página de demo interactiva para probar la API desde el celular."""
    html_path = Path(__file__).parent / "demo.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
