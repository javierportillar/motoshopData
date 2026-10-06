from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import uuid4

import duckdb
import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.users import User, _users_cache
from motoshop_api.purchase_assessments.analyzer import (
    analyze_purchase_invoice,
    discover_purchase_invoices,
)
from motoshop_api.purchase_assessments.generator import (
    MAX_LLM_PRODUCTS,
    MAX_OUTPUT_TOKENS,
    _context_metrics,
    generate_assessment_markdown,
)
from motoshop_api.purchase_assessments.repository import (
    FALLBACK_RETRY_COOLDOWN,
    SupabasePurchaseAssessmentRepository,
    get_purchase_assessment_repository,
)
from motoshop_api.purchase_assessments.service import (
    _assessment_row,
    assessment_fingerprint,
    refresh_purchase_assessments,
)
from motoshop_api.purchase_assessments.worker import PeriodicPurchaseAssessmentWorker


@pytest.fixture
def purchase_assessment_db(tmp_path):
    db_path = tmp_path / "purchase-assessment.duckdb"
    connection = duckdb.connect(str(db_path))
    connection.execute(
        "CREATE TABLE silver_fact_compras (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, nit_proveedor VARCHAR, nombre_proveedor VARCHAR, "
        "total_factura DOUBLE, estado_documento VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_compras_detalle (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, cod_producto VARCHAR, nombre_detalle VARCHAR, cantidad DOUBLE, "
        "valor_unitario DOUBLE, total_detalle DOUBLE, costo_producto DOUBLE)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_ventas (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, estado_documento VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE silver_fact_ventas_detalle (num_documento VARCHAR, cod_clase VARCHAR, "
        "business_date DATE, cod_producto VARCHAR, cantidad DOUBLE, total_detalle DOUBLE)"
    )
    connection.execute(
        "CREATE TABLE silver_dim_producto (cod_producto VARCHAR, nombre_producto VARCHAR, "
        "existencia DOUBLE, snapshot_date DATE, presentacion VARCHAR, cod_medida VARCHAR)"
    )
    connection.execute(
        "CREATE TABLE gold_mart_inventario_actual "
        "(cod_producto VARCHAR, cantidad_actual DOUBLE, snapshot_date DATE)"
    )
    connection.execute(
        "CREATE TABLE gold_mart_abc_xyz "
        "(business_month DATE, cod_producto VARCHAR, categoria_abc VARCHAR)"
    )
    connection.execute(
        "INSERT INTO silver_fact_compras VALUES "
        "('P1', 'FC', '2026-09-05', '900', 'Proveedor', 240, 'B'), "
        "('P2', 'FC', '2026-09-12', '900', 'Proveedor', 30, 'B'), "
        "('CANCEL', 'FC', '2026-09-14', '900', 'Proveedor', 200, 'A'), "
        "('DUP', 'FC', '2026-09-10', '900', 'Proveedor', 100, 'B'), "
        "('DUP', 'FC', '2026-09-10', '900', 'Proveedor', 100, 'B')"
    )
    connection.execute(
        "INSERT INTO silver_fact_compras_detalle VALUES "
        "('P1', 'FC', '2026-09-05', 'SKU1', 'Filtro', 20, 10, 200, 8), "
        "('P1', 'FC', '2026-09-06', 'SKU1', 'Wrong date detail', 99, 10, 990, 8), "
        "('P2', 'FC', '2026-09-12', 'SKU1', 'Filtro', 3, 10, 30, 8), "
        "('CANCEL', 'FC', '2026-09-14', 'SKU1', 'Filtro', 20, 10, 200, 8), "
        "('DUP', 'FC', '2026-09-10', 'SKU1', 'Filtro', 10, 10, 100, 8)"
    )
    connection.execute(
        "INSERT INTO silver_fact_ventas VALUES "
        "('V0', 'FV', '2026-08-20', 'B'), ('V1', 'FV', '2026-09-10', 'B'), "
        "('V2', 'FV', '2026-09-14', 'B'), ('VC', 'FV', '2026-09-15', 'A'), "
        "('V3', 'FV', '2026-09-18', 'B')"
    )
    connection.execute(
        "INSERT INTO silver_fact_ventas_detalle VALUES "
        "('V0', 'FV', '2026-08-20', 'SKU1', 18, 360), "
        "('V1', 'FV', '2026-09-10', 'SKU1', 4, 120), "
        "('V2', 'FV', '2026-09-14', 'SKU1', 2, 60), "
        "('VC', 'FV', '2026-09-15', 'SKU1', 90, 9000), "
        "('V3', 'FV', '2026-09-18', 'SKU1', 9, 270)"
    )
    connection.execute(
        "INSERT INTO silver_dim_producto VALUES "
        "('SKU1', 'Filtro', 7, '2026-09-16', 'UND', 'UND')"
    )
    connection.execute(
        "INSERT INTO gold_mart_inventario_actual VALUES ('SKU1', 7, '2026-09-16')"
    )
    connection.close()
    yield db_path


