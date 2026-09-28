from __future__ import annotations

from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
from motoshop_api.llm.qa_chat import ConversationManager, QAChat


class _NoProvider:
    def complete_with_tools(self, *args, **kwargs):
        raise AssertionError("Supported custom data intents must use typed query tools")


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def get_data_freshness(self) -> dict:
        return {
            "fecha_maxima": "2026-09-26",
            "por_tabla": {
                "silver_fact_compras": "2026-09-26",
                "silver_fact_ventas": "2026-09-26",
            },
        }

    def run(self, name: str, args: dict) -> dict:
        self.calls.append((name, args))
        if name == "get_top_compras_periodos" and not args.get("periods"):
            return {
                "status": "needs_clarification",
                "respuesta_fallback": "¿De qué mes y año querés consultar el ranking de compras?",
                "compras": [],
                "sources": [],
                "freshness": [],
            }
        if name == "get_compras_periodo" and not args.get("periods"):
            return {
                "status": "needs_clarification",
                "respuesta_fallback": (
                    "No tengo un corte válido de compras para inferir el año; indicame el año."
                ),
                "compras": [],
                "sources": [],
                "freshness": [],
            }
        return {
            "status": "complete",
            "respuesta_fallback": f"Query executed: {name}",
            "compras": [],
            "productos": [],
            "sources": [],
            "freshness": [],
        }


def _chat(executor: _RecordingExecutor) -> QAChat:
    names = {
        "get_top_compras_periodos",
        "get_compras_periodo",
        "get_top_productos_periodo",
        "get_productos_para_reponer",
    }
    return QAChat(
        _NoProvider(),
        ConversationManager(),
        executor,
        [{"function": {"name": name}} for name in names],
        tenant_id="motoshop",
        user_id="buyer",
        repository=InMemoryConversationRepository(),
    )


def test_custom_examples_keep_period_metric_and_supplier_filter() -> None:
    executor = _RecordingExecutor()
    chat = _chat(executor)

    product_rank = chat.chat("¿Cuál es el producto más vendido de septiembre y agosto?")
    supplier_rank = chat.chat("¿Cuál es la compra más grande hecha hacia MILIS en agosto?")
    listing = chat.chat("¿Cuáles son las compras realizadas el mes de agosto?")
    detail_followup = chat.chat(
        "Detalla esas compras, dime el proveedor y el total",
        conversation_id=listing["conversation_id"],
    )
    summary = chat.chat(
        "¿El mes de agosto tiene compras?",
        conversation_id=listing["conversation_id"],
    )
    replenishment = chat.chat(
        "¿Qué productos no tengo en stock y debería enlistar para mi siguiente compra?"
    )

    assert [name for name, _ in executor.calls] == [
        "get_top_productos_periodo",
        "get_top_compras_periodos",
        "get_compras_periodo",
        "get_compras_periodo",
        "get_compras_periodo",
        "get_productos_para_reponer",
    ]
    assert executor.calls[0][1]["metric"] == "units"
    assert [period["date_from"] for period in executor.calls[0][1]["periods"]] == [
        "2026-09-01", "2026-08-01",
    ]
    assert executor.calls[1][1]["supplier_query"] == "milis"
    assert executor.calls[2][1]["view"] == executor.calls[3][1]["view"] == "list"
    assert executor.calls[3][1]["periods"] == executor.calls[2][1]["periods"]
    assert executor.calls[4][1]["view"] == "summary"
    assert executor.calls[5][1] == {
        "target_cover_days": 45,
        "sales_window_days": 180,
        "limit": 50,
    }
    assert product_rank["tools_used"] == ["get_top_productos_periodo"]
    assert supplier_rank["tools_used"] == ["get_top_compras_periodos"]
    assert detail_followup["tools_used"] == ["get_compras_periodo"]
    assert summary["tools_used"] == ["get_compras_periodo"]
    assert replenishment["tools_used"] == ["get_productos_para_reponer"]


def test_today_and_yesterday_rank_the_exact_sales_dates() -> None:
    executor = _RecordingExecutor()
    chat = _chat(executor)
    today = chat.chat("¿Cuál fue el producto más vendido el día de hoy?")
    yesterday = chat.chat("¿Y del día de ayer?", conversation_id=today["conversation_id"])

    assert [name for name, _ in executor.calls] == [
        "get_top_productos_periodo", "get_top_productos_periodo",
    ]
    assert executor.calls[0][1]["periods"][0]["date_from"] == "2026-09-26"
    assert executor.calls[1][1]["periods"][0]["date_from"] == "2026-09-25"
    assert executor.calls[0][1]["metric"] == executor.calls[1][1]["metric"] == "units"
    assert yesterday["tools_used"] == ["get_top_productos_periodo"]


def test_month_correction_does_not_reuse_a_ranking_across_an_unrelated_turn() -> None:
    class _ConversationalLLM:
        def complete_with_tools(self, *args, **kwargs):
            return {"text": "Respuesta conversacional.", "tool_calls": []}

    executor = _RecordingExecutor()
    chat = QAChat(
        _ConversationalLLM(),
        ConversationManager(),
        executor,
        [{"function": {"name": "get_top_compras_periodos"}}],
        tenant_id="motoshop",
        user_id="buyer",
        repository=InMemoryConversationRepository(),
    )
    first = chat.chat("Top 3 compras más grandes de agosto 2026")
    chat.chat("Cambiemos de tema, ¿cómo van las ventas?", conversation_id=first["conversation_id"])
    corrected = chat.chat(
        "Las del mes de agosto, no septiembre",
        conversation_id=first["conversation_id"],
    )

    assert len(executor.calls) == 1
    assert corrected["tools_used"] == []
    assert corrected["text"] == "Respuesta conversacional."


def test_purchase_ranking_without_period_asks_for_month_not_for_supplier() -> None:
    executor = _RecordingExecutor()
    chat = _chat(executor)

    response = chat.chat("¿Cuál es la compra más grande?")

    assert executor.calls == [
        ("get_top_compras_periodos", {"periods": [], "view": "top", "limit": 3, "page": 1})
    ]
    assert response["status"] == "needs_clarification"
    assert response["text"] == "¿De qué mes y año querés consultar el ranking de compras?"
    assert "proveedor" not in response["text"].casefold()


def test_purchase_month_does_not_infer_year_from_sales_cutoff() -> None:
    from motoshop_api.llm.qa_chat import _purchase_audit_period

    class _NoPurchaseCutoffExecutor(_RecordingExecutor):
        def get_data_freshness(self) -> dict:
            return {
                "fecha_maxima": "2026-09-26",
                "por_tabla": {
                    "silver_fact_compras": None,
                    "silver_fact_ventas": "2026-09-26",
                },
            }

    executor = _NoPurchaseCutoffExecutor()
    response = _chat(executor).chat("¿Cuáles son las compras realizadas en agosto?")

    assert executor.calls == [
        (
            "get_compras_periodo",
            {"periods": [], "view": "list", "limit": 50, "page": 1},
        )
    ]
    assert response["status"] == "needs_clarification"
    assert "inferir el año" in response["text"]
    assert _purchase_audit_period("Analiza las compras de agosto", None) is None
    assert _purchase_audit_period("Analiza las compras de agosto 2025", None) == {
        "date_from": "2025-08-01",
        "date_to": "2025-08-31",
    }
