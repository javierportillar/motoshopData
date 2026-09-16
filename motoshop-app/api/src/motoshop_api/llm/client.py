"""LLMClient — dual-API wrapper (OpenCode GO + HuggingFace).

GO: https://opencode.ai/zen/go/v1 (primario, qwen3.6-plus, sin reasoning)
HF: https://router.huggingface.co/v1 (fallback, Qwen2.5-72B-Instruct)

Dual-key: OPENCODE_API_KEY (GO) + OPENCODE_API_KEY_FALLBACK (HF).
Si el modelo primario falla, intenta el fallback con su propia API/key.
"""

from __future__ import annotations

import logging
import time

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────────────────

GO_API_BASE = settings.go_api_base
GO_API_KEY = settings.opencode_api_key
GO_MODEL = settings.go_model
GO_MAX_TOKENS = settings.go_max_tokens

ZEN_API_BASE = settings.zen_api_base
ZEN_API_KEY = settings.opencode_api_key_fallback or settings.opencode_api_key
ZEN_MODEL = settings.zen_model
ZEN_MAX_TOKENS = settings.zen_max_tokens

LLM_REQUEST_DEADLINE_SECONDS = 60
TIMEOUT = min(settings.llm_timeout, LLM_REQUEST_DEADLINE_SECONDS)

_client_singleton: LLMClient | None = None


class LLMDependencyError(RuntimeError):
    """Base error for failures returned by configured LLM providers."""


class TransientLLMError(LLMDependencyError):
    """A retryable provider timeout, network error, rate limit, or 5xx response."""


