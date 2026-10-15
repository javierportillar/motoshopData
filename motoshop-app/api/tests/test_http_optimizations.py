"""Pruebas de optimizaciones HTTP: compresión GZip y conditional requests (ETag / 304)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from motoshop_api.main import app
from motoshop_api.middleware.etag import ETagMiddleware


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


class TestGZipCompression:
    """Pruebas para verificar la compresión GZip en respuestas salientes."""

    def test_gzip_compression_on_large_payload(self, client: TestClient) -> None:
        """Petición con Accept-Encoding: gzip a endpoint > 1KB devuelve Content-Encoding: gzip."""
        response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert response.headers.get("content-encoding") == "gzip"
        assert len(response.content) > 0

    def test_gzip_not_applied_on_small_payload(self, client: TestClient) -> None:
        """Respuestas < 1000 bytes (ej. /health) no deben comprimirse para evitar overhead."""
        response = client.get("/health", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert "content-encoding" not in response.headers

    def test_gzip_not_applied_with_identity_encoding(self, client: TestClient) -> None:
        """Con Accept-Encoding: identity, la respuesta no debe contener Content-Encoding: gzip."""
        response = client.get("/openapi.json", headers={"Accept-Encoding": "identity"})
        assert response.status_code == 200
        assert "content-encoding" not in response.headers


class TestETagAndConditionalRequests:
    """Pruebas para generación de ETags, partición Vary y respuestas 304 Not Modified."""

    def test_etag_generated_on_successful_get(self, client: TestClient) -> None:
        """GET exitoso (200 con body) genera ETag, Cache-Control y Vary con partición."""
        response = client.get("/health")
        assert response.status_code == 200
        etag = response.headers.get("etag")
        assert etag is not None
        assert etag.startswith('W/"')
        assert response.headers.get("cache-control") == "private, no-cache"
        vary = response.headers.get("vary", "")
        assert "Accept-Encoding" in vary
        assert "X-Tenant" in vary

    def test_304_not_modified_on_matching_etag(self, client: TestClient) -> None:
        """Enviar If-None-Match correspondiente devuelve 304, 0 B de cuerpo, y preserva headers."""
        response1 = client.get("/health")
        assert response1.status_code == 200
        etag = response1.headers.get("etag")
        assert etag is not None

        response2 = client.get("/health", headers={"If-None-Match": etag})
        assert response2.status_code == 304
        assert len(response2.content) == 0
        assert response2.headers.get("etag") == etag
        assert response2.headers.get("cache-control") == "private, no-cache"
        vary = response2.headers.get("vary", "")
        assert "Accept-Encoding" in vary
        assert "X-Tenant" in vary

    def test_304_not_modified_with_wildcard(self, client: TestClient) -> None:
        """If-None-Match: * devuelve 304 para recursos existentes con body."""
        response = client.get("/health", headers={"If-None-Match": "*"})
        assert response.status_code == 304
        assert len(response.content) == 0

    def test_200_returned_when_etag_does_not_match(self, client: TestClient) -> None:
        """Si el ETag no coincide, debe devolverse 200 con el contenido completo."""
        response = client.get("/health", headers={"If-None-Match": 'W/"non-matching-etag"'})
        assert response.status_code == 200
        assert len(response.content) > 0
        body = response.json()
        assert body["status"] == "ok"

    def test_gzip_and_etag_cooperation(self, client: TestClient) -> None:
        """GZip y ETag colaboran en respuestas grandes (> 1000 bytes) y soportan 304 sin payload."""
        headers = {"Accept-Encoding": "gzip"}
        res1 = client.get("/demo", headers=headers)
        assert res1.status_code == 200
        assert res1.headers.get("content-encoding") == "gzip"
        etag = res1.headers.get("etag")
        assert etag is not None

        res2 = client.get("/demo", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})
        assert res2.status_code == 304
        assert len(res2.content) == 0
        assert res2.headers.get("etag") == etag
        vary = res2.headers.get("vary", "")
        assert "Accept-Encoding" in vary
        assert "X-Tenant" in vary

    def test_304_preserves_custom_origin_cache_control_and_vary(self) -> None:
        """RFC 9110: el 304 preserva Cache-Control custom y fusiona Vary del endpoint origen."""
        custom_app = FastAPI()
        custom_app.add_middleware(ETagMiddleware)

        @custom_app.get("/custom")
        def custom_route() -> Response:
            return Response(
                content='{"custom": true}',
                media_type="application/json",
                headers={
                    "Cache-Control": "public, max-age=300",
                    "Vary": "Authorization",
                },
            )

        c = TestClient(custom_app)
        res1 = c.get("/custom")
        assert res1.status_code == 200
        etag = res1.headers["etag"]
        assert res1.headers["cache-control"] == "public, max-age=300"
        assert "Authorization" in res1.headers["vary"]
        assert "X-Tenant" in res1.headers["vary"]

        res2 = c.get("/custom", headers={"If-None-Match": etag})
        assert res2.status_code == 304
        assert len(res2.content) == 0
        assert res2.headers["cache-control"] == "public, max-age=300"
        vary = res2.headers["vary"]
        assert "Authorization" in vary
        assert "Accept-Encoding" in vary
        assert "X-Tenant" in vary


class TestEdgeCasesAndSafety:
    """Pruebas de tolerancia a fallos, métodos no-GET y respuestas no-200."""

    def test_non_200_response_does_not_generate_etag(self, client: TestClient) -> None:
        """Respuestas con error (ej. 404) no generan ETag ni devuelven 304."""
        response = client.get("/api/non-existent-route-404")
        assert response.status_code == 404
        assert "etag" not in response.headers

    def test_post_request_bypasses_etag(self, client: TestClient) -> None:
        """Peticiones POST no son modificadas por el middleware de ETag."""
        response = client.post("/api/auth/login", json={"username": "bad", "password": "bad"})
        assert "etag" not in response.headers

    def test_head_health_request(self, client: TestClient) -> None:
        """HEAD /health responde 200 correctamente sin errores."""
        response = client.head("/health")
        assert response.status_code == 200
        assert len(response.content) == 0
