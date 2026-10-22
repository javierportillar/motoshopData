"""Router de movimientos, sync-status y aplicación (S9.3).

Se verifica: el listado es del tenant activo y filtra por estado/fecha; aplicar
exige rol de cobranzas; un movimiento de otro tenant es 404 (no se filtra su
existencia); periodo cerrado es 409; el replay con la misma clave no duplica
el documento; sync-status expone última ingesta, nodo y ventana.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.bankreconciliation.matching import FacturaCandidata
from motoshop_api.erp.bankreconciliation.node_config import NodeConfig, load_node_config
from motoshop_api.erp.bankreconciliation.repo import BankReconciliationRepo
from motoshop_api.erp.bankreconciliation.router import (
    get_node_config,
    get_reconciliation_repo,
)
from motoshop_api.erp.bankreconciliation.router import router as bank_router
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn, EstadoMovimiento
from motoshop_api.erp.bankreconciliation.store import (
    FakeBankStore,
    get_bank_store,
    id_dominio_movimiento,
)
from motoshop_api.erp.guards import PeriodLockedError
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

TENANT_ID = "motoshop"
OTRO_TENANT_ID = "masvital"
ID_MOV = id_dominio_movimiento(TENANT_ID, "mov-1")
ID_MOV_AJENO = id_dominio_movimiento(OTRO_TENANT_ID, "mov-ajeno")


class DocumentoFake:
    """Ledger de documentos de caja (recibos o consignaciones)."""

    def __init__(self, *, periodo_cerrado: bool = False) -> None:
        self.creados: list[dict[str, Any]] = []
        self.periodo_cerrado = periodo_cerrado

    def create(
        self,
        body: object,
        *,
        tenant: str,
        empresa: str,
        actor: str,
        request_id: str,
        idempotency_key: str | None,
    ) -> dict:
        if self.periodo_cerrado:
            raise PeriodLockedError("El periodo está cerrado")
        cuerpo = body.model_dump() if hasattr(body, "model_dump") else dict(body)  # type: ignore[arg-type]
        documento = {
            "numero": f"{len(self.creados) + 1:04d}",
            "prefijo": "S01",
            "tenant": tenant,
            "idempotency_key": idempotency_key,
            **cuerpo,
        }
        self.creados.append(documento)
        return documento


@pytest.fixture(autouse=True)
def _seed_backend_state():
    _tenants_cache.clear()
    tenant = Tenant(
        id=TENANT_ID,
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache[TENANT_ID] = tenant
    _tenants_cache[OTRO_TENANT_ID] = Tenant(
        id=OTRO_TENANT_ID,
        nombre="MasVital",
        r2_object_key="masvital_gold.duckdb",
        local_db_path="/tmp/masvital_gold.duckdb",
    )
    yield
    _tenants_cache.clear()
    _users_cache.clear()


def _usuario(username: str, role: str, modules: tuple[str, ...]) -> User:
    user = User(
        username=username,
        hashed_password="x",
        email=f"{username}@test.com",
        role=role,
        tenants_allowed=[TENANT_ID],
        allowed_modules=list(modules),
        source="supabase",
    )
    _users_cache[username] = user
    return user


def _headers(
    username: str,
    role: str = "gerente",
    modules: tuple[str, ...] = ("erp-cash",),
) -> dict:
    _usuario(username, role, modules)
    token = create_access_token(username, role, [TENANT_ID])
    return {"Authorization": f"Bearer {token}", "X-Tenant": TENANT_ID}


def _store() -> FakeBankStore:
    store = FakeBankStore()
    store.upsert_movements(
        TENANT_ID,
        "01",
        [
            BankMovementIn(
                id_externo="mov-1",
                fecha_movimiento=date(2026, 10, 20),
                valor=Decimal("100000.00"),
                descripcion="PAGO QR NIT 900123456",
                referencia="0092055984",
                referencia_norm="0092055984",
                pagador_nombre="DISTRIBUIDORA EL SOL",
            ),
            BankMovementIn(
                id_externo="mov-2",
                fecha_movimiento=date(2026, 10, 21),
                valor=Decimal("55000.00"),
                descripcion="TRANSFERENCIA",
                referencia="7777777",
                referencia_norm="7777777",
                pagador_nombre="OTRO PAGADOR",
            ),
        ],
    )
    store.upsert_movements(
        OTRO_TENANT_ID,
        "01",
        [
            BankMovementIn(
                id_externo="mov-ajeno",
                fecha_movimiento=date(2026, 10, 20),
                valor=Decimal("90000.00"),
                referencia="123456",
                referencia_norm="123456",
                pagador_nombre="AJENO",
            )
        ],
    )
    return store


def _repo(
    store: FakeBankStore,
    *,
    receipts: DocumentoFake | None = None,
    consignments: DocumentoFake | None = None,
) -> BankReconciliationRepo:
    factura = FacturaCandidata(
        factura_id="F-1",
        tenant=TENANT_ID,
        numfven=100,
        prefven="FVP",
        nitter="900123456",
        cliente_nombre="DISTRIBUIDORA EL SOL",
        saldo=Decimal("150000.00"),
        referencia="0092055984",
    )
    return BankReconciliationRepo(
        movements=store,
        facturas=lambda _tenant, _empresa: [factura],
        receipts=receipts or DocumentoFake(),
        consignments=consignments or DocumentoFake(),
        codpag_transferencia="F07",
    )


def _config_nodo(tmp_path: Path) -> NodeConfig:
    return load_node_config(
        {
            "BANK_SCRAPER_ENABLED": "true",
            "BANK_TENANT": TENANT_ID,
            "BANK_ACCOUNT_LABEL": "MotoShop",
            "BANK_CREDENTIAL_ENTRY": f"bancolombia-{TENANT_ID}",
            "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
            "BANK_WINDOW_START": "2026-10-20T00:00:00",
            "BANK_WINDOW_END": "2026-10-20T23:59:59",
        }
    )


def _cliente(
    tmp_path: Path,
    *,
    store: FakeBankStore,
    repo: BankReconciliationRepo,
) -> TestClient:
    app = FastAPI()
    app.include_router(bank_router, prefix="/api", dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_tenant] = lambda: TENANT_ID
    app.dependency_overrides[get_bank_store] = lambda: store
    app.dependency_overrides[get_reconciliation_repo] = lambda: repo
    app.dependency_overrides[get_node_config] = lambda: _config_nodo(tmp_path)
    return TestClient(app)


def test_listado_de_movimientos_403_sin_permisos_de_cobranzas(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.get(
        "/api/erp/bank/movements",
        headers=_headers("vend1", role="vendedor", modules=("pos",)),
    )

    assert response.status_code == 403, response.text


def test_listado_de_movimientos_solo_del_tenant_actual(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.get(
        "/api/erp/bank/movements",
        headers=_headers("ger2"),
    )

    assert response.status_code == 200, response.text
    ids = [m["id"] for m in response.json()["movimientos"]]
    assert ID_MOV in ids
    assert ID_MOV_AJENO not in ids


def test_listado_filtra_por_estado_y_rango_de_fechas(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.get(
        "/api/erp/bank/movements",
        params={
            "estado": EstadoMovimiento.PENDIENTE.value,
            "desde": "2026-10-21",
            "hasta": "2026-10-21",
        },
        headers=_headers("ger3"),
    )

    assert response.status_code == 200, response.text
    movimientos = response.json()["movimientos"]
    assert [m["fecha"] for m in movimientos] == ["2026-10-21"]


def test_apply_403_sin_permisos_de_cobranzas(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.post(
        f"/api/erp/bank/reconciliation/{ID_MOV}/apply",
        params={"factura_id": "F-1"},
        headers=_headers("vend2", role="vendedor"),
    )

    assert response.status_code == 403, response.text


def test_apply_404_para_movimiento_de_otro_tenant(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.post(
        f"/api/erp/bank/reconciliation/{ID_MOV_AJENO}/apply",
        params={"factura_id": "F-1"},
        headers=_headers("ger4"),
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error_codigo"] == "movimiento_no_encontrado"


def test_apply_409_en_periodo_cerrado(tmp_path: Path) -> None:
    store = _store()
    receipts = DocumentoFake(periodo_cerrado=True)
    client = _cliente(tmp_path, store=store, repo=_repo(store, receipts=receipts))

    response = client.post(
        f"/api/erp/bank/reconciliation/{ID_MOV}/apply",
        params={"factura_id": "F-1"},
        headers=_headers("ger5"),
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["error_codigo"] == "periodo_cerrado"
    assert receipts.creados == []
    movimiento = store.find_movement(TENANT_ID, ID_MOV)
    assert movimiento is not None and movimiento.estado == EstadoMovimiento.PENDIENTE


def test_apply_replay_con_la_misma_idempotency_key_no_duplica_documento(tmp_path: Path) -> None:
    store = _store()
    receipts = DocumentoFake()
    client = _cliente(tmp_path, store=store, repo=_repo(store, receipts=receipts))
    headers = _headers("ger6")

    primera = client.post(
        f"/api/erp/bank/reconciliation/{ID_MOV}/apply",
        params={"factura_id": "F-1"},
        headers={**headers, "Idempotency-Key": "clave-fija"},
    )
    segunda = client.post(
        f"/api/erp/bank/reconciliation/{ID_MOV}/apply",
        params={"factura_id": "F-1"},
        headers={**headers, "Idempotency-Key": "clave-fija"},
    )

    assert primera.status_code == 200, primera.text
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["replay"] is True
    assert len(receipts.creados) == 1
    assert receipts.creados[0]["idempotency_key"] == "clave-fija"


def test_sync_status_devuelve_ultima_ingesta_nodo_y_ventana(tmp_path: Path) -> None:
    store = _store()
    client = _cliente(tmp_path, store=store, repo=_repo(store))

    response = client.get("/api/erp/bank/sync-status", headers=_headers("ger7"))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["nodo"] == "MotoShop"
    assert payload["scraperHabilitado"] is True
    assert payload["ultimaIngestaAt"] is not None
    assert payload["ventana"] == {
        "desde": datetime(2026, 10, 20, 0, 0).isoformat(),
        "hasta": datetime(2026, 10, 20, 23, 59, 59).isoformat(),
    }
