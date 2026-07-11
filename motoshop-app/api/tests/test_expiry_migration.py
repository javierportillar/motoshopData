"""Static guards for critical expiry migration invariants."""

from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "infra/supabase/migrations/20260711_001_masvital_inventory_lots.sql"
)


def test_adjustment_rpc_persists_and_compares_request_fingerprint() -> None:
    """The NOT NULL fingerprint must be declared, read on replay, and inserted on writes."""
    sql = MIGRATION.read_text(encoding="utf-8")
    adjustment_sql = sql.split("create or replace function public.app_inventory_lot_adjustment", 1)[
        1
    ]

    assert "v_existing_fingerprint text;" in adjustment_sql
    assert "into v_existing_lot, v_existing_movement_type, v_existing_fingerprint" in adjustment_sql
    assert "v_existing_fingerprint <> p_request_fingerprint" in adjustment_sql
    assert "reason, idempotency_key, request_fingerprint, created_by" in adjustment_sql
    assert "p_idempotency_key, p_request_fingerprint, trim(p_created_by)" in adjustment_sql