class MemoryAssessmentRepository:
    """Small atomic PostgREST stand-in for service and route tests."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows: dict[tuple[str, str, str, str, str], dict] = {}
        self.scan_cursors: dict[str, tuple[str, str, str] | None] = {}
        self.lock = Lock()
        for row in rows or []:
            stored = {
                "id": str(uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                **row,
            }
            self.rows[self._key(stored)] = stored

    @staticmethod
    def _key(row: dict) -> tuple[str, str, str, str, str]:
        return (
            str(row.get("tenant_id", "")),
            str(row.get("business_date", ""))[:10],
            str(row.get("cod_clase", "")),
            str(row.get("num_documento", "")),
            str(row.get("assessment_fingerprint", "")),
        )

    def get_scan_cursor(self, tenant_id: str):
        with self.lock:
            return self.scan_cursors.get(tenant_id)

    def advance_scan_cursor(self, tenant_id: str, expected, next_cursor) -> bool:
        with self.lock:
            if self.scan_cursors.get(tenant_id) != expected:
                return False
            self.scan_cursors[tenant_id] = next_cursor
            return True

    def reset_scan_cursor(self, tenant_id: str) -> None:
        with self.lock:
            self.scan_cursors[tenant_id] = None

    def insert_pending(self, rows: list[dict]) -> int:
        inserted = 0
        with self.lock:
            for row in rows:
                key = self._key(row)
                if key not in self.rows:
                    self.rows[key] = {
                        **row,
                        "id": str(uuid4()),
                        "created_at": datetime.now(UTC).isoformat(),
                        "updated_at": datetime.now(UTC).isoformat(),
                    }
                    inserted += 1
        return inserted

    def list_claimable(self, tenant_id: str, limit: int) -> list[dict]:
        with self.lock:
            now = datetime.now(UTC)
            priority = {"pending": 0, "failed": 1, "processing": 2}
            return sorted(
                [
                    row for row in self.rows.values()
                    if row.get("tenant_id") == tenant_id
                    and (
                        row.get("status") == "pending"
                        or (
                            row.get("status") == "failed"
                            and (
                                not row.get("next_retry_at")
                                or datetime.fromisoformat(row["next_retry_at"]) <= now
                            )
                        )
                        or (
                            row.get("status") == "processing"
                            and row.get("claimed_at")
                            and datetime.fromisoformat(row["claimed_at"])
                            < now - timedelta(minutes=10)
                        )
                    )
                ],
                key=lambda row: (
                    priority.get(row.get("status", "processing"), 3),
                    row["business_date"],
                    row["created_at"],
                ),
            )[:limit]

    def claim(self, row: dict) -> dict | None:
        with self.lock:
            stored = next((value for value in self.rows.values() if value["id"] == row["id"]), None)
            stale_processing = bool(
                stored
                and stored.get("status") == "processing"
                and stored.get("claimed_at")
                and datetime.fromisoformat(stored["claimed_at"])
                < datetime.now(UTC) - timedelta(minutes=10)
            )
            retry_not_due = bool(
                stored
                and stored.get("status") == "failed"
                and stored.get("next_retry_at")
                and datetime.fromisoformat(stored["next_retry_at"]) > datetime.now(UTC)
            )
            if not stored or (
                retry_not_due
                or (stored["status"] not in {"pending", "failed"} and not stale_processing)
            ):
                return None
            stored["status"] = "processing"
            stored["claim_token"] = str(uuid4())
            stored["attempt_count"] = stored.get("attempt_count", 0) + 1
            stored["claimed_at"] = datetime.now(UTC).isoformat()
            return dict(stored)

    def complete(
        self, tenant_id: str, row_id: str, claim_token: str, result: dict
    ) -> bool:
        with self.lock:
            row = next(
                (
                    value for value in self.rows.values()
                    if value["id"] == row_id and value["tenant_id"] == tenant_id
                ),
                None,
            )
            if not row or row.get("claim_token") != claim_token:
                return False
            row.update(result)
            row["status"] = (
                "fallback"
                if result["generation_mode"] == "deterministic_fallback"
                else "completed"
            )
            row["claim_token"] = None
            row["claimed_at"] = None
            row["completed_at"] = datetime.now(UTC).isoformat()
            row["next_retry_at"] = (
                (datetime.now(UTC) + FALLBACK_RETRY_COOLDOWN).isoformat()
                if row["status"] == "fallback"
                else None
            )
            return True

    def fail(
        self,
        tenant_id: str,
        row_id: str,
        claim_token: str,
        error_code: str,
        attempt_count: int,
    ) -> bool:
        with self.lock:
            row = next(
                (
                    value for value in self.rows.values()
                    if value["id"] == row_id and value["tenant_id"] == tenant_id
                ),
                None,
            )
            if not row or row.get("claim_token") != claim_token:
                return False
            row["status"] = "failed"
            row["last_error_code"] = error_code
            delay_minutes = min(2 ** max(0, attempt_count - 1), 60)
            row["next_retry_at"] = (
                datetime.now(UTC) + timedelta(minutes=delay_minutes)
            ).isoformat()
            row["claim_token"] = None
            return True

    def get_invoice(
        self, tenant_id: str, business_date: str, cod_clase: str,
        num_documento: str, nit_proveedor: str | None = None,
    ) -> dict | None:
        matches = [
            row for row in self.rows.values()
            if row.get("tenant_id") == tenant_id
            and str(row.get("business_date", ""))[:10] == business_date
            and row.get("cod_clase") == cod_clase
            and row.get("num_documento") == num_documento
            and (not nit_proveedor or row.get("nit_proveedor") == nit_proveedor)
        ]
        return max(matches, key=lambda row: row.get("created_at", ""), default=None)

    def get_assessment_by_id(self, tenant_id: str, assessment_id: str) -> dict | None:
        with self.lock:
            return next(
                (
                    dict(row)
                    for row in self.rows.values()
                    if row.get("tenant_id") == tenant_id and row.get("id") == assessment_id
                ),
                None,
            )

    def queue_fallback_retry(self, tenant_id: str, assessment_id: str) -> dict | None:
        with self.lock:
            row = next(
                (
                    value
                    for value in self.rows.values()
                    if value.get("tenant_id") == tenant_id and value.get("id") == assessment_id
                ),
                None,
            )
            if (
                not row
                or row.get("status") != "fallback"
                or row.get("generation_mode") != "deterministic_fallback"
            ):
                return None
            retry_at = row.get("next_retry_at")
            if retry_at and datetime.fromisoformat(retry_at) > datetime.now(UTC):
                return None
            row.update({
                "status": "pending",
                "markdown": None,
                "generation_mode": None,
                "provider": None,
                "model": None,
                "completed_at": None,
                "next_retry_at": None,
                "last_error_code": "manual_retry",
                "claim_token": None,
                "claimed_at": None,
                "updated_at": datetime.now(UTC).isoformat(),
            })
            return dict(row)

    def list_assessments(
        self, tenant_id: str, date_from: str, date_to: str,
        nit_proveedor: str | None, limit: int,
    ) -> list[dict]:
        return sorted(
            [
                row for row in self.rows.values()
                if row.get("tenant_id") == tenant_id
                and date_from <= str(row.get("business_date", ""))[:10] <= date_to
                and (not nit_proveedor or row.get("nit_proveedor") == nit_proveedor)
            ],
            key=lambda row: row["business_date"],
            reverse=True,
        )[:limit]


class CountingLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.session_ids: list[str] = []

    def complete(self, prompt: str, **kwargs) -> dict:
        self.calls += 1
        self.session_ids.append(kwargs["session_id"])
        assert len(prompt) <= 3_250
        assert kwargs["max_tokens"] == MAX_OUTPUT_TOKENS
        assert "no confiables" in kwargs["system"]
        return {
            "text": "# Evaluación\n\nNarrativa de prueba.",
            "backend": "fake",
            "model": "fake-model",
        }


def test_llm_context_limits_product_rows_and_reports_the_omitted_count():
    metrics = {
        "products": [{"cod_producto": f"SKU-{index}"} for index in range(15)],
        "totals": {"productos_distintos": 15},
    }

    context = _context_metrics(metrics)

    assert len(context["products"]) == MAX_LLM_PRODUCTS
    assert context["totals"]["productos_en_contexto_llm"] == MAX_LLM_PRODUCTS
    assert context["totals"]["productos_omitidos_del_contexto_llm"] == 15 - MAX_LLM_PRODUCTS


def test_each_assessment_generation_attempt_uses_a_fresh_provider_session():
    client = CountingLLM()
    metrics = {"invoice": {"cod_clase": "FC", "num_documento": "P1"}, "products": []}

    first = generate_assessment_markdown(metrics, llm_client=client, tenant_id="motoshop")
    second = generate_assessment_markdown(metrics, llm_client=client, tenant_id="motoshop")

    assert first["generation_mode"] == "llm"
    assert second["generation_mode"] == "llm"
    assert len(client.session_ids) == 2
    assert client.session_ids[0] != client.session_ids[1]


class FailingLLM:
    def complete(self, prompt: str, **kwargs) -> dict:
        raise RuntimeError("provider unavailable")


def test_supabase_repository_uses_tenant_filters_and_conditional_atomic_claim():
    class Response:
        status_code = 200

        def __init__(self, body: list[dict]) -> None:
            self.body = body

        def json(self) -> list[dict]:
            return self.body

    class RecordingClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, *, params, json, headers):
            self.calls.append({
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
            })
            body = []
            if method == "PATCH":
                body = [{
                    **json,
                    "id": params["id"].removeprefix("eq."),
                    "deterministic_metrics": {"invoice": {}},
                }]
            return Response(body)

    client = RecordingClient()
    repository = SupabasePurchaseAssessmentRepository(lambda: client)
    claimed = repository.claim({
        "id": "assessment-id",
        "tenant_id": "tenant-a",
        "status": "pending",
        "attempt_count": 0,
    })

    assert client.calls[0]["params"]["tenant_id"] == "eq.tenant-a"
    claim_call = client.calls[-1]
    assert claim_call["method"] == "PATCH"
    assert claim_call["params"] == {
        "id": "eq.assessment-id",
        "status": "eq.pending",
        "tenant_id": "eq.tenant-a",
    }
    assert claim_call["json"]["status"] == "processing"
    assert claim_call["json"]["claim_token"]
    assert claimed is not None
    repository.get_invoice("tenant-a", "2026-09-01", "FC", "D-1,(x)")
    assert client.calls[-1]["params"]["num_documento"] == "eq.D-1,(x)"


def test_scan_cursor_advance_is_compare_and_set():
    class Response:
        status_code = 200

        def __init__(self, body: list[dict]) -> None:
            self.body = body

        def json(self) -> list[dict]:
            return self.body

    class CursorClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, *, params, json, headers):
            self.calls.append({"method": method, "params": params, "json": json})
            if method == "PATCH":
                return Response([json])
            return Response([])

    client = CursorClient()
    repository = SupabasePurchaseAssessmentRepository(lambda: client)
    advanced = repository.advance_scan_cursor(
        "tenant-a",
        None,
        ("2026-09-05", "FC", "P1"),
    )

    patch = client.calls[-1]
    assert advanced is True
    assert patch["params"]["tenant_id"] == "eq.tenant-a"
    assert patch["params"]["cursor_business_date"] == "is.null"
    assert patch["params"]["cursor_cod_clase"] == "is.null"
    assert patch["params"]["cursor_num_documento"] == "is.null"
    assert patch["json"]["cursor_business_date"] == "2026-09-05"
    assert patch["json"]["cursor_num_documento"] == "P1"


def test_supabase_repository_reclaims_expired_processing_lease():
    class Response:
        status_code = 200

        def __init__(self, body: list[dict]) -> None:
            self.body = body

        def json(self) -> list[dict]:
            return self.body

    old_claimed_at = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
    stale_row = {
        "id": "stale-id",
        "tenant_id": "tenant-a",
        "business_date": "2026-09-05",
        "cod_clase": "FC",
        "num_documento": "P1",
        "content_fingerprint": "a" * 64,
        "assessment_fingerprint": "b" * 64,
        "status": "processing",
        "attempt_count": 3,
        "claimed_at": old_claimed_at,
        "claim_token": "old-token",
        "deterministic_metrics": {"invoice": {}},
    }

    class StaleClaimClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, *, params, json, headers):
            self.calls.append({"method": method, "params": params, "json": json})
            if method == "GET" and params.get("status") in {"eq.pending", "eq.failed"}:
                return Response([])
            if method == "GET" and params.get("status") == "eq.processing":
                return Response([stale_row])
            return Response([{**stale_row, **json}])

    client = StaleClaimClient()
    repository = SupabasePurchaseAssessmentRepository(lambda: client)
    due = repository.list_claimable("tenant-a", 1)
    claimed = repository.claim(due[0])

    assert due == [stale_row]
    assert claimed is not None
    assert claimed["attempt_count"] == 4
    assert claimed["claim_token"] != "old-token"
    claim_call = client.calls[-1]
    assert claim_call["params"]["status"] == "eq.processing"
    assert claim_call["params"]["claimed_at"].startswith("lt.")


def test_supabase_repository_requeues_only_same_tenant_deterministic_fallback():
    class Response:
        status_code = 200

        def __init__(self, body: list[dict]) -> None:
            self.body = body

        def json(self) -> list[dict]:
            return self.body

    fallback = {
        "id": "assessment-id",
        "tenant_id": "tenant-a",
        "business_date": "2026-09-05",
        "cod_clase": "FC",
        "num_documento": "P1",
        "content_fingerprint": "a" * 64,
        "assessment_fingerprint": "b" * 64,
        "status": "fallback",
        "generation_mode": "deterministic_fallback",
        "attempt_count": 1,
        "deterministic_metrics": {"invoice": {}},
        "markdown": "# deterministic report",
        "next_retry_at": None,
    }

    class RetryClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, *, params, json, headers):
            self.calls.append({"method": method, "params": params, "json": json})
            if method == "GET":
                return Response([fallback])
            return Response([{**fallback, **json}])

    client = RetryClient()
    repository = SupabasePurchaseAssessmentRepository(lambda: client)
    found = repository.get_assessment_by_id("tenant-a", "assessment-id")
    queued = repository.queue_fallback_retry("tenant-a", "assessment-id")

    assert found == fallback
    assert queued is not None
    assert queued["status"] == "pending"
    assert queued["markdown"] is None
    assert queued["generation_mode"] is None
    assert queued["deterministic_metrics"] == fallback["deterministic_metrics"]
    lookup = client.calls[0]["params"]
    assert lookup == {"id": "eq.assessment-id", "tenant_id": "eq.tenant-a", "limit": "1"}
    patch = client.calls[1]
    assert patch["params"]["tenant_id"] == "eq.tenant-a"
    assert patch["params"]["status"] == "eq.fallback"
    assert patch["params"]["generation_mode"] == "eq.deterministic_fallback"
    assert patch["params"]["or"].startswith("(next_retry_at.is.null,next_retry_at.lte.")
    assert patch["json"]["status"] == "pending"
    assert patch["json"]["last_error_code"] == "manual_retry"


def test_retry_backoff_does_not_block_new_pending_assessments():
    now = datetime.now(UTC)
    failed = {
        "tenant_id": "tenant-a",
        "business_date": "2026-09-01",
        "cod_clase": "FC",
        "num_documento": "OLD-FAILED",
        "assessment_fingerprint": "a" * 64,
        "content_fingerprint": "b" * 64,
        "status": "failed",
        "attempt_count": 10,
        "next_retry_at": (now + timedelta(hours=1)).isoformat(),
        "created_at": (now - timedelta(days=1)).isoformat(),
    }
    pending = {
        "tenant_id": "tenant-a",
        "business_date": "2026-09-20",
        "cod_clase": "FC",
        "num_documento": "NEW-PENDING",
        "assessment_fingerprint": "c" * 64,
        "content_fingerprint": "d" * 64,
        "status": "pending",
        "attempt_count": 0,
        "created_at": now.isoformat(),
    }
    repository = MemoryAssessmentRepository([failed, pending])

    due = repository.list_claimable("tenant-a", 1)

    assert [row["num_documento"] for row in due] == ["NEW-PENDING"]


def test_supabase_failed_claim_obeys_retry_time_and_uses_exponential_backoff():
    class Response:
        status_code = 200

        def __init__(self, body: list[dict]) -> None:
            self.body = body

        def json(self) -> list[dict]:
            return self.body

    due_retry_at = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    due_failed = {
        "id": "failed-id",
        "tenant_id": "tenant-a",
        "business_date": "2026-09-05",
        "cod_clase": "FC",
        "num_documento": "P1",
        "content_fingerprint": "a" * 64,
        "assessment_fingerprint": "b" * 64,
        "status": "failed",
        "attempt_count": 3,
        "next_retry_at": due_retry_at,
        "deterministic_metrics": {"invoice": {}},
    }

    class RetryClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method, url, *, params, json, headers):
            self.calls.append({"method": method, "params": params, "json": json})
            if method == "GET" and params.get("status") == "eq.pending":
                return Response([])
            if method == "GET" and params.get("status") == "eq.failed":
                return Response([due_failed])
            if method == "PATCH":
                return Response([{**due_failed, **json}])
            return Response([])

    client = RetryClient()
    repository = SupabasePurchaseAssessmentRepository(lambda: client)
    due = repository.list_claimable("tenant-a", 1)
    assert due == [due_failed]
    failed_query = client.calls[1]["params"]
    assert failed_query["or"].startswith("(next_retry_at.is.null,next_retry_at.lte.")

    claimed = repository.claim(due[0])
    assert claimed is not None
    claim_params = client.calls[-1]["params"]
    assert claim_params["next_retry_at"] == f"eq.{due_retry_at}"

    before = datetime.now(UTC)
    repository.fail("tenant-a", "failed-id", "claim-token", "ProviderError", 4)
    retry_at = datetime.fromisoformat(client.calls[-1]["json"]["next_retry_at"])
    assert before + timedelta(minutes=7) < retry_at <= before + timedelta(minutes=8, seconds=1)


def test_analyzer_excludes_canceled_and_duplicate_docs_and_uses_full_identity(
    purchase_assessment_db,
):
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    invoices = discover_purchase_invoices(connection)
    assert [(row.num_documento, row.cod_clase) for row in invoices] == [
        ("P1", "FC"), ("P2", "FC")
    ]

    metrics = analyze_purchase_invoice(connection, invoices[0])
    product = metrics["products"][0]
    assert metrics["totals"]["lineas_factura"] == 1
    assert metrics["totals"]["total_lineas_cop"] == 200
    assert metrics["totals"]["diferencia_factura_menos_lineas_cop"] == 40
    assert product["ventas_previas_180d_unidades"] == 18
    assert product["inventory_controlled"] is True
    assert product["control_evidence"] == "inventory_snapshot"
    assert product["stock_previo_estimado"] is None
    assert product["stock_reconstruido_negativo"] is True
    assert product["senal_deterministica"] == "insufficient_evidence"
    assert metrics["assessment_summary"]["senal_global"] == "evidencia_insuficiente"
    assert product["ventas_posteriores_hasta_corte_unidades"] == 15
    assert product["abc_etiqueta"] == "sin clasificación"
    assert product["margen_bruto_referencia_pct"] == pytest.approx(73.3, abs=0.1)
    assert "no demuestran" in " ".join(metrics["evidence_notes"])
    connection.close()


def test_invoice_discovery_applies_keyset_page_before_joining_details(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    first_page = discover_purchase_invoices(connection, limit=1)
    second_page = discover_purchase_invoices(
        connection,
        limit=1,
        after=first_page[-1].identity,
    )

    assert [invoice.num_documento for invoice in first_page] == ["P1"]
    assert [invoice.num_documento for invoice in second_page] == ["P2"]
    assert len(first_page[0].lines) == 1
    connection.close()


def test_unknown_snapshot_stock_is_insufficient_evidence_not_service(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db))
    connection.execute("DELETE FROM gold_mart_inventario_actual")
    invoice = discover_purchase_invoices(connection, limit=1)[0]
    product = analyze_purchase_invoice(connection, invoice)["products"][0]

    assert product["inventory_controlled"] is False
    assert product["control_evidence"] == "insufficient_evidence"
    assert product["senal_deterministica"] == "insufficient_evidence"
    assert product["cantidad_referencia_objetivo"] is None
    connection.close()


def test_abc_uses_latest_month_not_after_invoice(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db))
    connection.execute(
        "INSERT INTO gold_mart_abc_xyz VALUES "
        "('2026-08-01', 'SKU1', 'A'), ('2026-09-01', 'SKU1', 'B'), "
        "('2026-10-01', 'SKU1', 'A')"
    )
    connection.close()
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    invoice = discover_purchase_invoices(connection)[0]
    product = analyze_purchase_invoice(connection, invoice)["products"][0]
    assert product["abc_categoria"] == "B"
    assert product["abc_mes_clasificacion"] == "2026-09"
    connection.close()


def test_margin_uses_invoice_unit_price_when_product_cost_is_missing(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db))
    connection.execute(
        "UPDATE silver_fact_compras_detalle SET costo_producto = NULL "
        "WHERE num_documento = 'P1'"
    )
    invoice = discover_purchase_invoices(connection)[0]
    product = analyze_purchase_invoice(connection, invoice)["products"][0]

    assert product["costo_producto_unitario_promedio_cop"] is None
    assert product["fuente_costo_margen"] == "valor_unitario_factura"
    assert product["margen_bruto_referencia_pct"] == pytest.approx(66.7, abs=0.1)
    connection.close()


def test_assessment_fingerprint_ignores_cutoff_only_changes(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    invoice = discover_purchase_invoices(connection, limit=1)[0]
    metrics = analyze_purchase_invoice(connection, invoice)
    connection.close()
    changed_cutoff = {
        **metrics,
        "source_cutoffs": {**metrics["source_cutoffs"], "sales": "2026-09-20"},
    }

    assert assessment_fingerprint(invoice, changed_cutoff) == assessment_fingerprint(
        invoice, metrics
    )


def test_cutoff_only_change_does_not_repeat_llm_generation(purchase_assessment_db):
    repository = MemoryAssessmentRepository()
    llm = CountingLLM()
    refresh_purchase_assessments(
        "motoshop", purchase_assessment_db, repository=repository, llm_client=llm
    )
    connection = duckdb.connect(str(purchase_assessment_db))
    connection.execute(
        "INSERT INTO silver_fact_ventas VALUES ('V4', 'FV', '2026-09-20', 'B')"
    )
    connection.execute(
        "INSERT INTO silver_fact_ventas_detalle VALUES "
        "('V4', 'FV', '2026-09-20', 'UNRELATED', 1, 10)"
    )
    connection.close()

    result = refresh_purchase_assessments(
        "motoshop", purchase_assessment_db, repository=repository, llm_client=llm
    )

    assert result["discovered"] == 0
    assert result["generated"] == 0
    assert len(repository.rows) == 2
    assert llm.calls == 2


def test_invoice_content_stays_same_but_changed_sales_and_stock_create_revision(
    purchase_assessment_db,
):
    repository = MemoryAssessmentRepository()
    llm = CountingLLM()
    refresh_purchase_assessments(
        "motoshop", purchase_assessment_db, repository=repository, llm_client=llm
    )
    old_p1 = next(
        row for row in repository.rows.values() if row["num_documento"] == "P1"
    )

    connection = duckdb.connect(str(purchase_assessment_db))
    connection.execute(
        "UPDATE silver_fact_ventas_detalle SET cantidad = 3, total_detalle = 90 "
        "WHERE num_documento = 'V2' AND cod_producto = 'SKU1'"
    )
    connection.execute(
        "UPDATE gold_mart_inventario_actual SET cantidad_actual = 8 "
        "WHERE cod_producto = 'SKU1'"
    )
    connection.close()
    result = refresh_purchase_assessments(
        "motoshop", purchase_assessment_db, repository=repository, llm_client=llm
    )

    p1_revisions = [
        row for row in repository.rows.values() if row["num_documento"] == "P1"
    ]
    latest_p1 = max(p1_revisions, key=lambda row: row["created_at"])
    assert result["discovered"] == 2
    assert len(p1_revisions) == 2
    assert latest_p1["content_fingerprint"] == old_p1["content_fingerprint"]
    assert latest_p1["assessment_fingerprint"] != old_p1["assessment_fingerprint"]
    assert llm.calls == 4


def test_periodic_sweep_advances_past_first_invoice_page_without_refresh(
    purchase_assessment_db,
    monkeypatch,
):
    import motoshop_api.purchase_assessments.service as service_module

    monkeypatch.setattr(service_module, "DISCOVERY_PAGE_SIZE", 1)
    repository = MemoryAssessmentRepository()
    llm = CountingLLM()
    first = refresh_purchase_assessments(
        "motoshop", purchase_assessment_db, repository=repository, llm_client=llm
    )
    sweeper = PeriodicPurchaseAssessmentWorker(
        tenants_provider=lambda: {"motoshop": object()},
        db_path_for_tenant=lambda _tenant: purchase_assessment_db,
        repository=repository,
        llm_client=llm,
    )
    sweeper.run_once()

    assert first["discovered"] == 1
    assert {row["num_documento"] for row in repository.rows.values()} == {"P1", "P2"}
    assert llm.calls == 2


@pytest.mark.parametrize("environment,expected_bootstraps", [("prod", 1), ("test", 0)])
def test_tenant_snapshot_path_bootstraps_r2_outside_tests(
    tmp_path,
    monkeypatch,
    environment,
    expected_bootstraps,
):
    import motoshop_api.metrics.repo_duckdb as metrics_module
    import motoshop_api.purchase_assessments.worker as worker_module
    from motoshop_api.config import settings

    db_path = tmp_path / "motoshop_gold.duckdb"
    bootstrap_calls = []
    monkeypatch.setattr(settings, "env", environment)
    monkeypatch.setattr(settings, "duckdb_path", "")
    monkeypatch.setattr(metrics_module, "_make_db_path", lambda _tenant: db_path)
    monkeypatch.setattr(
        metrics_module,
        "_bootstrap_duckdb_from_r2",
        lambda path, tenant: bootstrap_calls.append((path, tenant)),
    )

    assert worker_module._tenant_snapshot_path("motoshop") == db_path
    assert len(bootstrap_calls) == expected_bootstraps
    if expected_bootstraps:
        assert bootstrap_calls == [(db_path, "motoshop")]


@pytest.mark.parametrize("initial_status", ["pending", "processing"])
def test_periodic_worker_recovers_durable_jobs_without_refresh_or_snapshot(
    purchase_assessment_db,
    tmp_path,
    initial_status,
):
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    invoice = discover_purchase_invoices(connection, limit=1)[0]
    metrics = analyze_purchase_invoice(connection, invoice)
    connection.close()
    stable_fingerprint = assessment_fingerprint(invoice, metrics)
    pending = _assessment_row("motoshop", invoice, metrics, stable_fingerprint)
    if initial_status == "processing":
        pending.update({
            "status": "processing",
            "attempt_count": 1,
            "claimed_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
            "claim_token": "expired-claim",
        })
    repository = MemoryAssessmentRepository([pending])
    llm = CountingLLM()
    missing_snapshot = tmp_path / "not-published.duckdb"
    worker = PeriodicPurchaseAssessmentWorker(
        tenants_provider=lambda: {"motoshop": object()},
        db_path_for_tenant=lambda _tenant: missing_snapshot,
        repository=repository,
        llm_client=llm,
    )

    worker.run_once()

    stored = next(iter(repository.rows.values()))
    expected_attempts = 2 if initial_status == "processing" else 1
    assert stored["status"] == "completed"
    assert stored["attempt_count"] == expected_attempts
    assert llm.calls == 1


def test_duplicate_refresh_is_idempotent_and_does_not_repeat_llm_work(purchase_assessment_db):
    db_path = purchase_assessment_db
    repository = MemoryAssessmentRepository()
    llm = CountingLLM()

    first = refresh_purchase_assessments(
        "motoshop", db_path, repository=repository, llm_client=llm
    )
    second = refresh_purchase_assessments(
        "motoshop", db_path, repository=repository, llm_client=llm
    )

    assert first == {"discovered": 2, "generated": 2, "failed": 0}
    assert second == {"discovered": 0, "generated": 0, "failed": 0}
    assert len(repository.rows) == 2
    assert llm.calls == 2
    assert {row["status"] for row in repository.rows.values()} == {"completed"}


def test_overlapping_refresh_workers_only_claim_each_invoice_once(purchase_assessment_db):
    repository = MemoryAssessmentRepository()
    llm = CountingLLM()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(
            lambda _: refresh_purchase_assessments(
                "motoshop",
                purchase_assessment_db,
                repository=repository,
                llm_client=llm,
            ),
            range(2),
        ))

    assert len(repository.rows) == 2
    assert llm.calls == 2
    assert {row["status"] for row in repository.rows.values()} == {"completed"}
    assert sum(result["generated"] for result in results) == 2


def test_llm_provider_failure_persists_marked_deterministic_fallback(purchase_assessment_db):
    db_path = purchase_assessment_db
    repository = MemoryAssessmentRepository()

    result = refresh_purchase_assessments(
        "motoshop", db_path, repository=repository, llm_client=FailingLLM()
    )

    assert result["generated"] == 2
    assert {row["status"] for row in repository.rows.values()} == {"fallback"}
    assert all("Respaldo determinístico" in row["markdown"] for row in repository.rows.values())
    assert all(
        row["generation_mode"] == "deterministic_fallback"
        for row in repository.rows.values()
    )


def test_authenticated_invoice_lookup_is_tenant_scoped(purchase_assessment_db):
    connection = duckdb.connect(str(purchase_assessment_db), read_only=True)
    metrics = analyze_purchase_invoice(connection, discover_purchase_invoices(connection)[0])
    connection.close()
    now = datetime.now(UTC).isoformat()
    shared = {
        "business_date": "2026-09-05",
        "cod_clase": "FC",
        "num_documento": "P1",
        "nit_proveedor": "900",
        "content_fingerprint": "a" * 64,
        "assessment_fingerprint": "b" * 64,
        "status": "fallback",
        "attempt_count": 1,
        "deterministic_metrics": metrics,
        "source_cutoffs": metrics["source_cutoffs"],
        "generation_mode": "deterministic_fallback",
        "provider": "fake",
        "model": "fake-model",
        "analyzer_revision": "purchase-invoice-v1",
        "prompt_revision": "purchase-assessment-spanish-v1",
        "markdown": "# tenant document",
        "created_at": now,
        "updated_at": now,
        "completed_at": now,
    }
    own_id = str(uuid4())
    other_tenant_id = str(uuid4())
    completed_id = str(uuid4())
    cooldown_id = str(uuid4())
    repository = MemoryAssessmentRepository([
        {**shared, "id": own_id, "tenant_id": "motoshop"},
        {
            **shared,
            "id": other_tenant_id,
            "tenant_id": "masvital",
            "markdown": "# private other tenant",
        },
        {
            **shared,
            "id": completed_id,
            "tenant_id": "motoshop",
            "business_date": "2026-09-06",
            "num_documento": "P2",
            "status": "completed",
            "generation_mode": "llm",
        },
        {
            **shared,
            "id": cooldown_id,
            "tenant_id": "motoshop",
            "business_date": "2026-09-07",
            "num_documento": "P3",
            "next_retry_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        },
    ])
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.main import app

    app.dependency_overrides[get_purchase_assessment_repository] = lambda: repository
    _users_cache.clear()
    _users_cache["assessment-admin"] = User(
        username="assessment-admin",
        hashed_password=hash_password("assessment123"),
        email="assessment@example.com",
        role="admin",
        tenants_allowed=["motoshop"],
        source="supabase",
    )
    try:
        client = TestClient(app, raise_server_exceptions=False)
        login = client.post(
            "/api/auth/login",
            json={"username": "assessment-admin", "password": "assessment123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        own = client.get(
            "/api/purchase-assessments/invoice",
            params={"business_date": "2026-09-05", "cod_clase": "FC", "num_documento": "P1"},
            headers=headers,
        )
        assert own.status_code == 200
        assert own.json()["markdown"] == "# tenant document"
        listing = client.get(
            "/api/purchase-assessments",
            params={
                "date_from": "2026-09-01",
                "date_to": "2026-09-30",
                "nit_proveedor": "900",
                "limit": 1,
            },
            headers=headers,
        )
        assert listing.status_code == 200
        assert len(listing.json()["items"]) == 1
        assert listing.json()["items"][0]["markdown"] == "# tenant document"
        retry_url = f"/api/purchase-assessments/{own_id}/retry"
        queued = client.post(retry_url, headers=headers)
        assert queued.status_code == 202
        assert queued.json()["status"] == "pending"
        assert queued.json()["markdown"] is None
        assert queued.json()["generation_mode"] is None
        assert queued.json()["deterministic_metrics"] == metrics

        replay = client.post(retry_url, headers=headers)
        assert replay.status_code == 202
        assert replay.json()["id"] == own_id
        assert replay.json()["attempt_count"] == 1

        completed_retry = client.post(
            f"/api/purchase-assessments/{completed_id}/retry", headers=headers
        )
        assert completed_retry.status_code == 409
        cooldown = client.post(
            f"/api/purchase-assessments/{cooldown_id}/retry", headers=headers
        )
        assert cooldown.status_code == 429
        assert int(cooldown.headers["Retry-After"]) > 0

        cross_tenant_retry = client.post(
            f"/api/purchase-assessments/{other_tenant_id}/retry",
            headers={**headers, "X-Tenant": "masvital"},
        )
        assert cross_tenant_retry.status_code == 403
        assert client.get(
            "/api/purchase-assessments/invoice",
            params={"business_date": "2026-09-05", "cod_clase": "FC", "num_documento": "P1"},
            headers={**headers, "X-Tenant": "masvital"},
        ).status_code == 403
    finally:
        app.dependency_overrides.pop(get_purchase_assessment_repository, None)
        _users_cache.clear()


def test_successful_data_refresh_schedules_background_processing(monkeypatch, tmp_path):
    import motoshop_api.metrics.repo_duckdb as duckdb_repo
    from motoshop_api.admin import router as admin_module
    from motoshop_api.auth.hash import hash_password
    from motoshop_api.main import app

    snapshot = tmp_path / "tenant-snapshot.duckdb"
    snapshot.write_bytes(b"valid test snapshot placeholder")
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.example.test")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setattr(admin_module, "_get_duckdb_path", lambda tenant: snapshot)
    refresh_result = {"success": True}
    monkeypatch.setattr(
        duckdb_repo,
        "_bootstrap_duckdb_from_r2",
        lambda *args, **kwargs: refresh_result["success"],
    )
    monkeypatch.setattr(admin_module, "_clear_metrics_cache", lambda: None)
    monkeypatch.setattr(admin_module, "close_all_shared_connections", lambda: None)
    monkeypatch.setattr(
        admin_module,
        "_run_purchase_assessment_refresh",
        lambda tenant, path: scheduled.append((tenant, path)),
    )
    _users_cache.clear()
    _users_cache["refresh-admin"] = User(
        username="refresh-admin",
        hashed_password=hash_password("refresh123"),
        email="refresh@example.com",
        role="admin",
    )
    try:
        client = TestClient(app, raise_server_exceptions=False)
        login = client.post(
            "/api/auth/login", json={"username": "refresh-admin", "password": "refresh123"}
        )
        response = client.post(
            "/api/admin/data/refresh",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert response.status_code == 200
        assert scheduled == [("motoshop", str(snapshot))]
        refresh_result["success"] = False
        failed_refresh = client.post(
            "/api/admin/data/refresh",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )
        assert failed_refresh.status_code == 503
        assert scheduled == [("motoshop", str(snapshot))]
    finally:
        _users_cache.clear()
