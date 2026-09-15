"""Router de LLM: briefing diario + cost dashboard.

POST /api/llm/briefing/generate  — genera briefing, no envía
POST /api/llm/briefing/send     — genera + envía a Telegram
GET  /api/admin/llm-cost        — cost dashboard mensual
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.concurrency import run_in_threadpool

from motoshop_api.auth.deps import get_current_user, require_refresh_token_or_admin, require_role
from motoshop_api.auth.tenant_dep import get_tenant, get_tenant_for_admin_or_machine
from motoshop_api.auth.users import User
from motoshop_api.config import settings
from motoshop_api.llm.client import PermanentLLMError, TransientLLMError
from motoshop_api.llm.contracts import AssistantEnvelope, AssistantRequest, problem_response
from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo
from motoshop_api.tenants import get_tenant_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm"])
briefing_router = APIRouter(prefix="/llm", tags=["llm"])
limiter = Limiter(key_func=get_remote_address)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


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


def _get_db_path(tenant: str) -> str:
    from motoshop_api.metrics.repo_duckdb import _make_db_path

    # A legacy DUCKDB_PATH override is global and therefore unsafe here: each
    # briefing must resolve through the tenant-aware snapshot path.
    return str(_make_db_path(tenant))


def _generate_briefing(tenant: str) -> dict:
    from motoshop_api.llm.briefing import BriefingGenerator

    tenant_config = get_tenant_config(tenant)
    if tenant_config is None:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant}' no configurado")
    gen = BriefingGenerator(
        duckdb_path=_get_db_path(tenant),
        tenant=tenant,
        company_name=tenant_config.nombre,
    )
    try:
        context = gen.build_context()
        context["empresa"] = tenant_config.nombre
        if not context.get("ventas_ayer"):
            raise HTTPException(
                status_code=404,
                detail="No hay datos del día anterior para generar briefing",
            )
        result = gen.generate(context)
        return result
    finally:
        gen.close()


def _briefing_dependency_http_error(
    exc: PermanentLLMError | TransientLLMError,
) -> HTTPException:
    if isinstance(exc, TransientLLMError):
        return HTTPException(
            status_code=503,
            detail="El proveedor de lenguaje no está disponible temporalmente.",
            headers={"Retry-After": "30"},
        )
    return HTTPException(
        status_code=502,
        detail="El proveedor de lenguaje rechazó la generación del briefing.",
    )


def _generate_briefing_for_delivery(tenant: str) -> dict:
    """Retry one transient generation failure before any Telegram side effect."""
    for attempt in range(2):
        try:
            return _generate_briefing(tenant)
        except PermanentLLMError as exc:
            logger.error("Permanent briefing generation failure tenant=%s", tenant)
            raise _briefing_dependency_http_error(exc) from exc
        except TransientLLMError as exc:
            if attempt == 0:
                logger.warning("Briefing generation failed; retrying tenant=%s", tenant)
                continue
            logger.error("Briefing generation failed after retry tenant=%s", tenant)
            raise _briefing_dependency_http_error(exc) from exc

    raise AssertionError("unreachable")


def _tenant_message(tenant: str, text: str) -> str:
    tenant_config = get_tenant_config(tenant)
    company_name = tenant_config.nombre if tenant_config else tenant
    return f"[{company_name}]\n{text}"


def _send_telegram(text: str, tenant: str) -> int:
    """Envía mensaje al chat del gerente vía Telegram Bot API. Retorna message_id."""
    chat_env = f"TELEGRAM_CHAT_ID_{tenant.upper().replace('-', '_')}"
    chat_id = os.environ.get(chat_env, "")
    if not TELEGRAM_TOKEN or not chat_id:
        raise HTTPException(
            status_code=503,
            detail=f"Destino de Telegram no configurado para el tenant '{tenant}'",
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
    except httpx.HTTPError:
        # Do not log the exception: httpx may include the token-bearing URL.
        logger.error("Telegram request failed for tenant=%s", tenant)
        raise HTTPException(status_code=502, detail="No se pudo contactar Telegram") from None

    if resp.status_code != 200:
        logger.error("Telegram send failed: tenant=%s status=%d", tenant, resp.status_code)
        raise HTTPException(status_code=502, detail=f"Telegram API error: {resp.status_code}")

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(status_code=502, detail=f"Telegram error: {data.get('description')}")

    return data["result"]["message_id"]


# ── Endpoints ──────────────────────────────────────────────────────────────


@briefing_router.post("/briefing/generate", response_model=BriefingGenerateResponse)
@limiter.limit("5/minute")
async def briefing_generate(
    request: Request,
    _authorized: bool = Depends(require_refresh_token_or_admin),
    tenant: str = Depends(get_tenant_for_admin_or_machine),
) -> BriefingGenerateResponse:
    """Genera el briefing diario (no lo envía). Admin JWT or machine token only."""
    try:
        result = await run_in_threadpool(_generate_briefing, tenant)
    except (PermanentLLMError, TransientLLMError) as exc:
        logger.error("Briefing generation dependency failure tenant=%s", tenant)
        raise _briefing_dependency_http_error(exc) from exc
    result["briefing_text"] = _tenant_message(tenant, result["briefing_text"])
    return BriefingGenerateResponse(**result)


@briefing_router.post("/briefing/send", response_model=BriefingSendResponse)
@limiter.limit("3/minute")
async def briefing_send(
    request: Request,
    _authorized: bool = Depends(require_refresh_token_or_admin),
    tenant: str = Depends(get_tenant_for_admin_or_machine),
) -> BriefingSendResponse:
    """Generate and send the tenant briefing with admin or machine-token authorization."""
    result = await run_in_threadpool(_generate_briefing_for_delivery, tenant)
    text = _tenant_message(tenant, result["briefing_text"])

    try:
        msg_id = await run_in_threadpool(_send_telegram, text, tenant)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected Telegram delivery failure for tenant=%s", tenant)
        raise HTTPException(status_code=502, detail="Error inesperado enviando a Telegram") from exc

    logger.info(
        "briefing_sent: tenant=%s msg_id=%d tokens=%d model=%s",
        tenant,
        msg_id,
        result["tokens_used"],
        result["model"],
    )

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
    from motoshop_api.llm.client import get_llm_client
    from motoshop_api.llm.forecast_explainer import ForecastExplainer

    db_path = str(settings.duckdb_path) if settings.duckdb_path else _get_db_path("motoshop")
    repo = DuckDBMetricsRepo(db_path=db_path)
    llm = get_llm_client()
    explainer = ForecastExplainer(repo, llm)
    text = explainer.explain()

    return ForecastExplainResponse(
        text=text,
        generated_at=datetime.now(),
    )


# ── Q&A Chat ────────────────────────────────────────────────────────────────


QAChatRequest = AssistantRequest
QAChatResponse = AssistantEnvelope


class ConversationResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str
    status: str
    created_at: str
    updated_at: str
    last_message_at: str
    message_count: int = 0


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    tools_used: list[str] = []
    sources: list[dict] = []


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    archived: bool | None = None


@router.post("/qa/chat", response_model=QAChatResponse)
@limiter.limit("60/minute")
async def qa_chat(
    request: Request,
    body: AssistantRequest,
    user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> QAChatResponse:
    """Chat conversacional con tool use sobre DuckDB.

    El LLM decide automáticamente qué tools usar para responder.
    Máximo 20 turnos por sesión (conversation_id).
    """
    from motoshop_api.llm.qa_chat import get_qa_chat

    qa = get_qa_chat(tenant=tenant, user_id=user.username)
    try:
        result = await run_in_threadpool(
            qa.chat, body.message, body.conversation_id, body.request_id
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Conversación no encontrada") from None
    except TransientLLMError:
        response = problem_response(
            503, "https://api.motoshop/errors/provider-unavailable",
            "El proveedor de inteligencia no está disponible temporalmente.",
            body.request_id or request.headers.get("X-Request-ID", "unknown"),
        )
        response.headers["Retry-After"] = "30"
        return response
    except PermanentLLMError:
        return problem_response(
            502, "https://api.motoshop/errors/provider-rejected",
            "El proveedor de inteligencia rechazó la consulta.",
            body.request_id or request.headers.get("X-Request-ID", "unknown"),
        )
    return AssistantEnvelope(
        status=result.get("status", "complete"), tenant_id=result.get("tenant_id", tenant),
        text=result.get("text", ""), conversation_id=result.get("conversation_id", ""),
        turn_count=result.get("turn_count", 0), tools_used=result.get("tools_used", []),
        sources=result.get("sources", []), freshness=result.get("freshness", []),
        entity_refs=result.get("entity_refs", []), attachments=result.get("attachments", []),
    )


@router.post("/chat/conversations", response_model=ConversationResponse)
async def create_chat_conversation(
    user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> ConversationResponse:
    from motoshop_api.llm.conversations.repository import get_conversation_repository

    repo = get_conversation_repository()
    row = await run_in_threadpool(repo.create_conversation, tenant, user.username)
    return ConversationResponse(**row)


@router.get("/chat/conversations", response_model=list[ConversationResponse])
async def list_chat_conversations(
    user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> list[ConversationResponse]:
    from motoshop_api.llm.conversations.repository import get_conversation_repository

    repo = get_conversation_repository()
    rows = await run_in_threadpool(repo.list_conversations, tenant, user.username)
    return [ConversationResponse(**row) for row in rows]


@router.get("/chat/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_chat_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> list[MessageResponse]:
    from motoshop_api.llm.conversations.repository import get_conversation_repository

    repo = get_conversation_repository()
    owner = await run_in_threadpool(repo.get_conversation, tenant, user.username, conversation_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    rows = await run_in_threadpool(repo.list_messages, tenant, user.username, conversation_id)
    return [MessageResponse(**row) for row in rows]


@router.patch("/chat/conversations/{conversation_id}", response_model=ConversationResponse)
async def patch_chat_conversation(
    conversation_id: str,
    body: ConversationPatch,
    user: User = Depends(get_current_user),
    tenant: str = Depends(get_tenant),
) -> ConversationResponse:
    from motoshop_api.llm.conversations.repository import get_conversation_repository

    repo = get_conversation_repository()
    row = await run_in_threadpool(repo.get_conversation, tenant, user.username, conversation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    if body.archived:
        await run_in_threadpool(repo.archive_conversation, tenant, user.username, conversation_id)
    if body.title is not None and hasattr(repo, "rename_conversation"):
        await run_in_threadpool(
            repo.rename_conversation, tenant, user.username, conversation_id, body.title
        )
    updated = await run_in_threadpool(repo.get_conversation, tenant, user.username, conversation_id)
    return ConversationResponse(**(updated or row))


# ── Admin cost dashboard ────────────────────────────────────────────────────

# Este endpoint va en el router admin, no en llm. Lo registramos aparte.
