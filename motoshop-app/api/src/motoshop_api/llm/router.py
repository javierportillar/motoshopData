"""Router de LLM: briefing diario + cost dashboard.

POST /api/llm/briefing/generate  — genera briefing, no envía
POST /api/llm/briefing/send     — genera + envía a Telegram
GET  /api/admin/llm-cost        — cost dashboard mensual
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from time import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from motoshop_api.auth.deps import get_current_user, require_role
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])
limiter = Limiter(key_func=get_remote_address)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_GERENTE_CHAT_ID", "")


# ── Schemas ───────────────────────────────────────────────────────────────


class BriefingGenerateResponse(BaseModel):
    briefing_text: str
    tokens_used: int
    tokens_input: int
    tokens_output: int
    model: str
    cost_usd: float


class BriefingSendResponse(BaseModel):
    status: str
    briefing_text: str
    telegram_message_id: int | None = None
    tokens_used: int
    model: str
    cost_usd: float


class LLMCostItem(BaseModel):
    model: str
    calls: int
    tokens_input: int
    tokens_output: int
    success_rate: float
    cost_usd: float


class LLMCostResponse(BaseModel):
    month: str
    total_calls: int
    total_tokens_input: int
    total_tokens_output: int
    total_cost_usd: float
    per_model: list[LLMCostItem]


# ── Helpers ────────────────────────────────────────────────────────────────


def _get_db_path() -> str:
    return settings.duckdb_path or (
        "/tmp/motoshop_gold.duckdb" if os.environ.get("ENV") == "prod" else "out/motoshop_gold.duckdb"
    )


def _generate_briefing() -> dict:
    from motoshop_api.llm.briefing import BriefingGenerator

    gen = BriefingGenerator(duckdb_path=_get_db_path())
    try:
        context = gen.build_context()
        if not context.get("ventas_ayer"):
            raise HTTPException(status_code=404, detail="No hay datos del día anterior para generar briefing")
        result = gen.generate(context)
        return result
    finally:
        gen.close()


def _send_telegram(text: str) -> int:
    """Envía mensaje al chat del gerente vía Telegram Bot API. Retorna message_id."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise HTTPException(status_code=503, detail="Telegram no configurado. Setear TELEGRAM_BOT_TOKEN y TELEGRAM_GERENTE_CHAT_ID")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = httpx.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=30)

    if resp.status_code != 200:
        logger.error("Telegram send failed: %d %s", resp.status_code, resp.text)
        raise HTTPException(status_code=502, detail=f"Telegram API error: {resp.status_code}")

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=f"Telegram error: {data.get('description')}")

    return data["result"]["message_id"]


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.post("/briefing/generate", response_model=BriefingGenerateResponse)
@limiter.limit("5/minute")
async def briefing_generate(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> BriefingGenerateResponse:
    """Genera el briefing diario (no lo envía). Admin-only."""
    result = _generate_briefing()
    return BriefingGenerateResponse(**result)


@router.post("/briefing/send", response_model=BriefingSendResponse)
@limiter.limit("3/minute")
async def briefing_send(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> BriefingSendResponse:
    """Genera el briefing diario y lo envía al gerente vía Telegram. Admin-only."""
    result = _generate_briefing()
    text = result["briefing_text"]

    try:
        msg_id = _send_telegram(text)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Telegram delivery failed")
        raise HTTPException(status_code=502, detail=f"Error enviando a Telegram: {exc}")

    logger.info("briefing_sent: msg_id=%d tokens=%d model=%s", msg_id, result["tokens_used"], result["model"])

    return BriefingSendResponse(
        status="sent",
        briefing_text=text,
        telegram_message_id=msg_id,
        tokens_used=result["tokens_used"],
        model=result["model"],
        cost_usd=result["cost_usd"],
    )


# ── Forecast explain ────────────────────────────────────────────────────────

class ForecastExplainResponse(BaseModel):
    text: str
    generated_at: datetime


@router.post("/forecast/explain", response_model=ForecastExplainResponse)
@limiter.limit("30/minute")
async def forecast_explain(
    request: Request,
    user: User = Depends(require_role("admin")),
) -> ForecastExplainResponse:
    """Narrativa explicativa del forecast por categoría. Admin-only.

    Genera un texto en español colombiano que explica el estado del forecast:
    WAPE, cobertura, categorías con mejor/peor desempeño, y recomendación.
    """
    from motoshop_api.llm.forecast_explainer import ForecastExplainer
    from motoshop_api.llm.client import get_llm_client

    db_path = _get_db_path()
    repo = DuckDBMetricsRepo(db_path=db_path)
    llm = get_llm_client()
    explainer = ForecastExplainer(repo, llm)
    text = explainer.explain()

    return ForecastExplainResponse(
        text=text,
        generated_at=datetime.now(),
    )


# ── Admin cost dashboard ────────────────────────────────────────────────────

# Este endpoint va en el router admin, no en llm. Lo registramos aparte.
