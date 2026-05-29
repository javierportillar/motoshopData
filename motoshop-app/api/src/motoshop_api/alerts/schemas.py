"""Schemas Pydantic para los endpoints /alerts/*.

Contrato entre Track T (PWA) y Track A (gold.alertas_quiebre).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AlertItem(BaseModel):
    """Alerta de quiebre de stock para un SKU."""

    sku: str
    nom_producto: str
    stock_actual: float
    demanda_predicha: float
    dias_hasta_quiebre: int
    urgencia: Literal["alta", "media", "baja"]


class AlertsResponse(BaseModel):
    """Lista de alertas de quiebre ordenada por urgencia."""

    alerts: list[AlertItem]
    total: int
    timestamp: datetime
