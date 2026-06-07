"""LLMClient — wrapper liviano sobre OpenCode Zen (OpenAI-compatible).

Modelo: deepseek-v4-flash-free (multi-idioma, $0 free forever)
API: https://opencode.ai/zen/v1 (OpenAI-compatible)

Soporta dual key: OPENCODE_API_KEY (primario, GO) + OPENCODE_API_KEY_FALLBACK (Zen).
Si el primario falla (401/rate-limit), reintenta con la key fallback mismo modelo.

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
API_BASE = os.environ.get("LLM_API_BASE", "https://opencode.ai/zen/v1")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))

# Dual key: GO key primario, Zen key secundario (redundancia)
API_KEY_PRIMARY = os.environ.get("OPENCODE_API_KEY", "")
API_KEY_FALLBACK = os.environ.get("OPENCODE_API_KEY_FALLBACK", "")

_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


# ── Client ─────────────────────────────────────────────────────────────────


class LLMClient:
    """Cliente HTTP a OpenCode Zen con fallback de API key."""

    def __init__(
        self,
        api_base: str = API_BASE,
        primary_key: str = API_KEY_PRIMARY,
        fallback_key: str = API_KEY_FALLBACK,
        model: str = PRIMARY_MODEL,
    ):
        self._api_base = api_base.rstrip("/")
        self._keys = [k for k in (primary_key, fallback_key) if k]  # quitar vacías
        self._model = model
        self._http = httpx.Client(timeout=httpx.Timeout(TIMEOUT))
        if not self._keys:
            logger.warning("No API keys configured — LLM calls will fail")

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
        """Llama al modelo, probando cada API key configurada."""
        last_error = None

        for key_idx, api_key in enumerate(self._keys):
            try:
                body = {
                    "model": self._model,
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
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

                if resp.status_code == 401:
                    logger.warning("LLM 401 key_idx=%d — trying next key", key_idx)
                    last_error = "401: API key rejected"
                    continue
                if resp.status_code >= 500:
                    logger.warning("LLM %d from key_idx=%d — trying next key", resp.status_code, key_idx)
                    last_error = f"{resp.status_code}: {resp.text[:200]}"
                    continue

                resp.raise_for_status()
                data = resp.json()

                if "error" in data:
                    err = data["error"]
                    err_msg = err.get("message", str(err))
                    logger.warning("LLM API error key_idx=%d: %s", key_idx, err_msg)
                    last_error = err_msg
                    continue

                choice = data["choices"][0]
                msg = choice["message"]
                # DeepSeek-R1 models ponen la respuesta en reasoning_content y
                # content queda vacío. Usamos content si existe, sino reasoning.
                text = msg.get("content") or msg.get("reasoning_content") or ""
                usage = data.get("usage", {})
                tokens_input = usage.get("prompt_tokens", 0)
                tokens_output = usage.get("completion_tokens", 0)

                logger.info(
                    "llm_call: model=%s key_idx=%d tokens_in=%d tokens_out=%d cost=$0",
                    self._model, key_idx, tokens_input, tokens_output,
                )

                return {
                    "text": text,
                    "tokens_used": tokens_input + tokens_output,
                    "tokens_input": tokens_input,
                    "tokens_output": tokens_output,
                    "model": self._model,
                    "cost_usd": 0.0,
                }

            except httpx.TimeoutException:
                logger.warning("LLM timeout key_idx=%d", key_idx)
                last_error = f"timeout after {TIMEOUT}s"
            except Exception as exc:
                logger.warning("LLM error key_idx=%d: %s", key_idx, exc)
                last_error = str(exc)

        raise RuntimeError(f"LLM call failed after trying {len(self._keys)} keys: {last_error}")

    def close(self):
        self._http.close()

    def __del__(self):
        try:
            self._http.close()
        except Exception:
            pass