class PermanentLLMError(LLMDependencyError):
    """A non-retryable provider configuration, request, or response failure."""


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
            self._backends.append(
                {
                    "name": "go",
                    "base": GO_API_BASE.rstrip("/"),
                    "key": GO_API_KEY,
                    "model": GO_MODEL,
                    "max_tokens": GO_MAX_TOKENS,
                }
            )
        if ZEN_API_KEY:
            self._backends.append(
                {
                    "name": "zen",
                    "base": ZEN_API_BASE.rstrip("/"),
                    "key": ZEN_API_KEY,
                    "model": ZEN_MODEL,
                    "max_tokens": ZEN_MAX_TOKENS,
                }
            )

        self._http = httpx.Client(timeout=httpx.Timeout(TIMEOUT))
        if not self._backends:
            logger.warning("No API keys configured — LLM calls will fail")

    @property
    def configured_backends(self) -> tuple[str, ...]:
        return tuple(backend["name"] for backend in self._backends)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        system: str = "",
        session_id: str | None = None,
        deadline: float | None = None,
    ) -> dict:
        """Chat completion. Retorna {text, tokens_used, model, cost_usd, backend}."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._call(messages, max_tokens, session_id=session_id, deadline=deadline)

    def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int | None = None,
        session_id: str | None = None,
        deadline: float | None = None,
    ) -> dict:
        """Complete a chat request that may return tool calls."""
        return self._call(messages, max_tokens, tools=tools, session_id=session_id, deadline=deadline)

    def _call(
        self,
        messages: list[dict],
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        session_id: str | None = None,
        deadline: float | None = None,
    ) -> dict:
        if not self._backends:
            raise PermanentLLMError("No LLM providers are configured")

        failures: list[str] = []
        last_cause: Exception | None = None
        saw_transient_failure = False
        now = time.monotonic()
        request_deadline = min(
            deadline if deadline is not None else now + LLM_REQUEST_DEADLINE_SECONDS,
            now + LLM_REQUEST_DEADLINE_SECONDS,
        )

        for backend in self._backends:
            remaining = request_deadline - time.monotonic()
            if remaining <= 0:
                saw_transient_failure = True
                failures.append("deadline_exceeded")
                break
            try:
                mt = max_tokens if max_tokens is not None else backend["max_tokens"]
                body = {
                    "model": backend["model"],
                    "messages": messages,
                    "max_tokens": mt,
                    "temperature": 0.3,
                }
                if tools:
                    body["tools"] = tools
                    body["tool_choice"] = "auto"

                headers = {
                    "Authorization": f"Bearer {backend['key']}",
                    "Content-Type": "application/json",
                }
                if backend["name"] == "go" or "opencode.ai" in backend.get("base", ""):
                    headers["x-opencode-session"] = session_id or "session-motoshop-agent"

                resp = self._http.post(
                    f"{backend['base']}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=min(TIMEOUT, remaining),
                )

                if resp.status_code in (402, 403, 408, 425, 429) or 500 <= resp.status_code <= 599:
                    logger.warning(
                        "LLM transient HTTP %d from %s/%s",
                        resp.status_code,
                        backend["name"],
                        backend["model"],
                    )
                    failures.append(f"{backend['name']}:{resp.status_code}")
                    saw_transient_failure = True
                    continue
                if not 200 <= resp.status_code < 300:
                    logger.warning(
                        "LLM permanent HTTP %d from %s/%s",
                        resp.status_code,
                        backend["name"],
                        backend["model"],
                    )
                    failures.append(f"{backend['name']}:{resp.status_code}")
                    continue

                try:
                    data = resp.json()
                    if not isinstance(data, dict):
                        raise TypeError("response must be a JSON object")
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "LLM malformed response from %s/%s",
                        backend["name"],
                        backend["model"],
                    )
                    failures.append(f"{backend['name']}:malformed_response")
                    last_cause = exc
                    continue

                if "error" in data:
                    logger.warning(
                        "LLM error payload from %s/%s",
                        backend["name"],
                        backend["model"],
                    )
                    failures.append(f"{backend['name']}:error_payload")
                    continue

                try:
                    choice = data["choices"][0]
                    msg = choice["message"]
                    text = msg.get("content") or msg.get("reasoning_content") or ""
                    tool_calls = msg.get("tool_calls", [])
                    usage = data.get("usage", {})
                    if not isinstance(msg, dict) or not isinstance(usage, dict):
                        raise TypeError("invalid completion response shape")
                except (AttributeError, IndexError, KeyError, TypeError) as exc:
                    logger.warning(
                        "LLM malformed completion from %s/%s",
                        backend["name"],
                        backend["model"],
                    )
                    failures.append(f"{backend['name']}:malformed_completion")
                    last_cause = exc
                    continue

                logger.info(
                    "llm_ok: backend=%s model=%s tokens_in=%d tokens_out=%d cost=$0",
                    backend["name"],
                    backend["model"],
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                )

                return {
                    "text": text,
                    "tool_calls": tool_calls,
                    "tokens_used": usage.get("total_tokens", 0),
                    "tokens_input": usage.get("prompt_tokens", 0),
                    "tokens_output": usage.get("completion_tokens", 0),
                    "model": backend["model"],
                    "backend": backend["name"],
                    "cost_usd": 0.0,
                }

            except httpx.TimeoutException as exc:
                logger.warning("LLM timeout %s/%s", backend["name"], backend["model"])
                failures.append(f"{backend['name']}:timeout")
                saw_transient_failure = True
                last_cause = exc
            except (httpx.InvalidURL, httpx.LocalProtocolError, httpx.UnsupportedProtocol) as exc:
                logger.warning(
                    "LLM provider configuration error %s/%s",
                    backend["name"],
                    backend["model"],
                )
                failures.append(f"{backend['name']}:provider_configuration")
                last_cause = exc
            except httpx.TransportError as exc:
                logger.warning("LLM network error %s/%s", backend["name"], backend["model"])
                failures.append(f"{backend['name']}:network_error")
                saw_transient_failure = True
                last_cause = exc
            except Exception as exc:
                logger.warning("LLM invalid response %s/%s", backend["name"], backend["model"])
                failures.append(f"{backend['name']}:invalid_response")
                last_cause = exc

        summary = ", ".join(failures)
        message = f"LLM call failed after trying {len(self._backends)} backends: {summary}"
        if saw_transient_failure:
            raise TransientLLMError(message) from last_cause
        raise PermanentLLMError(message) from last_cause

    def close(self):
        self._http.close()
