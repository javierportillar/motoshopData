"""Verificaciones de venta en Supabase: degradación limpia e idempotencia.

El dato no vive en el MySQL del nodo (es compartido entre dispositivos), así que
se prueba con un doble del cliente HTTP: nada de red ni de base real.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.config import settings
from motoshop_api.erp.bankreconciliation import verificaciones_venta as repo
from motoshop_api.erp.bankreconciliation.router import router as bank_router
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

TENANT_ID = "motoshop"


class _Respuesta:
    def __init__(self, status_code: int, cuerpo: object = None) -> None:
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self) -> object:
        return self._cuerpo


class _ClienteFalso:
    """Cliente httpx mínimo: registra la llamada y responde lo que se le pide."""

    def __init__(self, *, get: _Respuesta, post: _Respuesta) -> None:
        self._get = get
        self._post = post
        self.llamadas: list[tuple[str, str, dict, dict | None]] = []

    def __enter__(self) -> _ClienteFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def get(self, ruta: str, params: dict | None = None) -> _Respuesta:
        self.llamadas.append(("GET", ruta, params or {}, None))
        return self._get

    def post(
        self,
        ruta: str,
        params: dict | None = None,
        json: dict | None = None,
        headers: dict | None = None,
    ) -> _Respuesta:
        self.llamadas.append(("POST", ruta, params or {}, json))
        return self._post


@pytest.fixture()
def _supabase_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "https://proyecto.supabase.co")
    monkeypatch.setattr(settings, "supabase_service_key", "service-key-de-prueba")


def test_sin_credenciales_listar_devuelve_vacio_y_no_llama(monkeypatch) -> None:
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")

    assert repo.configurado() is False
    assert repo.listar(TENANT_ID, "2026-10-27") == []


def test_sin_credenciales_guardar_no_falla(_supabase_configurado, monkeypatch) -> None:
    """Un nodo sin Supabase no rompe la pantalla: simplemente no guarda."""
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")

    guardado = repo.guardar(
        tenant=TENANT_ID,
        cod_clase="FVP",
        num_documento="3714",
        fecha_venta="2026-10-27",
        valor=Decimal("6600.00"),
        estado="verificado",
        verificado_por="gerente",
    )

    assert guardado is False


def test_listar_filtra_por_tenant_y_fecha(_supabase_configurado, monkeypatch) -> None:
    fila = {
        "cod_clase": "FVP",
        "num_documento": "3714",
        "fecha_venta": "2026-10-27",
        "valor": 6600,
        "estado": "verificado",
        "pagador": "SANDRA MILENA ARTEAGA",
        "referencia": "0092055984",
        "fecha_movimiento": "2026-10-27",
        "job_id": "job-1",
        "verificado_por": "gerente",
        "verificado_at": "2026-10-27T16:00:00Z",
    }
    falso = _ClienteFalso(get=_Respuesta(200, [fila]), post=_Respuesta(201))
    monkeypatch.setattr(repo, "_cliente", lambda: falso)

    items = repo.listar(TENANT_ID, "2026-10-27")

    _, ruta, params, _ = falso.llamadas[0]
    assert ruta == "/bank_invoice_verifications"
    assert params["tenant"] == f"eq.{TENANT_ID}"
    assert params["fecha_venta"] == "eq.2026-10-27"
    assert items[0]["pagador"] == "SANDRA MILENA ARTEAGA"
    # El importe viaja como texto, nunca como float.
    assert items[0]["valor"] == "6600"


def test_guardar_hace_upsert_por_documento(_supabase_configurado, monkeypatch) -> None:
    falso = _ClienteFalso(get=_Respuesta(200, []), post=_Respuesta(201))
    monkeypatch.setattr(repo, "_cliente", lambda: falso)

    guardado = repo.guardar(
        tenant=TENANT_ID,
        cod_clase="FVP",
        num_documento="3714",
        fecha_venta="2026-10-27",
        valor=Decimal("6600.00"),
        estado="verificado",
        verificado_por="gerente",
        job_id="job-1",
        pagador="SANDRA MILENA ARTEAGA",
        referencia="0092055984",
        fecha_movimiento="2026-10-27",
    )

    assert guardado is True
    _, ruta, params, cuerpo = falso.llamadas[0]
    assert ruta == "/bank_invoice_verifications"
    assert params["on_conflict"] == "tenant,cod_clase,num_documento"
    assert cuerpo["valor"] == "6600.00"
    assert cuerpo["estado"] == "verificado"
    assert cuerpo["num_documento"] == "3714"


def test_guardar_rechaza_un_estado_desconocido(_supabase_configurado) -> None:
    with pytest.raises(repo.VerificacionVentaError):
        repo.guardar(
            tenant=TENANT_ID,
            cod_clase="FVP",
            num_documento="1",
            fecha_venta="2026-10-27",
            valor=Decimal("1.00"),
            estado="inventado",
            verificado_por="gerente",
        )


def test_listar_propaga_el_fallo_de_supabase(_supabase_configurado, monkeypatch) -> None:
    falso = _ClienteFalso(get=_Respuesta(500), post=_Respuesta(201))
    monkeypatch.setattr(repo, "_cliente", lambda: falso)

    with pytest.raises(repo.VerificacionVentaError):
        repo.listar(TENANT_ID, "2026-10-27")


# ── Endpoints ─────────────────────────────────────────────────────────────


def _cliente_api() -> TestClient:
    app = FastAPI()
    app.include_router(bank_router, prefix="/api", dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_tenant] = lambda: TENANT_ID
    _tenants_cache.clear()
    tenant = Tenant(
        id=TENANT_ID,
        nombre="MotoShop",
        r2_object_key="motoshop_gold.duckdb",
        local_db_path="/tmp/motoshop_gold.duckdb",
    )
    tenant.erp = TenantErpConfig(enabled=True, empresa="E01")
    _tenants_cache[TENANT_ID] = tenant
    _users_cache.clear()
    _users_cache["gerente"] = User(
        username="gerente",
        hashed_password="x",
        email="gerente@test.com",
        role="gerente",
        tenants_allowed=[TENANT_ID],
        allowed_modules=["erp-cash"],
        source="supabase",
    )
    return TestClient(app)


def _headers() -> dict:
    token = create_access_token("gerente", "gerente", [TENANT_ID])
    return {"Authorization": f"Bearer {token}", "X-Tenant": TENANT_ID}


def test_get_ventas_verificadas_sin_supabase_responde_200_vacio(monkeypatch) -> None:
    """La pantalla de ventas no se rompe si el nodo no tiene Supabase."""
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_key", "")

    respuesta = _cliente_api().get(
        "/api/erp/bank/ventas-verificadas?fecha=2026-10-27", headers=_headers()
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"fecha": "2026-10-27", "supabase": False, "items": []}


def test_get_ventas_verificadas_devuelve_las_guardadas(_supabase_configurado, monkeypatch) -> None:
    monkeypatch.setattr(
        repo,
        "listar",
        lambda tenant, fecha: [
            {
                "cod_clase": "FVP",
                "num_documento": "3714",
                "estado": "verificado",
                "pagador": "SANDRA MILENA ARTEAGA",
                "valor": "6600.00",
                "fecha_venta": fecha,
            }
        ],
    )

    respuesta = _cliente_api().get(
        "/api/erp/bank/ventas-verificadas?fecha=2026-10-27", headers=_headers()
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["supabase"] is True
    assert cuerpo["items"][0]["num_documento"] == "3714"


def test_post_estampa_la_verificacion(_supabase_configurado, monkeypatch) -> None:
    capturado: dict = {}

    def fake_guardar(**kwargs):
        capturado.update(kwargs)
        return True

    monkeypatch.setattr(repo, "guardar", fake_guardar)

    respuesta = _cliente_api().post(
        "/api/erp/bank/ventas/FVP/3714/verificacion",
        headers=_headers(),
        json={
            "fecha_venta": "2026-10-27",
            "valor": "6600.00",
            "estado": "verificado",
            "job_id": "job-1",
            "pagador": "SANDRA MILENA ARTEAGA",
            "referencia": "0092055984",
            "fecha_movimiento": "2026-10-27",
        },
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"guardado": True}
    assert capturado["tenant"] == TENANT_ID
    assert capturado["num_documento"] == "3714"
    assert capturado["verificado_por"] == "gerente"
    assert capturado["fecha_movimiento"] == "2026-10-27"


def test_post_estampado_rechaza_campos_desconocidos(_supabase_configurado) -> None:
    respuesta = _cliente_api().post(
        "/api/erp/bank/ventas/FVP/3714/verificacion",
        headers=_headers(),
        json={
            "fecha_venta": "2026-10-27",
            "valor": "6600.00",
            "estado": "verificado",
            "cliente": "no va",
        },
    )

    assert respuesta.status_code == 422, respuesta.text
