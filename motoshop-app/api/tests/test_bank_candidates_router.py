"""Candidatos por valor (S7 · 7.2): `GET /api/erp/bank/candidates`.

La UI del POS necesita responder "¿hay un ingreso por este importe?" para
**prellenar** la captura del pago sin que el operador escriba a mano. La
respuesta es una lista de candidatos **del tenant activo**: el mismo importe
de otro tenant no aparece nunca.

Se verifica aquí: **200** con `ambiguo`/`ventana`/`candidatos` y la última
ingesta; **200** con lista vacía cuando no hay coincidencia (no es un error);
el aislamiento por tenant; **422** con un importe inválido; **403** sin el
módulo `erp-cash` y **403** sin el tenant ERP habilitado.

La cadena de guardas completa corre (JWT → matriz de módulos → tenant ERP);
sólo el store de movimientos es un doble (`FakeBankStore`).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.bankreconciliation.router import router as bank_router
from motoshop_api.erp.bankreconciliation.schemas import BankMovementIn
from motoshop_api.erp.bankreconciliation.store import (
    FakeBankStore,
    get_bank_store,
    id_dominio_movimiento,
)
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

TENANT_ID = "motoshop"
OTRO_TENANT_ID = "masvital"
VALOR = "458200.00"
FECHA = datetime.date(2026, 10, 21)


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


def _headers(username: str, role: str, modules: tuple[str, ...]) -> dict:
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
    token = create_access_token(username, role, [TENANT_ID])
    return {"Authorization": f"Bearer {token}", "X-Tenant": TENANT_ID}


def _cliente(store: FakeBankStore, *, tenant_erp: bool = True) -> TestClient:
    """Router de producción + cadena de guardas; sólo el store es falso."""
    app = FastAPI()
    app.include_router(bank_router, prefix="/api", dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_tenant] = lambda: TENANT_ID
    app.dependency_overrides[get_bank_store] = lambda: store
    if not tenant_erp:
        _tenants_cache[TENANT_ID].erp = TenantErpConfig(enabled=False, empresa="E01")
    return TestClient(app)


def _ingesta(
    store: FakeBankStore,
    tenant: str,
    id_externo: str,
    *,
    valor: str = VALOR,
    fecha: datetime.date = FECHA,
    pagador: str = "CRISTOPHER BENAMIDES P",
    referencia: str = "0092055984",
) -> None:
    """Movimiento ingerido (la referencia ya viene saneada del parser)."""
    store.upsert_movements(
        tenant,
        tenant,
        [
            BankMovementIn(
                id_externo=id_externo,
                fecha_movimiento=fecha,
                valor=Decimal(valor),
                descripcion="PAGO QR CRISTOPHER BENAMIDES P",
                referencia=referencia,
                referencia_norm=referencia,
                pagador_nombre=pagador,
                cuenta_origen="MotoShop",
            )
        ],
    )


def _get(cliente: TestClient, headers: dict, **params) -> httpx.Response:
    """GET de candidatos (con la ventana explícita salvo que se pida otra)."""
    return cliente.get(
        "/api/erp/bank/candidates",
        params={"valor": VALOR, "desde": FECHA.isoformat(), "hasta": FECHA.isoformat()} | params,
        headers=headers,
    )


def _consulta(cliente: TestClient, headers: dict, **params) -> dict:
    """GET de candidatos que debe responder 200; devuelve el cuerpo."""
    respuesta = _get(cliente, headers, **params)
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_candidates_200_devuelve_ambiguo_ventana_y_candidatos() -> None:
    """Dos ingresos del mismo importe: ambiguo, con la ventana y ambos candidatos."""
    store = FakeBankStore()
    _ingesta(store, TENANT_ID, "m1")
    _ingesta(store, TENANT_ID, "m2")
    cliente = _cliente(store)

    payload = _consulta(cliente, _headers("ger1", "gerente", ("erp-cash",)))

    assert payload["ambiguo"] is True
    assert payload["ventana"] == {"desde": "2026-10-21", "hasta": "2026-10-21"}
    assert len(payload["candidatos"]) == 2
    candidato = payload["candidatos"][0]
    assert candidato["id"] == id_dominio_movimiento(TENANT_ID, "m1")
    assert candidato["valor"] == "458200.00"
    assert candidato["pagadorNombre"] == "CRISTOPHER BENAMIDES P"
    assert candidato["referencia"] == "0092055984"
    assert candidato["fecha"] == "2026-10-21"
    # Hubo ingesta: la última ingesta del tenant se expone.
    assert payload["ultimaIngestaAt"]


def test_candidates_200_con_lista_vacia_sin_coincidencia() -> None:
    """Sin coincidencia la respuesta es 200 con lista vacía (no es un error)."""
    store = FakeBankStore()
    _ingesta(store, TENANT_ID, "m1", valor="1000.00")
    cliente = _cliente(store)

    payload = _consulta(cliente, _headers("ger2", "gerente", ("erp-cash",)))

    assert payload["candidatos"] == []
    assert payload["ambiguo"] is False
    assert payload["ventana"] == {"desde": "2026-10-21", "hasta": "2026-10-21"}


def test_candidates_solo_consulta_movimientos_del_tenant_actual() -> None:
    """El mismo importe en otro tenant no aparece: los tenants no se cruzan."""
    store = FakeBankStore()
    _ingesta(store, TENANT_ID, "m1")
    _ingesta(store, OTRO_TENANT_ID, "m2")
    cliente = _cliente(store)

    payload = _consulta(cliente, _headers("ger3", "gerente", ("erp-cash",)))

    assert len(payload["candidatos"]) == 1
    assert payload["candidatos"][0]["id"] == id_dominio_movimiento(TENANT_ID, "m1")


def test_candidates_403_sin_permisos_de_cobranzas() -> None:
    """Sin el módulo `erp-cash` la consulta se rechaza (403)."""
    store = FakeBankStore()
    _ingesta(store, TENANT_ID, "m1")
    cliente = _cliente(store)

    respuesta = _get(cliente, _headers("ven1", "vendedor", ("erp-invoicing",)))

    assert respuesta.status_code == 403, respuesta.text


def test_candidates_403_sin_tenant_erp() -> None:
    """Sin el tenant ERP habilitado la consulta no llega a los movimientos."""
    store = FakeBankStore()
    _ingesta(store, TENANT_ID, "m1")
    cliente = _cliente(store, tenant_erp=False)

    respuesta = _get(cliente, _headers("ger4", "gerente", ("erp-cash",)))

    assert respuesta.status_code == 403, respuesta.text


def test_candidates_422_con_un_importe_invalido() -> None:
    """Un importe que no es decimal (o tiene más de dos decimales) es un 422."""
    store = FakeBankStore()
    cliente = _cliente(store)
    headers = _headers("ger5", "gerente", ("erp-cash",))

    no_numerico = _get(cliente, headers, valor="no-es-un-numero")
    demasiados_decimales = _get(cliente, headers, valor="458200.001")
    ausente = cliente.get("/api/erp/bank/candidates", headers=headers)

    assert no_numerico.status_code == 422, no_numerico.text
    assert demasiados_decimales.status_code == 422, demasiados_decimales.text
    assert ausente.status_code == 422, ausente.text


def test_candidates_sin_ingesta_devuelve_ultima_ingesta_null() -> None:
    """Sin movimientos ingeridos la última ingesta es `null` (no un error)."""
    store = FakeBankStore()
    cliente = _cliente(store)

    payload = _consulta(cliente, _headers("ger6", "gerente", ("erp-cash",)))

    assert payload["candidatos"] == []
    assert payload["ultimaIngestaAt"] is None
