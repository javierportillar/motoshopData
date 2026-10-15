"""Middleware para ETag y conditional requests (304 Not Modified)."""

from __future__ import annotations

import hashlib

from fastapi import Response
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def matches_etag(if_none_match: str, etag: str) -> bool:
    """Evalúa la cabecera If-None-Match según RFC 9110 (comparación débil)."""
    if not if_none_match or not if_none_match.strip():
        return False
    if if_none_match.strip() == "*":
        return True

    def normalize(val: str) -> str:
        val = val.strip()
        if val.startswith("W/"):
            val = val[2:]
        return val.strip('"')

    target = normalize(etag)
    candidates = [normalize(item) for item in if_none_match.split(",")]
    return target in candidates


def merge_vary(existing_vary: str | None, *required_tokens: str) -> str:
    """Combina cabeceras Vary preservando directivas existentes sin duplicados."""
    tokens: list[str] = []
    if existing_vary:
        for part in existing_vary.split(","):
            token = part.strip()
            if token and not any(token.lower() == t.lower() for t in tokens):
                tokens.append(token)
    for req in required_tokens:
        if not any(req.lower() == t.lower() for t in tokens):
            tokens.append(req)
    return ", ".join(tokens)


class ETagMiddleware:
    """Middleware ASGI que genera ETags y gestiona respuestas 304 Not Modified.

    - Para peticiones GET y HEAD que devuelven 200 OK con body:
      - Genera un ETag débil basado en SHA-1 (formato W/"<hash>").
      - Configura cabecera ETag y Cache-Control (preservando directivas del endpoint u
        omitiendo si no se especificó y aplicando 'private, no-cache').
      - Configura Vary combinando directivas existentes con 'Accept-Encoding' y 'X-Tenant'
        para aislamiento de caché multi-tenant en clientes y proxies.
      - Si If-None-Match coincide con el ETag, devuelve 304 Not Modified con cuerpo vacío (0 B),
        preservando cabeceras Cache-Control, Vary, Date, Expires y Content-Location (RFC 9110).
    - Omite respuestas con no-store, respuestas streaming (chunked) y respuestas no-200.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if_none_match = headers.get("if-none-match")

        initial_message: Message | None = None
        is_chunked = False

        async def send_wrapper(message: Message) -> None:
            nonlocal initial_message, is_chunked

            if message["type"] == "http.response.start":
                initial_message = message
                return

            if message["type"] == "http.response.body":
                if is_chunked:
                    await send(message)
                    return

                more_body = message.get("more_body", False)
                if more_body:
                    # Respuesta streaming (chunked): pasar directamente sin almacenar
                    is_chunked = True
                    if initial_message:
                        await send(initial_message)
                        initial_message = None
                    await send(message)
                    return

                status_code = initial_message["status"] if initial_message else None
                body = message.get("body", b"")

                if status_code == 200 and body and initial_message is not None:
                    mut_headers = MutableHeaders(raw=initial_message["headers"])
                    cache_control = mut_headers.get("cache-control", "")

                    if "no-store" not in cache_control.lower():
                        existing_etag = mut_headers.get("etag")
                        etag = existing_etag or f'W/"{hashlib.sha1(body).hexdigest()}"'

                        # RFC 9110 §15.4.5 & Multi-tenant cache separation
                        resolved_cache_control = cache_control or "private, no-cache"
                        resolved_vary = merge_vary(
                            mut_headers.get("vary"),
                            "Accept-Encoding",
                            "X-Tenant",
                        )

                        if if_none_match and matches_etag(if_none_match, etag):
                            resp_headers: dict[str, str] = {
                                "ETag": etag,
                                "Cache-Control": resolved_cache_control,
                                "Vary": resolved_vary,
                            }
                            for hdr in ("date", "expires", "content-location"):
                                if hdr in mut_headers:
                                    resp_headers[hdr] = mut_headers[hdr]

                            response_304 = Response(
                                status_code=304,
                                headers=resp_headers,
                            )
                            await response_304(scope, receive, send)
                            initial_message = None
                            return

                        mut_headers["etag"] = etag
                        if "cache-control" not in mut_headers:
                            mut_headers["cache-control"] = resolved_cache_control
                        mut_headers["vary"] = resolved_vary

                if initial_message:
                    await send(initial_message)
                    initial_message = None
                await send(message)
                return

            # Para otros tipos de mensajes ASGI (ej. http.response.pathsend)
            if initial_message and not is_chunked:
                is_chunked = True
                await send(initial_message)
                initial_message = None
            await send(message)

        await self.app(scope, receive, send_wrapper)
