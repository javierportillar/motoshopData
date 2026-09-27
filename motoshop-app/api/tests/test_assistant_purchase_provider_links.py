from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.tenant_dep import TenantContext, get_tenant, get_tenant_context
from motoshop_api.auth.users import User
from motoshop_api.llm.conversations.repository import InMemoryConversationRepository
from motoshop_api.llm.registry import resolve_entity_ref, resolve_supplier_refs
from motoshop_api.main import app
from motoshop_api.metrics.router import get_purchase_profile_repo


@dataclass
class TenantDatabases:
    paths: dict[str, Path]
    connections: dict[str, duckdb.DuckDBPyConnection]

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()
        self.connections.clear()


@pytest.fixture
def tenant_databases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TenantDatabases:
    paths = {tenant: tmp_path / f"{tenant}.duckdb" for tenant in ("motoshop", "masvital")}
    for tenant, path in paths.items():
        with duckdb.connect(str(path)) as connection:
            connection.execute(
                """
                CREATE TABLE silver_fact_compras (
                    business_date DATE, num_documento VARCHAR, cod_clase VARCHAR,
                    nit_proveedor VARCHAR, nombre_proveedor VARCHAR, total_factura DOUBLE,
                    estado_documento VARCHAR
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE silver_fact_compras_detalle (
                    cod_producto VARCHAR, business_date DATE, cantidad DOUBLE,
                    costo_producto DOUBLE, total_detalle DOUBLE, num_documento VARCHAR,
                    cod_clase VARCHAR, nombre_detalle VARCHAR, valor_unitario DOUBLE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE silver_fact_ventas (
                    business_date DATE, num_documento VARCHAR, cod_clase VARCHAR,
                    estado_documento VARCHAR
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE silver_fact_ventas_detalle (
                    cod_producto VARCHAR, business_date DATE, cantidad DOUBLE,
                    total_detalle DOUBLE, costo_producto DOUBLE, num_documento VARCHAR,
                    cod_clase VARCHAR
                )
                """
            )
            if tenant == "motoshop":
                connection.executemany(
                    "INSERT INTO silver_fact_compras VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("2026-01-02", "55", "FC", "900111111-1", "Shared Supplier", 100, "B"),
                        ("2026-01-02", "55", "NC", "900222222-2", "Shared Supplier", 75, "B"),
                        ("2026-01-03", "55", "NC", "900111111-1", "Shared Supplier", 200, "B"),
                        ("2026-01-04", "77", "FC", "900111111-1", "Shared Supplier", 50, "B"),
                        ("2026-01-05", "100", "FC", "900111111-1", "Shared Supplier", 0, "B"),
                        ("2026-02-01", "55", "FC", "900222222-2", "Shared Supplier", 400, "B"),
                        ("2026-02-02", "88", "FC", "900111111-1", "Shared Supplier", 500, "A"),
                        ("2026-02-03", "99", "FC", "900222222-2", "Shared Supplier", 300, "B"),
                        ("2026-02-04", "89", "FC", "900333333-3", "Canceled Supplier", 600, "A"),
                        ("2026-05-01", "A/55", "FC/WEB", "900222222-2", "Shared Supplier", 10, "B"),
                    ],
                )
                connection.executemany(
                    "INSERT INTO silver_fact_compras_detalle VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("SKU-1", "2026-01-02", 2, 10, 80, "55", "FC", "Alpha part", 40),
                        ("SKU-1", "2026-01-03", 1, 10, 40, "55", "NC", "Alpha part", 40),
                        ("SKU-3", "2026-01-04", 5, 20, 150, "77", "FC", "Gamma part", 30),
                        ("SKU-4", "2026-01-05", 1, 0, 0, "100", "FC", "Delta part", 0),
                        ("SKU-2", "2026-02-01", 2, 50, 200, "55", "FC", "Beta part", 100),
                        ("SKU-1", "2026-02-02", 20, 999, 1000, "88", "FC", "Alpha part", 50),
                        ("SKU-2", "2026-02-03", 1, 50, 100, "99", "FC", "Beta part", 100),
                    ],
                )
                connection.executemany(
                    "INSERT INTO silver_fact_ventas VALUES (?, ?, ?, ?)",
                    [
                        ("2026-03-01", "V-1", "FV", "B"),
                        ("2026-03-01", "V-2", "FV", "B"),
                        ("2026-03-02", "V-CANCEL", "FV", "A"),
                        ("2026-03-03", "V-3", "FV", "B"),
                    ],
                )
                connection.executemany(
                    "INSERT INTO silver_fact_ventas_detalle VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        ("SKU-1", "2026-03-01", 2, 100, 10, "V-1", "FV"),
                        ("SKU-2", "2026-03-01", 2, 200, 50, "V-2", "FV"),
                        ("SKU-1", "2026-03-02", 20, 5000, 0, "V-CANCEL", "FV"),
                        ("SKU-4", "2026-03-03", 1, 50, 0, "V-3", "FV"),
                    ],
                )
            else:
                connection.execute(
                    "INSERT INTO silver_fact_compras VALUES "
                    "('2026-01-05', '55', 'FC', '800111111-1', 'Other tenant supplier', 10, 'B')"
                )
                connection.execute(
                    "INSERT INTO silver_fact_compras_detalle VALUES "
                    "('OTHER-SKU', '2026-01-05', 1, 1, 1, '55', 'FC', 'Other item', 1)"
                )

    connections: dict[str, duckdb.DuckDBPyConnection] = {}

    def shared_connection(path: str | Path):
        key = str(path)
        if key not in connections:
            connections[key] = duckdb.connect(key, read_only=True)
        return connections[key]

    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb._make_db_path",
        lambda tenant: paths[tenant],
    )
    monkeypatch.setattr(
        "motoshop_api.metrics.repo_duckdb.get_shared_connection", shared_connection
    )
    result = TenantDatabases(paths, connections)
    yield result
    result.close()


