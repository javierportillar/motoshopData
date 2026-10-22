"""Numbered hand-run SQL migration runner for `infra/migrations/` (F8 series).

ADR-0008-08: the repo has no Alembic; migrations are numbered SQL files applied
by this runner exactly once, with state recorded in the InnoDB table
`app_migration_state` (created on boot by the runner itself).

Contract:
- Files matching the series prefix (default `F8-`) are discovered, sorted and
  validated against recorded state before anything executes.
- Each pending file runs its statements in order; a state row (name, sha256
  checksum, applied_at) is recorded after success.
- A second run is a no-op: pending = discovered - recorded.
- Errors fail fast BEFORE DDL: duplicate serial numbers, an already-applied
  migration whose SQL file disappeared, a pending file with a number lower
  than the highest applied one, or a checksum drift on an applied file.
- `find_duplicate_rows` / `precheck_no_duplicates` ship here for the
  unique-index migrations (F8-003+) which MUST abort before DDL when existing
  duplicate key pairs are detected (WF-6s2).

Usage (from the repository root, with a privileged MySQL user):

    motoshop-app\\api\\.venv\\Scripts\\python.exe -m infra.migrations.run_migrations

DSN resolution: MYSQL_HOST / MYSQL_PORT / MYSQL_DATABASE / MYSQL_USER /
MYSQL_PASSWORD environment variables (`.env` in the repo root is loaded),
with `--user` / `--password` CLI overrides for hand-runs by the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parent
DEFAULT_PREFIX = "F8"

MIGRATION_STATE_DDL = """
CREATE TABLE IF NOT EXISTS app_migration_state (
  id             INT UNSIGNED   AUTO_INCREMENT PRIMARY KEY,
  migration_name VARCHAR(128)   NOT NULL,
  checksum       VARCHAR(64)    NOT NULL,
  applied_at     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_migration_name (migration_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_unicode_ci
"""

_FILE_RE = re.compile(r"^(?P<prefix>[A-Z]\d+)-(?P<serial>\d+)-(?P<title>.+)\.sql$")


# ─── Errors ────────────────────────────────────────────────────


class MigrationError(Exception):
    """Base class for migration runner failures."""


class DuplicateMigrationNumberError(MigrationError):
    pass


class MigrationOutOfOrderError(MigrationError):
    pass


class MissingSqlFileError(MigrationError):
    pass


class ChecksumMismatchError(MigrationError):
    pass


class PrecheckFailedError(MigrationError):
    """Duplicate key pairs detected; DDL must not run."""


# ─── SQL text handling ─────────────────────────────────────────


def split_statements(sql_text: str) -> list[str]:
    """Split a F-series SQL file into executable statements.

    Full-line `--` comments are removed, statements are chunked on the
    canonical F-series `;` terminator. Inline trailing comments stay inside
    their statement (MySQL treats them as legal inline comments).
    """
    live_lines: list[str] = []
    for raw_line in sql_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        live_lines.append(raw_line)
    joined = "\n".join(live_lines)
    statements = []
    for chunk in joined.split(";"):
        # F-series file convention: comments only appear between statements or
        # glued to a terminator; they are never part of an executable statement.
        chunk = "\n".join(
            line
            for line in chunk.splitlines()
            if not line.strip().startswith("--")
        )
        text = chunk.strip()
        if text:
            statements.append(text)
    return statements


def sha256_file(path: Path) -> str:
    """Checksum of a migration file, normalized for line endings.

    The checksum MUST be stable across platforms: git's ``autocrlf`` turns
    the LF files of the repository into CRLF in a Windows working tree, so
    hashing the raw bytes reports a false "checksum drift" for every
    migration that was applied from an LF checkout. The line endings are
    normalized to LF before hashing, which is also what the ledger rows
    recorded on the first run.
    """
    raw = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


# ─── Discovery / ordering (pure, hermetically testable) ────────


@dataclass(frozen=True)
class MigrationFile:
    name: str
    serial: int
    path: Path


def discover_f8_files(directory: Path, prefix: str = DEFAULT_PREFIX) -> list[MigrationFile]:
    """Discover migration files of `prefix` sorted by serial number."""
    found: dict[int, MigrationFile] = {}
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        match = _FILE_RE.match(path.name)
        if not match or match.group("prefix") != prefix:
            continue
        serial = int(match.group("serial"))
        if serial in found:
            raise DuplicateMigrationNumberError(
                f"Duplicated serial {serial}: {found[serial].name} and {path.name}"
            )
        found[serial] = MigrationFile(name=path.name, serial=serial, path=path)
    return [found[serial] for serial in sorted(found)]


def validate_order(
    applied_names: list[str],
    files: list[MigrationFile],
    applied_checksums: dict[str, str] | None = None,
) -> list[MigrationFile]:
    """Validate pending files against recorded state and return pending list.

    - A recorded applied migration whose SQL file no longer exists is an error.
    - A pending file with a serial lower than the highest applied serial is an
      out-of-order error (the series would reorder executed history).
    - If `applied_checksums` is provided, an existing file whose content changed
      after being applied fails with ChecksumMismatchError.
    """
    artifacts = {f.name: f for f in files}
    for name in applied_names:
        if name not in artifacts:
            raise MissingSqlFileError(
                f"Recorded applied migration has no SQL file: {name}"
            )
    max_applied = -1
    for name in applied_names:
        max_applied = max(max_applied, artifacts[name].serial)
    pending: list[MigrationFile] = []
    for migration in files:
        if migration.name in applied_names:
            if applied_checksums:
                recorded = applied_checksums[migration.name]
                current = sha256_file(migration.path)
                if recorded != current:
                    raise ChecksumMismatchError(
                        f"{migration.name} changed after being applied "
                        f"(state={recorded[:12]}…, file={current[:12]}…)"
                    )
            continue
        if migration.serial < max_applied:
            raise MigrationOutOfOrderError(
                f"{migration.name} (serial {migration.serial}) is out of order: "
                f"highest applied serial is {max_applied}"
            )
        pending.append(migration)
    return pending


# ─── Duplicate pre-check helper (WF-6s2, consumed by F8-003+) ───


def find_duplicate_rows(
    conn: object, table: str, key_columns: tuple[str, ...]
) -> list[tuple]:
    """Return duplicate key groups on `table` for `key_columns`.

    Each item is (key…, duplicate row count). Empty list means clean.
    """
    cursor = conn.cursor()
    try:
        cols = ", ".join(key_columns)
        cursor.execute(
            f"SELECT {cols}, COUNT(*) AS dup_count FROM `{table}` "
            f"GROUP BY {cols} HAVING COUNT(*) > 1"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    return [tuple(row) for row in rows]


def precheck_no_duplicates(conn: object, table: str, key_columns: tuple[str, ...]) -> None:
    """Abort with PrecheckFailedError when duplicate pairs exist (before DDL)."""
    groups = find_duplicate_rows(conn, table, key_columns)
    if groups:
        detail = ", ".join(f"{grp[:-1]} x{grp[-1]}" for grp in groups[:10])
        raise PrecheckFailedError(
            f"precheck failed on {table} ({', '.join(key_columns)}): "
            f"{len(groups)} duplicate groups [{detail}] — DDL aborted"
        )


_PRECHECK_RE = re.compile(
    r"^--\s*precheck:\s*(?P<table>[\w$]+)\((?P<cols>[^)]+)\)\s*$",
    re.IGNORECASE,
)


def _extract_prechecks(sql_text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Parse ``-- precheck: table(col, …)`` directives from a SQL file.

    Unique-index migrations (F8-003+) declare the dup pre-check inline so
    the runner runs it BEFORE that file's DDL (WF-6s2: duplicates abort the
    migration, the index is never created on dirty data).
    """
    found: list[tuple[str, tuple[str, ...]]] = []
    for raw_line in sql_text.splitlines():
        match = _PRECHECK_RE.match(raw_line.strip())
        if not match:
            continue
        cols = tuple(
            col.strip().strip("`")
            for col in match.group("cols").split(",")
            if col.strip()
        )
        found.append((match.group("table").strip("`"), cols))
    return found


# ─── Apply ─────────────────────────────────────────────────────


def _ensure_state_table(conn) -> None:  # type: ignore[valid-type]
    cursor = conn.cursor()
    try:
        cursor.execute(MIGRATION_STATE_DDL)
        conn.commit()
    finally:
        cursor.close()


def _load_state(conn) -> tuple[list[str], dict[str, str]]:  # type: ignore[valid-type]
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT migration_name, checksum FROM app_migration_state "
            "ORDER BY migration_name"
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    names: list[str] = []
    checksums: dict[str, str] = {}
    for name, checksum in rows:
        names.append(name)
        checksums[name] = checksum
    return names, checksums


def _apply_one(conn, migration: MigrationFile) -> None:  # type: ignore[valid-type]
    statements = split_statements(migration.path.read_text(encoding="utf-8"))
    cursor = conn.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        conn.commit()
    finally:
        cursor.close()


def apply_migrations(conn, migrations: list[MigrationFile]) -> list[str]:  # type: ignore[valid-type]
    """Apply pending migrations to `conn`; return the names applied now.

    The caller runs validate_order() first; state rows are inserted after each
    file commits so a crash leaves the applied history consistent (each file is
    a list of autocommitted DDL statements — the journal of record is the state
    table).
    """
    applied_now: list[str] = []
    for migration in migrations:
        sql_text = migration.path.read_text(encoding="utf-8")
        # WF-6s2: declared dup pre-checks run BEFORE any DDL of the file
        for table, key_columns in _extract_prechecks(sql_text):
            precheck_no_duplicates(conn, table, key_columns)
        _apply_one(conn, migration)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO app_migration_state (migration_name, checksum) VALUES (%s, %s)",
                (migration.name, sha256_file(migration.path)),
            )
            conn.commit()
        finally:
            cursor.close()
        applied_now.append(migration.name)
        print(f"  · applied {migration.name}")
    if not applied_now:
        print("  · nothing pending: no-op run")
    return applied_now


def run_against_conn(
    conn,  # type: ignore[valid-type]
    migration_files: list[MigrationFile],
    prefix: str | None = None,
) -> list[str]:
    """Validate and apply one series; other series in the state table are ignored.

    `app_migration_state` is shared by every series (F5, F7, F8, F9…), but
    `discover_f8_files` only sees the series being run. Validating the whole
    recorded history against one series used to raise MissingSqlFileError for
    every previously applied series. Scope the recorded state to the same
    prefix as the discovery (defaults to the series of the files passed in).
    """
    _ensure_state_table(conn)
    applied_names, checksums = _load_state(conn)
    series = prefix or (migration_files[0].name.split("-", 1)[0] if migration_files else "")
    if series:
        applied_names = [n for n in applied_names if n.split("-", 1)[0] == series]
        checksums = {n: c for n, c in checksums.items() if n.split("-", 1)[0] == series}
    pending = validate_order(applied_names, migration_files, checksums)
    return apply_migrations(conn, pending)


def _build_conn_from_env(args: argparse.Namespace):
    host = args.host or os.getenv("MYSQL_HOST", "localhost")
    port = int(args.port or os.getenv("MYSQL_PORT", "3306"))
    database = args.database or os.getenv("MYSQL_DATABASE", "motoshop2024")
    user = args.user or os.getenv("MYSQL_USER", "root")
    password = args.password if args.password is not None else os.getenv("MYSQL_PASSWORD", "")
    if args.password_file:
        password = Path(args.password_file).read_text(encoding="utf-8").strip()
    return pymysql.connect(
        host=host, port=port, user=user, password=password, database=database,
        charset="latin1", connect_timeout=10,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default=str(DEFAULT_MIGRATIONS_DIR))
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument(
        "--password", default=None,
        help="MySQL password (local runs; prefer --password-file)",
    )
    parser.add_argument("--password-file", default=None, help="Read the MySQL password from a file")
    args = parser.parse_args(argv)

    files = discover_f8_files(Path(args.dir), prefix=args.prefix)
    if not files:
        print(f"No {args.prefix} migrations found in {args.dir}")
        return 0

    conn = _build_conn_from_env(args)
    print(
        f"Series {args.prefix}: {len(files)} file(s); "
        f"host={conn.host} db={conn.db} user={conn.user}"
    )
    try:
        try:
            applied = run_against_conn(conn, files, prefix=args.prefix)
        except PrecheckFailedError as exc:
            print(f"[ABORTED before DDL] {exc}")
            return 2
        print(f"Run complete: {len(applied)} applied in this run.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
