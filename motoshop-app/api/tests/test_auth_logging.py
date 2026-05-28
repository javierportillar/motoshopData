"""Tests de logging: verificación V5 (PII redaction)."""

from __future__ import annotations

import io
import logging

from motoshop_api.logging import redact_pii


def test_password_field_is_redacted() -> None:
    """V5: un campo 'password' en el log debe aparecer como [REDACTED]."""
    event_dict = {
        "event": "login_attempt",
        "username": "admin",
        "password": "supersecret123",
        "ip": "127.0.0.1",
    }
    result = redact_pii(None, None, event_dict)
    assert result["password"] == "[REDACTED]"
    assert result["username"] == "admin"  # no PII


def test_token_field_is_redacted() -> None:
    event_dict = {
        "event": "auth_check",
        "token": "eyJhbGciOiJIUzI1NiJ9...",
        "authorization": "Bearer eyJ...",
    }
    result = redact_pii(None, None, event_dict)
    assert result["token"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"


def test_non_pii_fields_not_redacted() -> None:
    event_dict = {
        "event": "request",
        "method": "GET",
        "path": "/products",
        "status": 200,
    }
    result = redact_pii(None, None, event_dict)
    assert result == event_dict
