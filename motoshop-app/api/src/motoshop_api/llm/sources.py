"""Read-only source adapters with tenant injection and bounded results."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from motoshop_api.auth.tenant_dep import TenantContext
from motoshop_api.llm.catalog import get_query_spec
from motoshop_api.llm.contracts import SourceEvidence, redact_sensitive


class SourceUnavailable(RuntimeError):
    """A source failed without exposing provider or credential details."""

class DuckDBSourceAdapter:
    def __init__(self, context: TenantContext, *, connection: Any | None = None) -> None:
        from motoshop_api.metrics.repo_duckdb import _make_db_path, get_shared_connection
        self.context = context
        self.connection = connection or get_shared_connection(_make_db_path(context.tenant_id))

    def read(self, domain: str, args: dict[str, object]) -> tuple[list[dict[str, Any]], SourceEvidence]:
        if not self.context.allows(domain):
            raise PermissionError("assistant_source_denied")
        spec = get_query_spec(domain)
        cursor: Any = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(spec.sql, spec.bind(self.context.tenant_id, args))
            columns = [item[0] for item in cursor.description]
            rows = [redact_sensitive(dict(zip(columns, row, strict=True)))
                    for row in cursor.fetchmany(spec.max_rows)]
        except Exception as exc:
            raise SourceUnavailable("La fuente de datos no está disponible") from exc
        finally:
            if cursor is not None:
                cursor.close()
        return rows, _evidence("duckdb", domain)
class SupabaseSourceAdapter:
    """Allowlisted read facade for tenant-scoped live domains."""

    _TABLES = {"expenses": "gastos_operativos", "expiry": "app_inventory_lots"}
    _FILTERS = {"mes": re.compile(r"^eq\.\d{4}-\d{2}$"),
                "expires_on": re.compile(r"^(?:eq|lte)\.\d{4}-\d{2}-\d{2}$")}

    def __init__(self, context: TenantContext, *, client: Any) -> None:
        self.context, self.client = context, client

    def read(self, domain: str, filters: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], SourceEvidence]:
        if not self.context.allows(domain) or domain not in self._TABLES:
            raise PermissionError("assistant_source_denied")
        params = {"tenant": f"eq.{self.context.tenant_id}"}
        for key, value in (filters or {}).items():
            if key in self._FILTERS:
                if not self._FILTERS[key].fullmatch(value):
                    raise ValueError("invalid source filter")
                params[key] = value
        try:
            rows = self.client.get(f"/{self._TABLES[domain]}", params=params).json()
            if not isinstance(rows, list):
                raise ValueError("invalid response")
        except Exception as exc:
            raise SourceUnavailable("La fuente de datos no está disponible") from exc
        return redact_sensitive(rows), _evidence("supabase", domain)
def _evidence(kind: str, domain: str) -> SourceEvidence:
    return SourceEvidence(source_id=f"{kind}-{domain}", domain=domain, kind=kind,
                          citation=f"{kind.title()} {domain}", observed_at=datetime.now(UTC).isoformat(),
                          status="used")
