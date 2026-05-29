"""Schemas Pydantic para los endpoints /forecast/*.

Contrato entre Track T (PWA) y Track A (gold.forecast_demanda_sku).
Cuando la tabla gold no exista, FakeForecastRepo devuelve datos mock.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ForecastItem(BaseModel):
    """Predicción puntual para un SKU en una fecha-horizonte."""

    sku: str
    forecast_date: date         # fecha de la predicción
    horizon: int                # días: 7, 14, 30
    predicted_qty: float
    model_version: str
    confidence_lower: float | None = None
    confidence_upper: float | None = None


class ForecastMetrics(BaseModel):
    """Métricas del modelo para este SKU."""

    model_version: str
    mape: float | None = None
    smape: float | None = None
    training_date: str | None = None  # YYYY-MM-DD


class ForecastResponse(BaseModel):
    """Respuesta completa de forecast para un SKU."""

    sku: str
    forecast: list[ForecastItem]
    metrics: ForecastMetrics | None = None
