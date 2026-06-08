"""QAChat — orquestador de Q&A con tool use sobre DuckDB.

Loop: mensaje usuario → LLM con tools → ejecutar tool calls → resultado → respuesta final.
"""

from __future__ import annotations

import json as _json
import logging
import time
from uuid import uuid4

logger = logging.getLogger(__name__)

QA_SYSTEM = """Sos un asistente de MotoShop, una tienda de motopartes en Cali, Colombia. El gerente te hace preguntas en lenguaje natural sobre el negocio.

Reglas:
- Usá las tools disponibles para obtener datos REALES del negocio.
- NUNCA inventés cifras. Toda cifra debe venir de una tool.
- Si una pregunta no se puede responder con las tools disponibles, decílo honestamente.
- Tono natural colombiano, directo, máximo 5 oraciones por respuesta.
- Cuando uses una cifra, mencioná de dónde viene (ej: "según los KPIs de hoy...").
- Los valores monetarios se expresan en pesos colombianos (COP)."""

CONVERSATION_TTL = 30 * 60  # 30 minutos
MAX_TURNS = 20
MAX_TOOL_ITERATIONS = 5


# ── Conversation Manager ──────────────────────────────────────────────────

class ConversationManager:
    """Memoria en proceso con TTL. Sesiones por conversation_id."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def get_or_create(self, conversation_id: str) -> dict:
        now = time.time()
        session = self._sessions.get(conversation_id)
        if session and (now - session["last_active"]) < CONVERSATION_TTL:
            session["last_active"] = now
            return session
        # Nueva sesión
        session = {
            "id": conversation_id,
            "messages": [],
            "created_at": now,
            "last_active": now,
            "turn_count": 0,
        }
        self._sessions[conversation_id] = session
        return session

    def add_turn(self, conversation_id: str, user_msg: str, assistant_msg: str, tool_calls_used: list[str]):
        session = self._sessions.get(conversation_id)
        if not session:
            return
        session["messages"].append({"role": "user", "content": user_msg})
        session["messages"].append({"role": "assistant", "content": assistant_msg})
        session["turn_count"] += 1
        session["last_active"] = time.time()
        # Guardar solo últimos 20 mensajes para no saturar contexto
        if len(session["messages"]) > 40:
            session["messages"] = session["messages"][-40:]

    def gc(self):
        """Limpia sesiones expiradas."""
        now = time.time()
        expired = [cid for cid, s in self._sessions.items() if (now - s["last_active"]) > CONVERSATION_TTL]
        for cid in expired:
            del self._sessions[cid]

    def is_over_limit(self, conversation_id: str) -> bool:
        session = self._sessions.get(conversation_id)
        return session is not None and session["turn_count"] >= MAX_TURNS


# ── Q&A Chat ──────────────────────────────────────────────────────────────

_conversation_mgr = ConversationManager()


def get_qa_chat():
    from motoshop_api.llm.client import get_llm_client
    from motoshop_api.llm.tools import ToolExecutor, TOOL_DEFINITIONS
    return QAChat(get_llm_client(), _conversation_mgr, ToolExecutor(), TOOL_DEFINITIONS)


class QAChat:
    def __init__(self, llm_client, conversation_mgr, tool_executor, tool_defs):
        self.llm = llm_client
        self.cm = conversation_mgr
        self.executor = tool_executor
        self.tool_defs = tool_defs

    def chat(self, message: str, conversation_id: str | None = None) -> dict:
        cid = conversation_id or str(uuid4())

        # GC antes de arrancar
        self.cm.gc()

        # Validaciones
        if self.cm.is_over_limit(cid):
            return {"text": "Has alcanzado el límite de 20 turnos en esta sesión. Iniciá una nueva conversación.", "conversation_id": cid, "turn_count": MAX_TURNS, "tools_used": []}

        if len(message) > 500:
            return {"text": "La pregunta es muy larga. Intentá con menos de 500 caracteres.", "conversation_id": cid, "turn_count": 0, "tools_used": []}

        session = self.cm.get_or_create(cid)

        # Construir mensajes
        messages = [{"role": "system", "content": QA_SYSTEM}]
        messages.extend(session["messages"][-30:])  # últimos 30 mensajes
        messages.append({"role": "user", "content": message})

        tool_calls_used = []
        final_text = ""

        try:
            # Loop tool calls
            for _ in range(MAX_TOOL_ITERATIONS):
                result = self.llm.complete_with_tools(messages, self.tool_defs, max_tokens=1000)
                tc = result.get("tool_calls", [])

                if not tc:
                    final_text = result["text"]
                    break

                # Agregar assistant message con tool calls
                assistant_msg = {"role": "assistant", "content": result["text"] or ""}
                if tc:
                    assistant_msg["tool_calls"] = tc
                messages.append(assistant_msg)

                # Ejecutar cada tool
                for call in tc:
                    fn = call.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = _json.loads(fn.get("arguments", "{}"))
                    except _json.JSONDecodeError:
                        args = {}
                    tool_result = self.executor.run(name, args)
                    tool_calls_used.append(name)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": _json.dumps(tool_result, ensure_ascii=False),
                    })
                    logger.info("qa_tool: %s(%s) → %s", name, args, str(tool_result)[:100])

            if not final_text:
                final_text = "No pude obtener una respuesta concreta con las tools disponibles. ¿Podés reformular la pregunta?"

        except Exception as exc:
            logger.exception("qa_chat_error")
            final_text = f"Error interno al procesar tu consulta. Intentá de nuevo."

        # Registrar turno
        self.cm.add_turn(cid, message, final_text, tool_calls_used)

        # Cost logging
        _log_qa_cost(result.get("model", "unknown"), result.get("tokens_input", 0), result.get("tokens_output", 0), cid)

        return {
            "text": final_text,
            "conversation_id": cid,
            "turn_count": session["turn_count"],
            "tools_used": tool_calls_used,
        }


def _log_qa_cost(model: str, tokens_input: int, tokens_output: int, conversation_id: str) -> None:
    try:
        from datetime import datetime, timezone
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": "qa_chat",
            "model": model,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "conversation_id": conversation_id,
            "success": True,
        }
        with open("/tmp/llm_usage.jsonl", "a") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass
