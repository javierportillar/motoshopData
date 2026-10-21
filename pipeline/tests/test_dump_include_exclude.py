"""Task 1.7 tests: dump include/exclude policy (spec erp-write-foundation WF-9).

Scenario «ETL stays clean»: once the ERP write-path tables exist, the cloud
dump MUST keep `app_*` internals (journal, idempotency, migration ledger)
out of bronze/gold aggregates while legacy doc tables (facventas,
detcuentas, …) keep flowing with desktop + web postings.

The policy is a PURE function (`resolve_dump_tables`) so tests don't touch
MySQL or Databricks; the CLI (main) only consumes its verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "infra"))

import dump_to_cloud as dumper  # noqa: E402


VALID = {
    "facventas", "detfventas", "detapago", "detcuentas", "terceros",
    "productos", "ubiprodbod", "contadores", "compras", "detcompras",
    "app_doc_journal", "app_idempotency", "app_migration_state",
}


def _resolve(requested):
    return dumper.resolve_dump_tables(requested, VALID)


# ─── app_* internals are invisible to bronze/gold ──────────────


def test_app_internal_tables_are_excluded_from_a_full_dump():
    included, excluded = _resolve(sorted(VALID))
    assert "app_doc_journal" not in included
    assert "app_idempotency" not in included
    assert "app_migration_state" not in included
    excluded_names = {table for table, _reason in excluded}
    assert {
        "app_doc_journal", "app_idempotency", "app_migration_state",
    } == excluded_names
    # the exclusion reason names the policy (audit-friendly)
    for _table, reason in excluded:
        assert "internal" in reason


def test_legacy_doc_tables_always_flow():
    included, excluded = _resolve(
        ["facventas", "detfventas", "detapago", "detcuentas", "detcompras"]
    )
    assert included == ["facventas", "detfventas", "detapago", "detcuentas", "detcompras"]
    assert excluded == []


def test_explicit_request_of_internal_table_is_excluded_not_dumped():
    """A manual operator ran `--tables app_doc_journal`; the policy refuses."""
    included, excluded = _resolve(["app_doc_journal", "facventas"])
    assert included == ["facventas"]
    assert len(excluded) == 1
    assert excluded[0][0] == "app_doc_journal"
    assert "internal" in excluded[0][1]


def test_unknown_table_is_excluded_with_reason_naming_it():
    included, excluded = _resolve(["facventas", "no_existe"])
    assert included == ["facventas"]
    assert len(excluded) == 1
    assert excluded[0][0] == "no_existe"
    assert "not found" in excluded[0][1]


def test_tables_all_uses_mysql_listing_minus_erp_internals():
    class FakeCursor:
        def execute(self, statement, params=None):
            assert "SHOW TABLES" in statement

        def fetchall(self):
            return [("facventas",), ("app_doc_journal",), ("terceros",)]

        def close(self):
            pass

    class FakeConn:
        def cursor(self):
            return FakeCursor()

    listed = dumper.list_all_tables(FakeConn())
    included, _excluded = dumper.resolve_dump_tables(listed, listed)
    assert sorted(included) == ["facventas", "terceros"]


def test_core_listing_has_no_app_internal_tables():
    # the F1 core list predates the ERP change; it must remain clean
    assert not any(table.startswith("app_") for table in dumper.TABLES_CORE)