def _context(tenant: str = "motoshop", *domains: str) -> TenantContext:
    return TenantContext(tenant, "ana", "vendedor", True, frozenset(domains or ("purchases",)))


def test_only_known_structured_purchase_tool_results_create_reference_candidates() -> None:
    from motoshop_api.llm.qa_chat import _persisted_entity_candidates, _tool_entity_candidates

    structured = {
        "compras": [
            {
                "fecha": "2026-01-02",
                "cod_clase": "FC",
                "num_documento": "55",
                "nit_proveedor": "900111111-1",
                "proveedor": "Shared Supplier",
                "total_factura": 55,
            }
        ]
    }

    candidates = _tool_entity_candidates("get_compras_recientes", structured)

    assert {(item["entity_type"], item["entity_id"]) for item in candidates} == {
        ("purchase_document", "2026-01-02|FC|55"),
        ("supplier", "900111111-1"),
    }
    assert _tool_entity_candidates("get_kpis_today", structured) == []
    assert _tool_entity_candidates("get_detalle_compra", {"compra": {"num_documento": "55"}}) == []
    assert _persisted_entity_candidates({
        "entity_refs": [{"entity_type": "purchase_document", "entity_id": "2026-01-02|FC|55"}],
        "tools_used": ["get_kpis_today"],
    }) == []


