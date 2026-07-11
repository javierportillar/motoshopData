"""Static guards for critical expiry migration invariants."""

from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "infra/supabase/migrations/20260711_001_masvital_inventory_lots.sql"
)


def test_adjustment_rpc_persists_and_compares_request_fingerprint() -> None:
    """The fingerprint must be read on replay and inserted on writes."""
    sql = MIGRATION.read_text(encoding="utf-8")
    adjustment_sql = sql.split("create or replace function public.app_inventory_lot_adjustment", 1)[
        1
    ]

    # Replay path: the fingerprint is selected into the generic record and compared.
    assert "m.request_fingerprint as request_fingerprint" in adjustment_sql
    assert "v_existing.request_fingerprint <> p_request_fingerprint" in adjustment_sql
    # Write path: the fingerprint column and value are persisted.
    assert "reason, idempotency_key, request_fingerprint, created_by" in adjustment_sql
    assert "p_idempotency_key, p_request_fingerprint, trim(p_created_by)" in adjustment_sql


def test_replay_lookup_never_mixes_a_row_var_with_scalars() -> None:
    """Regression guard for PL/pgSQL 42601.

    A row/record variable cannot share a multi-item INTO list with scalars.
    The original migration selected `l, m.movement_type, m.request_fingerprint`
    into a row-typed `v_existing_lot` plus scalars, which failed at CREATE
    FUNCTION time. Both RPCs must use a single generic `record` variable.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    # The buggy multi-item INTO with a row variable must not come back.
    assert "into v_existing_lot, v_existing_movement_type" not in sql
    assert "v_existing_lot public.app_inventory_lots;" not in sql
    # Both functions read the replayed lot through the generic record helper.
    assert sql.count("into v_existing\n") >= 4
    assert sql.count("v_existing record;") == 2
