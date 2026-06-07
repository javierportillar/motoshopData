"""LLMClient — wrapper liviano sobre OpenCode Zen (OpenAI-compatible).

Modelo primario: deepseek-v4-flash-free (multi-idioma, $0)
Modelo fallback: qwen3.6-plus-free ($0)
API: https://opencode.ai/zen/v1 (OpenAI-compatible)

Uso:
    client = get_llm_client()
    result = client.complete("Decí hola")
    print(result["text"])  # "¡Hola! ¿En qué puedo ayudarte?"
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────

PRIMARY_MODEL = os.environ.get("LLM_PRIMARY_MODEL", "deepseek-v4-flash-free")
FALLBACK_MODEL = os.environ.get("LLM_FALLBACK_MODEL", "qwen3.6-plus-free")
API_BASE = os.environ.get("LLM_API_BASE", "https://opencode.ai/zen/v1")
API_KEY = os.environ.get("OPENCODE_API_KEY", "")
TIMEOUT = 60

_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


# ── Client ─────────────────────────────────────────────────────────────────


class LLMClient:
    """Cliente HTTP a OpenCode Zen con fallback automático."""

    def __init__(
        self,
        api_base: str = API_BASE,
        api_key: str = API_KEY,
        primary_model: str = PRIMARY_MODEL,
        fallback_model: str = FALLBACK_MODEL,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._primary = primary_model
        self._fallback = fallback_model
        self._http = httpx.Client(timeout=httpx.Timeout(TIMEOUT))

    def complete(self, prompt: str, *, max_tokens: int = 500, system: str = "") -> dict:
        """Chat completion simple. Retorna {text, tokens_used, model, cost_usd}."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return self._call(messages, max_tokens)

    def complete_json(self, prompt: str, *, max_tokens: int = 500, system: str = "") -> dict:
        """Chat completion con response_format JSON. Retorna dict parseado."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system + "\nRespondé ÚNICAMENTE con JSON válido, sin markdown ni comentarios."})
        else:
            messages.append({"role": "system", "content": "Respondé ÚNICAMENTE con JSON válido, sin markdown ni comentarios."})
        messages.append({"role": "user", "content": prompt})

        result = self._call(messages, max_tokens, response_format={"type": "json_object"})
        try:
            result["json"] = json.loads(result["text"])
        except json.JSONDecodeError:
            logger.warning("complete_json: LLM returned non-JSON: %s", result["text"][:200])
            result["json"] = {"error": "non_json_response", "raw": result["text"]}
        return result

    def _call(self, messages: list[dict], max_tokens: int, response_format: dict | None = None) -> dict:
        """Llama al modelo primario, con fallback si falla."""
        models_to_try = [self._primary, self._fallback]
        last_error = None

        for model in models_to_try:
            try:
                body = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                }
                if response_format:
                    body["response_format"] = response_format

                resp = self._http.post(
                    f"{self._api_base}/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code == 401:
                    logger.error("LLM 401 — API key rejected for model=%s", model)
                    last_error = f"401: API key rejected"
                    continue
                if resp.status_code >= 500:
                    logger.warning("LLM %d from %s — trying fallback", resp.status_code, model)
                    last_error = f"{resp.status_code}: {resp.text[:200]}"
                    continue

                resp.raise_for_status()
                data = resp.json()

                choice = data["choices"][0]
                text = choice["message"]["content"]
                usage = data.get("usage", {})
                tokens_input = usage.get("prompt_tokens", 0)
                tokens_output = usage.get("completion_tokens", 0)

                logger.info(
                    "llm_call: model=%s tokens_in=%d tokens_out=%d cost=$0",
                    model, tokens_input, tokens_output,
                )

                return {
                    "text": text,
                    "tokens_used": tokens_input + tokens_output,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "model": model,
                    "cost_usd": 0.0,  # modelos free forever
                }

            except httpx.TimeoutException:
                logger.warning("LLM timeout for model=%s", model)
                last_error = f"timeout after {TIMEOUT}s"
            except Exception as exc:
                logger.warning("LLM error for model=%s: %s", model, exc)
                last_error = str(exc)

        raise RuntimeError(f"LLM call failed after trying {models_to_try}: {last_error}")

    def close(self):
        self._http.close()

    def __del__(self):
        try:
            self._http.close()
        except Exception:
            pass
