"""Listado de ventas hechas por el POS web (con detalle).

Se distinguen por el journal de escritura: `app_doc_journal` sólo tiene filas de
los documentos que crea el motor, no de los que se facturan a mano en SgHermes.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.pos.router import router as pos_router
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

TENANT = "masvital"


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path/'erp.db'}")
    with eng.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_doc_journal (
                id INTEGER PRIMARY KEY, codclas TEXT, pref TEXT, docnum INTEGER,
                status TEXT, doc_type TEXT, tenant TEXT, empresa TEXT, actor TEXT,
                request_id TEXT, idempotency_key TEXT, error_msg TEXT,
                created_at TEXT, updated_at TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE facventas (
                numfven TEXT, codclas TEXT, prefven TEXT, fecfven TEXT, nitter TEXT,
                clifven TEXT, nitvend TEXT, codcaj TEXT, codpag TEXT, totfven REAL,
                estfven TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE detfventas (
                numfven TEXT, codclas TEXT, numite INTEGER, codprod TEXT, nomdet TEXT,
                candet REAL, valuni REAL, totdet REAL, codbod TEXT, codmed TEXT
            )"""))
        conn.execute(text("""
            CREATE TABLE detapago (
                numnum TEXT, codclas TEXT, codpag TEXT, valpag REAL, estado TEXT
            )"""))
        conn.execute(text(
            "INSERT INTO app_doc_journal VALUES (1,'S15','FVP',3782,'COMMITTED','',"
            ":t,'E01','javier','sale-1',NULL,NULL,'2026-11-05 10:00:00',NULL)"
        ), {"t": TENANT})
        conn.execute(text(
            "INSERT INTO facventas VALUES ('3782','S15','FVP','2026-11-05 10:00:00',"
            "'222222222','CONSUMIDOR','1151970853','C1','F01',100,'B')"
        ))
        conn.execute(text(
            "INSERT INTO detfventas VALUES ('3782','S15',1,'1204','CM Natural 360g',"
            "1,100,100,'BD01','001')"
        ))
        conn.execute(text(
            "INSERT INTO detapago VALUES ('3782','S15','F01',100,'B')"
        ))
    monkeypatch.setattr("motoshop_api.db.engine.get_engine", lambda *a, **k: eng)
    return eng


def _cliente() -> TestClient:
    app = FastAPI()
    app.include_router(pos_router, dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_tenant] = lambda: TENANT
    _tenants_cache.clear()
    tenant = Tenant(
        id=TENANT, nombre="MasVital", r2_object_key="m.duckdb",
        local_db_path="/tmp/m.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache[TENANT] = tenant
    _users_cache.clear()
    _users_cache["javier"] = User(
        username="javier", hashed_password="x", email="j@t.com", role="gerente",
        tenants_allowed=[TENANT], allowed_modules=["pos"], source="supabase",
    )
    token = create_access_token("javier", "gerente", [TENANT])
    return TestClient(app, headers={"Authorization": f"Bearer {token}", "X-Tenant": TENANT})


def test_lista_la_venta_del_pos_con_detalle(engine) -> None:
    resp = _cliente().get("/api/pos/sales?fecha=2026-11-05")

    assert resp.status_code == 200, resp.text
    ventas = resp.json()["ventas"]
    assert len(ventas) == 1
    venta = ventas[0]
    assert venta["documento"] == "FVP3782"
    assert venta["total"] == "100.0"
    assert venta["cajero"] == "javier"
    assert venta["anulada"] is False
    assert venta["lineas"][0]["codprod"] == "1204"
    assert venta["lineas"][0]["codbod"] == "BD01"
    assert venta["pagos"][0]["codpag"] == "F01"


def test_no_lista_documentos_sin_journal(engine) -> None:
    """Una factura hecha a mano en SgHermes no tiene fila en el journal."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO facventas VALUES ('9999','S15','FVP','2026-11-05 11:00:00',"
            "'222222222','MANUAL','1151970853','C1','F01',50,'B')"
        ))

    resp = _cliente().get("/api/pos/sales?fecha=2026-11-05")

    documentos = [v["documento"] for v in resp.json()["ventas"]]
    assert documentos == ["FVP3782"]
