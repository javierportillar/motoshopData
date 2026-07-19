"""Contract tests for diagnostic-safe PostgREST failures in app_users."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException

from motoshop_api.users.supabase_repo import _handle


def test_missing_postgrest_table_is_reported_as_service_unavailable() -> None:
    response = httpx.Response(
        404,
        json={
            "code": "PGRST205",
            "message": "Could not find the table 'public.app_users' in the schema cache",
            "details": None,
            "hint": "Perhaps you meant public.other_table",
            "internal_debug": "must not leak",
        },
    )

    with pytest.raises(HTTPException) as error:
        _handle(response, "list")

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "users_upstream_unavailable"
    assert error.value.detail["message"] == "Servicio de usuarios no disponible"
    assert error.value.detail["upstream_status"] == 404
    assert error.value.detail["correlation_id"]
    serialized = str(error.value.detail)
    assert "public.app_users" not in serialized
    assert "public.other_table" not in serialized
    assert "PGRST205" not in serialized


def test_postgrest_conflict_is_categorized_without_leaking_row_details() -> None:
    response = httpx.Response(
        409,
        json={
            "code": "23505",
            "message": "duplicate key value violates unique constraint",
            "details": "Key (username)=(admin) already exists.",
            "hint": None,
        },
    )

    with pytest.raises(HTTPException) as error:
        _handle(response, "create")

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "users_upstream_conflict"
    assert error.value.detail["upstream_status"] == 409
    assert error.value.detail["correlation_id"]
    serialized = str(error.value.detail)
    assert "23505" not in serialized
    assert "admin" not in serialized
    assert "unique constraint" not in serialized
