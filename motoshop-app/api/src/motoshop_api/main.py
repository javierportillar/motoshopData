"""Punto de entrada de la API FastAPI de MotoShop."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from motoshop_api import __version__
from motoshop_api.config import settings

app = FastAPI(
    title="MotoShop API",
    version=__version__,
    description="API de consulta remota para MotoShop (Track T). Solo lectura en F1-F4.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Endpoint de salud usado por el túnel y el monitoreo."""
    return HealthResponse(status="ok", version=__version__, env=settings.env)