def test_purchase_tools_preserve_document_class_and_exact_detail_identity(
    tenant_databases: TenantDatabases,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm import tools as tools_module
    from motoshop_api.llm.tools import ToolExecutor

    connection = duckdb.connect(str(tenant_databases.paths["motoshop"]), read_only=True)
    monkeypatch.setattr(tools_module, "get_shared_connection", lambda _path: connection)
    executor = ToolExecutor(
        duckdb_path=str(tenant_databases.paths["motoshop"]), tenant="motoshop"
    )

    latest = executor.get_ultima_compra()
    recent = executor.get_compras_recientes()
    by_supplier = executor.buscar_compras_por_proveedor("Shared Supplier")
    detail = executor.get_detalle_compra("55", fecha="2026-01-02", cod_clase="FC")

    assert latest["cod_clase"] == "FC/WEB"
    assert all("cod_clase" in item for item in recent["compras"])
    assert all("cod_clase" in item for item in by_supplier["compras"])
    assert detail["compra"]["cod_clase"] == "FC"
    assert detail["compra"]["fecha"] == "2026-01-02"
    ambiguous = executor.get_detalle_compra("55")
    assert ambiguous["ambiguo"] is True
    assert "Indicá la fecha y el código de clase" in ambiguous["error"]
    connection.close()


def test_purchase_reference_requires_explicit_document_mention_and_rejects_amounts(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.qa_chat import (
        _entity_candidates_mentioned_in_text,
        _tool_entity_candidates,
    )

    candidates = _tool_entity_candidates(
        "get_ultima_compra",
        {
            "fecha": "2026-01-04",
            "cod_clase": "FC",
            "num_documento": "77",
            "nit_proveedor": "900111111-1",
            "proveedor": "Shared Supplier",
            "total_factura": 77,
        },
    )
    purchase = next(item for item in candidates if item["entity_type"] == "purchase_document")

    assert _entity_candidates_mentioned_in_text("Total: $77 COP", [purchase], _context()) == []
    assert _entity_candidates_mentioned_in_text(
        "La factura sumó $77 COP.", [purchase], _context()
    ) == []
    assert _entity_candidates_mentioned_in_text(
        "La factura 77 fue recibida.", [purchase], _context()
    ) == [purchase]


def test_exact_purchase_resolution_preserves_date_class_and_encodes_route(
    tenant_databases: TenantDatabases,
) -> None:
    ref = resolve_entity_ref(
        _context(),
        entity_type="purchase_document",
        entity_id="2026-01-02|FC|55",
        label="untrusted label",
        domain="purchases",
        route_key="purchase_document",
    )

    assert ref.entity_id == "2026-01-02|FC|55"
    assert ref.href == "/dashboards/compras/dia/2026-01-02/documento/55?cod_clase=FC"
    duplicate_number = resolve_entity_ref(
        _context(),
        entity_type="purchase_document",
        entity_id="2026-01-03|NC|55",
        label="55",
        domain="purchases",
        route_key="purchase_document",
    )
    assert duplicate_number.href.endswith("/documento/55?cod_clase=NC")
    same_date_different_class = resolve_entity_ref(
        _context(),
        entity_type="purchase_document",
        entity_id="2026-01-02|NC|55",
        label="55",
        domain="purchases",
        route_key="purchase_document",
    )
    assert same_date_different_class.href.endswith("/documento/55?cod_clase=NC")
    encoded = resolve_entity_ref(
        _context(),
        entity_type="purchase_document",
        entity_id="2026-05-01|FC/WEB|A/55",
        label="A/55",
        domain="purchases",
        route_key="purchase_document",
    )
    assert encoded.href == (
        "/dashboards/compras/dia/2026-05-01/documento/A%2F55?cod_clase=FC%2FWEB"
    )


def test_duplicate_exact_purchase_identity_is_ambiguous(
    tenant_databases: TenantDatabases,
) -> None:
    with duckdb.connect(str(tenant_databases.paths["motoshop"])) as connection:
        connection.execute(
            "INSERT INTO silver_fact_compras VALUES "
            "('2026-01-02', '55', 'FC', '900111111-1', 'Shared Supplier', 100, 'B')"
        )

    with pytest.raises(LookupError):
        resolve_entity_ref(
            _context(),
            entity_type="purchase_document",
            entity_id="2026-01-02|FC|55",
            label="55",
            domain="purchases",
            route_key="purchase_document",
        )


def test_reused_purchase_number_requires_visible_date_and_class(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.registry import purchase_document_ref_mentioned

    context = _context()
    entity_id = "2026-01-02|FC|55"

    assert not purchase_document_ref_mentioned(context, "La factura 55 suma $100.", entity_id)
    assert purchase_document_ref_mentioned(
        context, "La factura 55 clase FC del 2026-01-02 suma $100.", entity_id
    )


@pytest.mark.parametrize(
    "entity_id",
    ["2026-02-02|FC|88", "2026-01-01|FC|55", "2026-01-02|FC|missing"],
)
def test_canceled_or_missing_purchase_documents_do_not_resolve(
    tenant_databases: TenantDatabases, entity_id: str
) -> None:
    with pytest.raises(LookupError):
        resolve_entity_ref(
            _context(),
            entity_type="purchase_document",
            entity_id=entity_id,
            label="55",
            domain="purchases",
            route_key="purchase_document",
        )


def test_purchase_reference_rejects_malformed_identity_and_denied_access(
    tenant_databases: TenantDatabases,
) -> None:
    with pytest.raises(ValueError, match="invalid_entity_reference"):
        resolve_entity_ref(
            _context(),
            entity_type="purchase_document",
            entity_id="55",
            label="55",
            domain="purchases",
            route_key="purchase_document",
        )


def test_history_purchase_backfill_requires_structured_source_and_exact_visible_identity(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.registry import resolve_purchase_refs_in_messages

    context = _context("motoshop", "purchases")
    rows = resolve_purchase_refs_in_messages(
        context,
        [
            "La última compra fue el 2 de enero de 2026. Documento: 55. Clase: FC. "
            "Proveedor: Shared Supplier (NIT 900111111-1).",
            "Documento: 55. Proveedor: NIT 900111111-1.",
            "Documento: $77 COP; NIT 999999999-9.",
        ],
    )

    assert {(ref.entity_type, ref.entity_id) for ref in rows[0]} == {
        ("purchase_document", "2026-01-02|FC|55"),
        ("supplier", "900111111-1"),
    }
    # The reused number is ambiguous without visible date/class; the NIT is still tenant-verified.
    assert [(ref.entity_type, ref.entity_id) for ref in rows[1]] == [
        ("supplier", "900111111-1")
    ]
    assert 2 not in rows


def test_history_purchase_backfill_does_not_link_hidden_markdown_destination(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.registry import resolve_purchase_refs_in_messages

    rows = resolve_purchase_refs_in_messages(
        _context("motoshop", "purchases"),
        ["Total $77 [documento](/dashboards/compras/dia/2026-01-04/documento/77?cod_clase=FC)"],
    )

    assert rows == {}
    with pytest.raises(PermissionError, match="entity_destination_denied"):
        resolve_entity_ref(
            _context("motoshop", "sales"),
            entity_type="purchase_document",
            entity_id="2026-01-02|FC|55",
            label="55",
            domain="purchases",
            route_key="purchase_document",
        )


def test_supplier_names_are_canonical_and_shared_names_are_not_linkable(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.qa_chat import (
        _entity_candidates_mentioned_in_text,
        _entity_references,
        _tool_entity_candidates,
    )
    from motoshop_api.llm.registry import supplier_ref_mentioned

    context = _context()
    refs = resolve_supplier_refs(context, ["900111111-1", "900222222-2"])
    by_nit = {ref.entity_id: ref for ref in refs}

    assert by_nit["900111111-1"].label == "Shared Supplier"
    assert by_nit["900111111-1"].label_is_unique is False
    assert not supplier_ref_mentioned("Shared Supplier", by_nit["900111111-1"])
    assert supplier_ref_mentioned("NIT 900111111-1", by_nit["900111111-1"])
    assert by_nit["900111111-1"].href == "/dashboards/compras/proveedores/900111111-1"

    candidates = _tool_entity_candidates(
        "get_ultima_compra",
        {
            "fecha": "2026-01-02",
            "cod_clase": "FC",
            "num_documento": "55",
            "nit_proveedor": "900111111-1",
            "proveedor": "Shared Supplier",
        },
    )
    supplier_candidate = next(item for item in candidates if item["entity_type"] == "supplier")
    name_match = _entity_candidates_mentioned_in_text(
        "Proveedor Shared Supplier", [supplier_candidate], context
    )
    assert _entity_references(
        name_match,
        "motoshop",
        "ana",
        context,
        visible_text="Proveedor Shared Supplier",
    ) == []
    nit_match = _entity_candidates_mentioned_in_text(
        "Proveedor NIT 900111111-1", [supplier_candidate], context
    )
    resolved = _entity_references(
        nit_match,
        "motoshop",
        "ana",
        context,
        visible_text="Proveedor NIT 900111111-1",
    )
    assert resolved[0]["entity_id"] == "900111111-1"


def test_purchase_resolution_is_tenant_scoped_and_permission_checked(
    tenant_databases: TenantDatabases,
) -> None:
    with pytest.raises(LookupError):
        resolve_entity_ref(
            _context("masvital"),
            entity_type="purchase_document",
            entity_id="2026-01-02|FC|55",
            label="55",
            domain="purchases",
            route_key="purchase_document",
        )
    with pytest.raises(LookupError):
        resolve_entity_ref(
            _context("motoshop"),
            entity_type="supplier",
            entity_id="800111111-1",
            label="Other tenant supplier",
            domain="purchases",
            route_key="supplier",
        )
    with pytest.raises(PermissionError):
        resolve_entity_ref(
            _context("motoshop", "sales"),
            entity_type="supplier",
            entity_id="900111111-1",
            label="Shared Supplier",
            domain="purchases",
            route_key="supplier",
        )


def test_persisted_retry_revalidates_purchase_reference_and_current_access(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat

    context = _context()
    ref = resolve_entity_ref(
        context,
        entity_type="purchase_document",
        entity_id="2026-01-04|FC|77",
        label="77",
        domain="purchases",
        route_key="purchase_document",
    )
    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "ana")
    repository.append_turn(
        "motoshop",
        "ana",
        conversation["id"],
        "Show invoice",
        "La factura 77 fue recibida; la factura 88 fue anulada.",
        request_id="retry-1",
        tools_used=["get_detalle_compra"],
        entity_refs=[
            {**ref.model_dump(), "href": "/forged"},
            {
                "entity_type": "purchase_document",
                "entity_id": "2026-02-02|FC|88",
                "label": "88",
                "domain": "purchases",
                "href": "/forged-canceled",
            },
        ],
    )
    chat = QAChat(
        llm_client=None,
        conversation_mgr=ConversationManager(),
        tool_executor=None,
        tool_defs=[],
        tenant_id="motoshop",
        user_id="ana",
        repository=repository,
        tenant_context=context,
    )

    replay = chat.chat("Show invoice", request_id="retry-1")

    assert replay["entity_refs"][0]["href"].endswith("/documento/77?cod_clase=FC")
    assert len(replay["entity_refs"]) == 1
    chat.tenant_context = _context("motoshop", "sales")
    denied_replay = chat.chat("Show invoice", request_id="retry-1")
    assert denied_replay["entity_refs"] == []


@pytest.fixture
def supplier_profile_client(monkeypatch: pytest.MonkeyPatch):
    class ProfileRepo:
        def __init__(self) -> None:
            self.arguments: tuple | None = None
            self.result: dict | None = {
                "proveedor": {"nit": "900111111-1", "nombre": "Shared Supplier"},
                "periodo": {"fecha_inicio": "2025-09-27", "fecha_fin": "2026-09-27"},
                "compras": {
                    "total_compras": 0,
                    "num_documentos": 0,
                    "productos_top": [],
                },
                "ventas_estimadas": {
                    "metodo_atribucion": {"id": "latest_supplier_per_sku", "descripcion": "test"}
                },
                "documentos": [],
                "paginacion": {
                    "page": 1,
                    "page_size": 20,
                    "total_documentos": 0,
                    "has_more": False,
                },
            }

        def get_compras_proveedor_perfil(
            self, nit, fecha_inicio, fecha_fin, *, page, page_size
        ):
            self.arguments = (nit, fecha_inicio, fecha_fin, page, page_size)
            return self.result

    repo = ProfileRepo()
    authorized_user = User(
        username="managed",
        hashed_password="unused",
        email="managed@test.invalid",
        role="vendedor",
        tenants_allowed=["motoshop"],
        allowed_modules=["ventas-summary"],
        source="supabase",
    )
    overrides = {
        get_current_user: lambda: authorized_user,
        get_tenant: lambda: "motoshop",
        get_purchase_profile_repo: lambda: repo,
    }
    app.dependency_overrides.update(overrides)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, repo, authorized_user
    for dependency in overrides:
        app.dependency_overrides.pop(dependency, None)


def test_supplier_profile_endpoint_auth_default_range_and_pagination(
    supplier_profile_client,
) -> None:
    client, repo, _user = supplier_profile_client

    response = client.get(
        "/api/metrics/compras-proveedor-perfil?nit_proveedor=900111111-1&page=2&page_size=25"
    )

    assert response.status_code == 200
    end = date.today()
    from motoshop_api.metrics.router import _subtract_years

    assert repo.arguments == (
        "900111111-1",
        _subtract_years(end, 1).isoformat(),
        end.isoformat(),
        2,
        25,
    )
    assert (
        response.json()["ventas_estimadas"]["metodo_atribucion"]["id"]
        == "latest_supplier_per_sku"
    )


@pytest.mark.parametrize(
    "query",
    [
        "nit_proveedor=!!",
        "nit_proveedor=900111111-1&fecha_inicio=no-date",
        "nit_proveedor=900111111-1&fecha_inicio=2026-02-01&fecha_fin=2026-01-01",
        "nit_proveedor=900111111-1&fecha_inicio=2015-01-01&fecha_fin=2026-01-01",
        "nit_proveedor=900111111-1&page=0",
        "nit_proveedor=900111111-1&page=10001",
        "nit_proveedor=900111111-1&page_size=101",
    ],
)
def test_supplier_profile_rejects_invalid_nit_dates_and_pagination(
    supplier_profile_client, query: str
) -> None:
    client, _repo, _user = supplier_profile_client

    assert client.get(f"/api/metrics/compras-proveedor-perfil?{query}").status_code == 422


def test_supplier_profile_returns_not_found_and_requires_purchase_access(
    supplier_profile_client,
) -> None:
    client, repo, user = supplier_profile_client
    repo.result = None
    assert client.get(
        "/api/metrics/compras-proveedor-perfil?nit_proveedor=900111111-1"
    ).status_code == 404

    restricted = user.model_copy(update={"allowed_modules": ["analisis"]})
    app.dependency_overrides[get_current_user] = lambda: restricted
    assert client.get(
        "/api/metrics/compras-proveedor-perfil?nit_proveedor=900111111-1"
    ).status_code == 403


def test_supplier_profile_requires_authentication(client: TestClient) -> None:
    assert client.get(
        "/api/metrics/compras-proveedor-perfil?nit_proveedor=900111111-1"
    ).status_code == 401


def test_supplier_profile_endpoint_has_rate_limit(supplier_profile_client) -> None:
    from motoshop_api.metrics.router import limiter

    client, _repo, _user = supplier_profile_client
    storage = limiter._storage
    if hasattr(storage, "storage") and isinstance(storage.storage, dict):
        storage.storage.clear()

    responses = [
        client.get("/api/metrics/compras-proveedor-perfil?nit_proveedor=900111111-1")
        for _ in range(31)
    ]

    assert responses[-1].status_code == 429


def test_supplier_profile_actual_aggregates_pagination_and_estimated_methodology(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

    repo = DuckDBMetricsRepo(db_path=tenant_databases.paths["motoshop"], tenant="motoshop")
    first = repo.get_compras_proveedor_perfil(
        "900111111-1", "2026-01-01", "2026-04-01", page=1, page_size=2
    )
    assert first is not None
    assert first["compras"]["total_compras"] == 350
    assert first["compras"]["num_documentos"] == 4
    assert first["compras"]["ticket_promedio"] == pytest.approx(87.5)
    assert first["compras"]["skus_distintos"] == 3
    assert first["compras"]["productos_top"][0] == {
        "cod_producto": "SKU-3",
        "nombre": "Gamma part",
        "unidades": 5.0,
        "total_compras": 150.0,
        "documentos": 1,
    }
    assert first["compras"]["productos_top"][0]["cod_producto"] == "SKU-3"
    assert len(first["documentos"]) == 2
    assert first["paginacion"] == {
        "page": 1,
        "page_size": 2,
        "total_documentos": 4,
        "has_more": True,
    }
    assert first["documentos"][0]["business_date"] == "2026-01-05"
    assert first["documentos"][0]["cod_clase"] == "FC"
    assert first["documentos"][0]["num_documento"] == "100"

    second = repo.get_compras_proveedor_perfil(
        "900111111-1", "2026-01-01", "2026-04-01", page=2, page_size=2
    )
    assert second is not None
    assert len(second["documentos"]) == 2
    assert second["paginacion"]["has_more"] is False

    estimated = first["ventas_estimadas"]
    assert estimated["revenue"] == 150
    assert estimated["revenue_with_cost"] == 100
    assert estimated["margen_cobertura_pct"] == pytest.approx(66.67)
    assert estimated["margen"] == 80
    assert estimated["margen_pct"] == 80
    assert estimated["skus_vendidos"] == 2
    assert estimated["skus_con_costo"] == 1
    assert estimated["metodo_atribucion"]["id"] == "latest_supplier_per_sku"
    assert "compra válida más reciente" in estimated["metodo_atribucion"]["descripcion"]
    assert "no representa ventas facturadas directamente" in estimated["metodo_atribucion"]["descripcion"]


def test_supplier_profile_empty_range_and_supplier_missing_from_tenant(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.metrics.repo_duckdb import DuckDBMetricsRepo

    repo = DuckDBMetricsRepo(db_path=tenant_databases.paths["motoshop"], tenant="motoshop")
    empty = repo.get_compras_proveedor_perfil(
        "900111111-1", "2030-01-01", "2030-12-31", page=1, page_size=20
    )

    assert empty is not None
    assert empty["compras"]["total_compras"] == 0
    assert empty["compras"]["num_documentos"] == 0
    assert empty["documentos"] == []
    assert empty["ventas_estimadas"]["revenue"] == 0
    canceled_only = repo.get_compras_proveedor_perfil(
        "900333333-3", "2026-01-01", "2026-04-01"
    )
    assert canceled_only is not None
    assert canceled_only["compras"]["num_documentos"] == 0
    assert canceled_only["documentos"] == []
    unknown_cost = repo.get_compras_proveedor_perfil(
        "900111111-1", "2026-03-03", "2026-03-03"
    )
    assert unknown_cost is not None
    assert unknown_cost["ventas_estimadas"]["revenue"] == 50
    assert unknown_cost["ventas_estimadas"]["revenue_with_cost"] == 0
    assert unknown_cost["ventas_estimadas"]["margen"] is None
    assert unknown_cost["ventas_estimadas"]["margen_pct"] is None
    assert unknown_cost["ventas_estimadas"]["skus_vendidos"] == 1
    assert unknown_cost["ventas_estimadas"]["skus_con_costo"] == 0
    assert unknown_cost["ventas_estimadas"]["margen_cobertura_pct"] == 0
    assert repo.get_compras_proveedor_perfil(
        "999999999-9", "2026-01-01", "2026-04-01"
    ) is None


def test_history_revalidates_stored_purchase_reference_without_mutating_text(
    tenant_databases: TenantDatabases,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm.conversations import repository as repository_module

    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "managed")
    repository.append_turn(
        "motoshop",
        "managed",
        conversation["id"],
        "Show the invoice",
        "La factura 77 fue recibida; la factura 88 fue anulada.",
        tools_used=["get_detalle_compra"],
        entity_refs=[
            {
                "entity_type": "purchase_document",
                "entity_id": "2026-01-04|FC|77",
                "label": "old label",
                "domain": "purchases",
                "href": "/forged",
            },
            {
                "entity_type": "purchase_document",
                "entity_id": "2026-02-02|FC|88",
                "label": "88",
                "domain": "purchases",
                "href": "/forged-canceled",
            },
        ],
    )
    monkeypatch.setattr(repository_module, "get_conversation_repository", lambda: repository)
    context = _context("motoshop", "purchases")
    user = User(
        username="managed",
        hashed_password="unused",
        email="managed@test.invalid",
        role="vendedor",
        tenants_allowed=["motoshop"],
        allowed_modules=["chat-ia", "ventas-summary"],
        source="supabase",
    )
    overrides = {
        get_current_user: lambda: user,
        get_tenant: lambda: "motoshop",
        get_tenant_context: lambda: context,
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/llm/chat/conversations/{conversation['id']}/messages"
            )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 200
    assistant_message = response.json()[1]
    assert assistant_message["content"] == "La factura 77 fue recibida; la factura 88 fue anulada."
    assert len(assistant_message["entity_refs"]) == 1
    assert assistant_message["entity_refs"][0]["href"].endswith("/documento/77?cod_clase=FC")


def test_history_backfills_explicit_purchase_and_supplier_mentions_read_only(
    tenant_databases: TenantDatabases,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from motoshop_api.llm.conversations import repository as repository_module

    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "managed")
    answer = (
        "La compra fue realizada el 2 de enero de 2026.\n"
        "Documento: 55 · Clase: FC.\n"
        "Proveedor: Shared Supplier (NIT: 900111111-1)."
    )
    repository.append_turn(
        "motoshop",
        "managed",
        conversation["id"],
        "¿Cuál fue la última compra?",
        answer,
        tools_used=["get_ultima_compra"],
        entity_refs=[],
    )
    monkeypatch.setattr(repository_module, "get_conversation_repository", lambda: repository)
    context = _context("motoshop", "purchases")
    user = User(
        username="managed",
        hashed_password="unused",
        email="managed@test.invalid",
        role="vendedor",
        tenants_allowed=["motoshop"],
        allowed_modules=["chat-ia", "ventas-summary"],
        source="supabase",
    )
    overrides = {
        get_current_user: lambda: user,
        get_tenant: lambda: "motoshop",
        get_tenant_context: lambda: context,
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            response = client.get(
                f"/api/llm/chat/conversations/{conversation['id']}/messages"
            )
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)

    assert response.status_code == 200
    assistant_message = response.json()[1]
    refs = assistant_message["entity_refs"]
    assert {ref["entity_type"] for ref in refs} == {"purchase_document", "supplier"}
    assert next(ref for ref in refs if ref["entity_type"] == "purchase_document")["href"] == (
        "/dashboards/compras/dia/2026-01-02/documento/55?cod_clase=FC"
    )
    supplier_ref = next(ref for ref in refs if ref["entity_type"] == "supplier")
    assert supplier_ref["href"] == "/dashboards/compras/proveedores/900111111-1"
    assert supplier_ref["label_is_unique"] is False
    stored_message = repository.list_messages("motoshop", "managed", conversation["id"])[1]
    assert stored_message["content"] == answer
    assert stored_message["entity_refs"] == []


def test_follow_up_can_reuse_a_verified_purchase_from_conversation_history(
    tenant_databases: TenantDatabases,
) -> None:
    from motoshop_api.llm.qa_chat import ConversationManager, QAChat

    repository = InMemoryConversationRepository()
    conversation = repository.create_conversation("motoshop", "ana")
    repository.append_turn(
        "motoshop",
        "ana",
        conversation["id"],
        "¿Cuál fue la última compra?",
        "La factura 77 del 4 de enero de 2026 fue de Shared Supplier (NIT 900111111-1).",
        request_id="last-purchase",
        tools_used=["get_ultima_compra"],
        entity_refs=[],
    )

    class FollowUpLLM:
        def complete_with_tools(self, *_args, **_kwargs):
            return {"text": "La factura 77 del 4 de enero de 2026 está aquí.", "tool_calls": []}

    class Executor:
        pass

    chat = QAChat(
        FollowUpLLM(),
        ConversationManager(),
        Executor(),
        [],
        tenant_id="motoshop",
        user_id="ana",
        repository=repository,
        tenant_context=_context("motoshop", "purchases"),
    )

    reply = chat.chat(
        "Pasame el link de esa compra",
        conversation["id"],
        request_id="purchase-follow-up",
    )

    assert reply["entity_refs"] == [{
        "entity_type": "purchase_document",
        "entity_id": "2026-01-04|FC|77",
        "label": "77",
        "label_is_unique": True,
        "domain": "purchases",
        "href": "/dashboards/compras/dia/2026-01-04/documento/77?cod_clase=FC",
    }]
