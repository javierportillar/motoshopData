"""Migration runner + F8 series tests (WF-6s1, WF-6s2 pre-check helper).

Contract: `infra/migrations/run_migrations.py` applies numbered SQL files
exactly once, records state in `app_migration_state`, and re-runs are no-ops.
The duplicate pre-check helper (used by unique-index migrations such as the
future F8-003) must abort BEFORE any DDL when duplicate key pairs exist.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from infra.migrations import run_migrations as runner  # noqa: E402
from infra.migrations.run_migrations import (  # noqa: E402, F401
    DuplicateMigrationNumberError,
    MigrationOutOfOrderError,
    MissingSqlFileError,
    PrecheckFailedError,
)

# ─── statement splitting ───────────────────────────────────────


def test_split_statements_strips_comments_and_blanks():
    sql = "-- c1\nCREATE TABLE a (x INT);-- c2\n\n--only comment;\nINSERT INTO a VALUES (1);\n"
    stmts = runner.split_statements(sql)
    assert stmts == ["CREATE TABLE a (x INT)", "INSERT INTO a VALUES (1)"]


# ─── discovery / ordering validation ───────────────────────────


def test_discover_f8_files_sorted(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text("-- seed\nSELECT 1;\n", encoding="utf-8")
    (d / "F8-002-app_idempotency.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (d / "README.md").write_text("docs", encoding="utf-8")

    files = runner.discover_f8_files(d, prefix="F8")
    assert [f.name for f in files] == [
        "F8-001-app_doc_journal.sql",
        "F8-002-app_idempotency.sql",
    ]


def test_discover_migrations_duplicate_serial_is_error(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (d / "F8-001-app_idempotency.sql").write_text("SELECT 2;\n", encoding="utf-8")
    with pytest.raises(DuplicateMigrationNumberError):
        runner.discover_f8_files(d, prefix="F8")


def test_validate_order_applied_file_missing_is_error(tmp_path):
    (tmp_path / "F8-001-app_doc_journal.sql").write_text("SELECT 1;\n", encoding="utf-8")
    files = runner.discover_f8_files(tmp_path, prefix="F8")
    applied = ["F8-001-app_doc_journal.sql", "F8-002-app_idempotency.sql"]
    with pytest.raises(MissingSqlFileError):
        runner.validate_order(applied, files)


def test_validate_order_out_of_order_pending_is_error(tmp_path):
    (tmp_path / "F8-001-app_doc_journal.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "F8-002-app_idempotency.sql").write_text("SELECT 2;\n", encoding="utf-8")
    files = runner.discover_f8_files(tmp_path, prefix="F8")
    # F8-002 recorded as applied; F8-001 arriving later would reorder history
    applied = ["F8-002-app_idempotency.sql"]
    with pytest.raises(MigrationOutOfOrderError):
        runner.validate_order(applied, files)


def test_validate_order_accepts_pending_continuation(tmp_path):
    (tmp_path / "F8-001-app_doc_journal.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tmp_path / "F8-002-app_idempotency.sql").write_text("SELECT 2;\n", encoding="utf-8")
    (tmp_path / "F8-003-unique_doc_indexes.sql").write_text("SELECT 3;\n", encoding="utf-8")
    files = runner.discover_f8_files(tmp_path, prefix="F8")
    applied = ["F8-001-app_doc_journal.sql", "F8-002-app_idempotency.sql"]
    runner.validate_order(applied, files)  # no raise


# ─── apply exactly once (fake conn recorder) ───────────────────


class _FakeCursor:
    """Records executed statements; emulates app_migration_state reads."""

    def __init__(self):
        self.executed: list[str] = []
        self._state_rows: list[tuple[str, str]] = []

    def execute(self, sql, params=None):
        if params and sql.startswith("INSERT INTO app_migration_state"):
            self._state_rows.append(tuple(params))
        self.executed.append(sql.strip())

    def fetchall(self):
        return list(self._state_rows)

    def close(self):
        pass


def _fake_conn():
    conn = MagicMock()
    conn.cursor.return_value = _FakeCursor()
    return conn


def test_runner_applies_each_pending_file_once_and_records_state(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text(
        "CREATE TABLE IF NOT EXISTS app_doc_journal (id INT);\n", encoding="utf-8"
    )
    (d / "F8-002-app_idempotency.sql").write_text(
        "CREATE TABLE IF NOT EXISTS app_idempotency (id INT);\n", encoding="utf-8"
    )
    files = runner.discover_f8_files(d, prefix="F8")
    conn = _fake_conn()

    migrations = runner.validate_order([], files)
    applied_names = runner.apply_migrations(conn, migrations)
    assert applied_names == [
        "F8-001-app_doc_journal.sql",
        "F8-002-app_idempotency.sql",
    ]
    executed = conn.cursor.return_value.executed
    assert any("app_doc_journal" in s for s in executed)
    assert any("app_idempotency" in s for s in executed)
    # one state row per applied file
    inserts = [s for s in executed if s.startswith("INSERT INTO app_migration_state")]
    assert len(inserts) == 2


def test_second_run_is_noop_with_recorded_state(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text("CREATE TABLE x (id INT);\n", encoding="utf-8")
    files = runner.discover_f8_files(d, prefix="F8")
    conn = _fake_conn()

    runner.apply_migrations(conn, runner.validate_order([], files))
    # simulate second run where state already has the migration
    second = runner.validate_order(["F8-001-app_doc_journal.sql"], files)
    applied = runner.apply_migrations(conn, second)
    assert applied == []  # nothing re-executed


class _StateConn:
    """Fake conn whose `app_migration_state` is preloaded with other series."""

    def __init__(self, state: list[tuple[str, str]]):
        self.state = list(state)
        self.executed: list[str] = []

    def cursor(self):
        return _StateCursor(self)

    def commit(self) -> None:
        pass


class _StateCursor:
    def __init__(self, conn: _StateConn):
        self._conn = conn
        self._rows: list[tuple[str, str]] = []

    def execute(self, sql, params=None):
        sql = sql.strip()
        if params and sql.startswith("INSERT INTO app_migration_state"):
            self._conn.state.append((params[0], params[1]))
            self._conn.executed.append(sql)
            self._rows = []
        elif sql.startswith("SELECT migration_name"):
            self._rows = list(self._conn.state)
        else:
            self._conn.executed.append(sql)
            self._rows = []

    def fetchall(self):
        return list(self._rows)

    def close(self) -> None:
        pass


def test_prefix_run_ignores_state_of_other_series(tmp_path):
    """A `--prefix F9` run must not trip over F8 rows already recorded."""
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text(
        "CREATE TABLE app_doc_journal (id INT);\n", encoding="utf-8"
    )
    (d / "F9-001-app_bank_movements.sql").write_text(
        "CREATE TABLE app_bank_movements (id INT);\n", encoding="utf-8"
    )
    files = runner.discover_f8_files(d, prefix="F9")
    conn = _StateConn([("F8-001-app_doc_journal.sql", "a" * 64)])

    applied = runner.run_against_conn(conn, files, prefix="F9")

    assert applied == ["F9-001-app_bank_movements.sql"]
    assert not any("app_doc_journal" in s for s in conn.executed)


def test_prefix_run_second_time_is_noop_and_keeps_other_series(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-001-app_doc_journal.sql").write_text(
        "CREATE TABLE app_doc_journal (id INT);\n", encoding="utf-8"
    )
    (d / "F9-001-app_bank_movements.sql").write_text(
        "CREATE TABLE app_bank_movements (id INT);\n", encoding="utf-8"
    )
    files = runner.discover_f8_files(d, prefix="F9")
    conn = _StateConn([("F8-001-app_doc_journal.sql", "a" * 64)])

    runner.run_against_conn(conn, files, prefix="F9")
    assert runner.run_against_conn(conn, files, prefix="F9") == []
    assert [name for name, _checksum in conn.state] == [
        "F8-001-app_doc_journal.sql",
        "F9-001-app_bank_movements.sql",
    ]


def test_console_encoding_is_hardened_for_utf8(monkeypatch):
    """cp1252 consoles raised UnicodeEncodeError while printing the failure."""
    calls: list[dict[str, str]] = []

    class _Stream:
        def reconfigure(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(runner.sys, "stdout", _Stream())
    monkeypatch.setattr(runner.sys, "stderr", _Stream())

    runner._harden_console_encoding()

    assert calls == [
        {"encoding": "utf-8", "errors": "replace"},
        {"encoding": "utf-8", "errors": "replace"},
    ]


def test_console_encoding_tolerates_streams_without_reconfigure(monkeypatch):
    monkeypatch.setattr(runner.sys, "stdout", object())
    monkeypatch.setattr(runner.sys, "stderr", object())

    runner._harden_console_encoding()  # no raise


def test_checksum_drift_on_applied_file_is_error(tmp_path):
    name = "F8-001-app_doc_journal.sql"
    (tmp_path / name).write_text("CREATE TABLE x (id INT);\n", encoding="utf-8")
    files = runner.discover_f8_files(tmp_path, prefix="F8")
    # recorded checksum of DIFFERENT content → already-applied file drifted
    applied_checksums = {name: "0" * 64}
    with pytest.raises(runner.ChecksumMismatchError):
        runner.validate_order([name], files, applied_checksums)


# ─── duplicate pre-check helper (WF-6s2 contract, exercised in 3.2) ──


def test_find_duplicate_rows_returns_groups_from_query():
    class _Rows2(_FakeCursor):
        def execute(self, sql, params=None):
            assert "GROUP BY" in sql
            self._rows = [("F001", 5)]

        def fetchall(self):
            return self._rows

    conn = MagicMock()
    conn.cursor.return_value = _Rows2()
    groups = runner.find_duplicate_rows(conn, "facventas", ("pref", "numdoc"))
    assert groups == [("F001", 5)]


def test_precheck_no_duplicates_raises_when_dups_found():
    class _Rows3(_FakeCursor):
        def execute(self, sql, params=None):
            self._rows = [("F001", 5), ("F002", 1)]

        def fetchall(self):
            return self._rows

    conn = MagicMock()
    conn.cursor.return_value = _Rows3()
    with pytest.raises(PrecheckFailedError) as exc:
        runner.precheck_no_duplicates(conn, "facventas", ("pref", "numdoc"))
    assert "facventas" in str(exc.value)
    assert "F001" in str(exc.value)


def test_precheck_no_duplicates_passes_clean_table():
    class _Rows0(_FakeCursor):
        def execute(self, sql, params=None):
            self._rows = []

        def fetchall(self):
            return self._rows

    conn = MagicMock()
    conn.cursor.return_value = _Rows0()
    runner.precheck_no_duplicates(conn, "facventas", ("pref", "numdoc"))  # no raise


# ─── F8 SQL files exist and parse ───────────────────────────────


_REAL_MIGRATIONS_DIR = Path(runner.__file__).resolve().parent


def test_f8_files_present_and_parseable():
    texts = []
    for name in ("F8-001-app_doc_journal.sql", "F8-002-app_idempotency.sql"):
        p = _REAL_MIGRATIONS_DIR / name
        assert p.is_file(), f"{name} missing"
        text = p.read_text(encoding="utf-8")
        texts.append((name, text))
    by_name = dict(texts)
    assert "CREATE TABLE IF NOT EXISTS app_doc_journal" in by_name["F8-001-app_doc_journal.sql"]
    assert "ENGINE=InnoDB" in by_name["F8-001-app_doc_journal.sql"]
    assert "CREATE TABLE IF NOT EXISTS app_idempotency" in by_name["F8-002-app_idempotency.sql"]
    # statements split cleanly
    for _n, text in texts:
        stmts = runner.split_statements(text)
        assert stmts and all(s.strip() for s in stmts)


def test_f9_grant_verifications_query_table_privileges():
    """`SCHEMA_PRIVILEGES` has no TABLE_NAME column: F9-002/F9-004 aborted there."""
    for name, table in (
        ("F9-002-grant_app_writer_bank.sql", "app_bank_movements"),
        ("F9-004-grant_app_writer_bank_jobs.sql", "app_bank_verification_jobs"),
    ):
        text = (_REAL_MIGRATIONS_DIR / name).read_text(encoding="utf-8")
        assert "information_schema.TABLE_PRIVILEGES" in text, name
        assert "TABLE_SCHEMA = DATABASE()" in text, name
        assert f"TABLE_NAME = '{table}'" in text, name
        assert "SCHEMA_PRIVILEGES" not in text, name


def test_f9_files_present_and_parseable():
    """The F9 series ships four files and every one splits into statements."""
    expected = (
        "F9-001-app_bank_movements.sql",
        "F9-002-grant_app_writer_bank.sql",
        "F9-003-app_bank_verification_jobs.sql",
        "F9-004-grant_app_writer_bank_jobs.sql",
    )
    for name in expected:
        path = _REAL_MIGRATIONS_DIR / name
        assert path.is_file(), f"{name} missing"
        stmts = runner.split_statements(path.read_text(encoding="utf-8"))
        assert stmts and all(s.strip() for s in stmts), name


# ─── 3.2: F8-003 unique doc index + pre-check directives (WF-6s2) ──


def test_extract_prechecks_parses_directives():
    sql = (
        "-- precheck: facventas(codclas, prefven, numfven)\n"
        "-- precheck: detfventas(codclas, numfven)\n"
        "ALTER TABLE facventas ADD UNIQUE KEY uq_doc (codclas, prefven, numfven);\n"
    )
    assert runner._extract_prechecks(sql) == [
        ("facventas", ("codclas", "prefven", "numfven")),
        ("detfventas", ("codclas", "numfven")),
    ]


def test_extract_prechecks_ignores_files_without_directives():
    assert runner._extract_prechecks("CREATE TABLE a (x INT);\n") == []


def test_f8_003_file_exists_with_unique_index_and_precheck():
    p = _REAL_MIGRATIONS_DIR / "F8-003-unique_doc_indexes.sql"
    assert p.is_file(), "F8-003-unique_doc_indexes.sql missing (task 3.2)"
    text = p.read_text(encoding="utf-8")
    assert "ALTER TABLE facventas" in text
    assert "UNIQUE" in text.upper()
    assert "prefven" in text and "numfven" in text
    # the dup pre-check MUST be declared for the indexed doc table (WF-6s2)
    assert ("facventas", ("codclas", "prefven", "numfven")) in \
        runner._extract_prechecks(text)


class _DispatchCursor:
    """Fake cursor: GROUP BY probes return scripted rows, DDL is recorded."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        sql = sql.strip()
        if "GROUP BY" in sql and "HAVING" in sql:
            self._conn.rows = self._conn.dup_rows
        else:
            self._conn.executed.append(sql)
            self._conn.rows = []

    def fetchall(self):
        return list(self._conn.rows)

    def close(self):
        pass


