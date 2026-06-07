"""LLMClient — dual-API wrapper (OpenCode GO + Zen).

GO: https://opencode.ai/zen/go/v1 (primario, qwen3.6-plus, sin reasoning)
Zen: https://opencode.ai/zen/v1 (fallback, deepseek-v4-flash-free, necesita max_tokens alto)

Dual-key: OPENCODE_API_KEY (GO) + OPENCODE_API_KEY_FALLBACK (Zen).
Si el modelo primario falla, intenta el fallback con su propia API/key.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────

GO_API_BASE = os.environ.get("GO_API_BASE", "https://opencode.ai/zen/go/v1")
GO_API_KEY = os.environ.get("OPENCODE_API_KEY", "")
GO_MODEL = os.environ.get("GO_MODEL", "qwen3.6-plus")
GO_MAX_TOKENS = int(os.environ.get("GO_MAX_TOKENS", "800"))

ZEN_API_BASE = os.environ.get("ZEN_API_BASE", "https://opencode.ai/zen/v1")
ZEN_API_KEY = os.environ.get("OPENCODE_API_KEY_FALLBACK", "")
ZEN_MODEL = os.environ.get("ZEN_MODEL", "deepseek-v4-flash-free")
ZEN_MAX_TOKENS = int(os.environ.get("ZEN_MAX_TOKENS", "8000"))

TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "120"))

_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


class LLMClient:
    """Cliente HTTP dual-API: GO primario, Zen fallback."""

    def __init__(self):
        self._backends = []
        if GO_API_KEY:
            self._backends.append({
                "name": "go",
                "base": GO_API_BASE.rstrip("/"),
                "key": GO_API_KEY,
                "model": GO_MODEL,
                "max_tokens": GO_MAX_TOKENS,
            })
        if ZEN_API_KEY:
            self._backends.append({
                "name": "zen",
                "base": ZEN_API_BASE.rstrip("/"),
                "key": ZEN_API_KEY,
                "model": ZEN_MODEL,
                "max_tokens": ZEN_MAX_TOKENS,
            })

        self._http = httpx.Client(timeout=httpx.Timeout(TIMEOUT))
        if not self._backends:
            logger.warning("No API keys configured — LLM calls will fail")

    def complete(self, prompt: str, *, max_tokens: int | None = None, system: str = "") -> dict:
        """Chat completion. Retorna {text, tokens_used, model, cost_usd, backend}."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call(messages, max_tokens)

    def _call(self, messages: list[dict], max_tokens: int | None = None) -> dict:
        last_error = None

        for backend in self._backends:
            try:
                mt = max_tokens if max_tokens is not None else backend["max_tokens"]
                body = {
                    "model": backend["model"],
                    "messages": messages,
                    "max_tokens": mt,
                    "temperature": 0.3,
                }

                resp = self._http.post(
                    f"{backend['base']}/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {backend['key']}",
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code in (401, 403):
                    logger.warning("LLM %d from %s/%s", resp.status_code, backend["name"], backend["model"])
                    last_error = f"{resp.status_code}"
                    continue
                if resp.status_code >= 500:
                    logger.warning("LLM %d from %s/%s", resp.status_code, backend["name"], backend["model"])
                    last_error = f"{resp.status_code}"
                    continue

                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    err_msg = data["error"].get("message", str(data["error"]))
                    logger.warning("LLM API error %s/%s: %s", backend["name"], backend["model"], err_msg)
                    last_error = err_msg
                    continue

                choice = data["choices"][0]
                msg = choice["message"]
                text = msg.get("content") or msg.get("reasoning_content") or ""
                usage = data.get("usage", {})

                logger.info(
                    "llm_ok: backend=%s model=%s tokens_in=%d tokens_out=%d cost=$0",
                    backend["name"], backend["model"],
                    usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                )

                # Log a MySQL (best-effort, no bloquea la llamada)
                self._log_usage(
                    endpoint="briefing_generate",
                    model=backend["model"],
                    tokens_input=usage.get("prompt_tokens", 0),
                    tokens_output=usage.get("completion_tokens", 0),
                    success=True,
                )

                return {
                    "text": text,
                    "tokens_used": usage.get("total_tokens", 0),
                    "tokens_input": usage.get("prompt_tokens", 0),
                    "tokens_output": usage.get("completion_tokens", 0),
                    "model": backend["model"],
                    "backend": backend["name"],
                    "cost_usd": 0.0,
                }

            except httpx.TimeoutException:
                logger.warning("LLM timeout %s/%s", backend["name"], backend["model"])
                last_error = f"timeout after {TIMEOUT}s"
            except Exception as exc:
                logger.warning("LLM error %s/%s: %s", backend["name"], backend["model"], exc)
                last_error = str(exc)

        raise RuntimeError(f"LLM call failed after trying {len(self._backends)} backends: {last_error}")

    @staticmethod
    def _log_usage(endpoint: str, model: str, tokens_input: int, tokens_output: int, success: bool = True):
        """Inserta registro en app_llm_usage. Intenta MySQL, fallback a DuckDB."""
        # 1. Intentar MySQL (Windows)
        try:
            from motoshop_api.config import settings
            import pymysql
            conn = pymysql.connect(
                host=settings.mysql_host, port=settings.mysql_port,
                user=settings.mysql_user, password=settings.mysql_password,
                database=settings.mysql_database, charset="utf8mb4", connect_timeout=3,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO app_llm_usage
                       (endpoint, model, tokens_input, tokens_output, cost_usd, success)
                       VALUES (%s, %s, %s, %s, 0, %s)""",
                    [endpoint, model, tokens_input, tokens_output, 1 if success else 0],
                )
            conn.commit()
            conn.close()
            return
        except Exception:
            pass

        # 2. Fallback: DuckDB (archivo separado para evitar conflicto read-only)
        try:
            import os, duckdb, traceback
            db_path = os.environ.get("DUCKDB_PATH", "/tmp/motoshop_gold.duckdb")
            cost_path = db_path.replace(".duckdb", "_cost.duckdb")
            con = duckdb.connect(cost_path)
            con.execute("""
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    endpoint VARCHAR,
                    model VARCHAR,
                    tokens_input INTEGER,
                    tokens_output INTEGER,
                    success BOOLEAN DEFAULT TRUE
                )
            """)
            con.execute(
                "INSERT INTO llm_usage (endpoint, model, tokens_input, tokens_output, success) VALUES (?, ?, ?, ?, ?)",
                [endpoint, model, tokens_input, tokens_output, success],
            )
            logger.info("cost_logged: path=%s calls=%d", cost_path,
                        con.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0])
            con.close()
        except Exception as exc:
            logger.warning("cost_log_failed: %s", exc)

    def close(self):
        self._http.close()