class _PrecheckConn:
    def __init__(self, dup_rows):
        self.dup_rows = dup_rows
        self.executed: list[str] = []
        self.rows: list = []
        self.commit_calls = 0

    def cursor(self):
        return _DispatchCursor(self)

    def commit(self):
        self.commit_calls += 1


def test_migration_with_duplicates_aborts_before_ddl(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-003-unique_doc_indexes.sql").write_text(
        "-- precheck: facventas(codclas, prefven, numfven)\n"
        "ALTER TABLE facventas ADD UNIQUE KEY uq_doc (codclas, prefven, numfven);\n",
        encoding="utf-8",
    )
    conn = _PrecheckConn(dup_rows=[("S15", "FVP", 7322, 2)])
    with pytest.raises(PrecheckFailedError) as exc:
        runner.apply_migrations(
            conn, runner.discover_f8_files(d, prefix="F8")
        )
    assert "facventas" in str(exc.value)
    # no DDL ran: only the pre-check probe (the GROUP BY) was executed
    assert all("GROUP BY" in s or "HAVING" in s for s in conn.executed)
    assert not any("ALTER TABLE" in s for s in conn.executed)


def test_clean_migration_runs_ddl_after_precheck(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "F8-003-unique_doc_indexes.sql").write_text(
        "-- precheck: facventas(codclas, prefven, numfven)\n"
        "ALTER TABLE facventas ADD UNIQUE KEY uq_doc (codclas, prefven, numfven);\n",
        encoding="utf-8",
    )
    conn = _PrecheckConn(dup_rows=[])
    applied = runner.apply_migrations(
        conn, runner.discover_f8_files(d, prefix="F8")
    )
    assert applied == ["F8-003-unique_doc_indexes.sql"]
    assert any("ALTER TABLE" in s for s in conn.executed)


def test_f8_003_real_file_dry_precheck_against_fake_clean_conn():
    """The real F8-003 file parses and its precheck directives resolve."""
    path = _REAL_MIGRATIONS_DIR / "F8-003-unique_doc_indexes.sql"
    text = path.read_text(encoding="utf-8")
    stmts = runner.split_statements(text)
    assert stmts, "F8-003 has no executable statements"
    conn = _PrecheckConn(dup_rows=[])
    for table, key_columns in runner._extract_prechecks(text):
        runner.precheck_no_duplicates(conn, table, key_columns)  # no raise
