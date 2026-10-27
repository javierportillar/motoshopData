"""Router de verificación bancaria (S6 · 6.3): 202, 503, 403 y 404.

El scrape del portal no cabe en un request HTTP: `POST` crea el job y
responde `202` al instante; el nodo local lo corre y el front sondea `GET`.

Se verifica aquí: `POST` → **202** con `job_id`/`estado`/`expira_en`; **503**
`scraper_no_habilitado` en la nube y **503** `tenant_no_servido` cuando el
nodo sirve a otro tenant (nunca se cruzan tenants); **403** sin permiso de
cobranzas (un `vendedor` no crea jobs) y **403** sin el tenant ERP
habilitado; `GET` → **200** con el estado (y el error si lo hubo) y **404**
para un job inexistente **o** de otro tenant (no se filtra la existencia de
jobs ajenos).

La cadena de guardas completa corre (JWT → matriz de módulos → tenant ERP →
rol de cobranzas); sólo el store de jobs y el nodo son dobles.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from motoshop_api.auth.jwt import create_access_token
from motoshop_api.auth.module_access import require_route_module
from motoshop_api.auth.tenant_dep import get_tenant
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.erp.bankreconciliation.jobs import (
    EstadoJob,
    FakeVerificationJobStore,
    get_verification_job_store,
)
from motoshop_api.erp.bankreconciliation.node_config import NodeConfig, load_node_config
from motoshop_api.erp.bankreconciliation.router import (
    get_despachador,
    get_node_config,
)
from motoshop_api.erp.bankreconciliation.router import (
    router as bank_router,
)
from motoshop_api.tenants import Tenant, TenantErpConfig, _tenants_cache

BODY = {"factura_id": "FVP-100", "valor": "458200.00"}
TENANT_ID = "motoshop"
OTRO_TENANT_ID = "masvital"


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


def _headers(username: str, role: str, modules: tuple[str, ...]) -> dict:
    _usuario(username, role, modules)
    token = create_access_token(username, role, [TENANT_ID])
    return {"Authorization": f"Bearer {token}", "X-Tenant": TENANT_ID}


def _config_nodo(tmp_path: Path, *, tenant: str = TENANT_ID, scraper: bool = True) -> NodeConfig:
    env = {
        "BANK_SCRAPER_ENABLED": "true" if scraper else "false",
        "BANK_TENANT": tenant,
        "BANK_ACCOUNT_LABEL": "MotoShop",
        "BANK_CREDENTIAL_ENTRY": f"bancolombia-{tenant}",
        "BANK_PROFILE_DIR": str(tmp_path / "perfil"),
    }
    return load_node_config(env)


def _cliente(
    tmp_path: Path,
    *,
    jobs: FakeVerificationJobStore,
    config: NodeConfig | None = None,
    despachados: list | None = None,
    tenant_erp: bool = True,
) -> TestClient:
    """Router de producción + cadena de guardas; store de jobs y nodo falsos."""
    app = FastAPI()
    app.include_router(bank_router, prefix="/api", dependencies=[Depends(require_route_module)])
    app.dependency_overrides[get_verification_job_store] = lambda: jobs
    app.dependency_overrides[get_tenant] = lambda: TENANT_ID
    app.dependency_overrides[get_node_config] = lambda: config
    app.dependency_overrides[get_despachador] = lambda: (
        despachados.append if despachados is not None else (lambda job: None)
    )
    if not tenant_erp:
        _tenants_cache[TENANT_ID].erp = TenantErpConfig(enabled=False, empresa="E01")
    return TestClient(app)


def test_post_verificaciones_responde_202_con_job_id_estado_y_expira_en(tmp_path: Path) -> None:
    """El POST crea el job y responde 202 con su identidad y su vencimiento."""
    jobs = FakeVerificationJobStore()
    despachados: list = []
    client = _cliente(
        tmp_path,
        jobs=jobs,
        config=_config_nodo(tmp_path),
        despachados=despachados,
    )

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=BODY,
        headers=_headers("ger1", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    payload = response.json()
    assert uuid.UUID(payload["job_id"]).version == 4
    assert payload["estado"] == EstadoJob.EN_COLA.value
    assert payload["expira_en"]
    # El job existe y se le entregó al worker del nodo.
    guardado = jobs.get_job(TENANT_ID, payload["job_id"])
    assert guardado is not None
    assert guardado.factura_id == "FVP-100"
    assert guardado.valor == Decimal("458200.00")
    assert [job.job_id for job in despachados] == [payload["job_id"]]


def test_post_verificaciones_503_scraper_no_habilitado(tmp_path: Path) -> None:
    """En la nube (sin scraper) el POST responde 503 con su código."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path, scraper=False))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=BODY,
        headers=_headers("ger2", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error_codigo"] == "scraper_no_habilitado"
    assert jobs.jobs == {}


def test_post_verificaciones_503_tenant_no_servido(tmp_path: Path) -> None:
    """El nodo de otro tenant no sirve este job: 503 y ningún job creado."""
    jobs = FakeVerificationJobStore()
    client = _cliente(
        tmp_path,
        jobs=jobs,
        config=_config_nodo(tmp_path, tenant=OTRO_TENANT_ID),
    )

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=BODY,
        headers=_headers("ger3", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error_codigo"] == "tenant_no_servido"
    assert jobs.jobs == {}


def test_post_verificaciones_403_sin_permisos_de_cobranzas(tmp_path: Path) -> None:
    """Un `vendedor` no crea jobs de verificación (es escritura de cobranzas)."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=BODY,
        headers=_headers("ven1", "vendedor", ("erp-cash",)),
    )

    assert response.status_code == 403, response.text
    assert jobs.jobs == {}


def test_post_verificaciones_403_sin_tenant_erp(tmp_path: Path) -> None:
    """Sin el tenant ERP habilitado la verificación no llega al job."""
    jobs = FakeVerificationJobStore()
    client = _cliente(
        tmp_path,
        jobs=jobs,
        config=_config_nodo(tmp_path),
        tenant_erp=False,
    )

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=BODY,
        headers=_headers("ger4", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 403, response.text
    assert jobs.jobs == {}


def test_get_verificaciones_200_con_estado_y_error(tmp_path: Path) -> None:
    """El sondeo devuelve el estado del job y el código de error si lo hubo."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))
    job = jobs.create_job(TENANT_ID, "FVP-100", Decimal("458200.00"))
    jobs.update_job(
        TENANT_ID,
        job.job_id,
        EstadoJob.FALLIDO,
        error_codigo="credencial_ausente",
    )

    response = client.get(
        f"/api/erp/bank/verificaciones/{job.job_id}",
        headers=_headers("ger5", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["job_id"] == job.job_id
    assert payload["estado"] == EstadoJob.FALLIDO.value
    assert payload["error"] == "credencial_ausente"
    assert payload["expira_en"]
    assert "resultado" not in payload


def test_get_verificaciones_404_para_job_de_otro_tenant(tmp_path: Path) -> None:
    """El job de otro tenant es un 404: nunca se revela su existencia."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))
    job = jobs.create_job(OTRO_TENANT_ID, "FVP-100", Decimal("458200.00"))

    response = client.get(
        f"/api/erp/bank/verificaciones/{job.job_id}",
        headers=_headers("ger6", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error_codigo"] == "job_no_encontrado"


def test_get_verificaciones_404_job_inexistente(tmp_path: Path) -> None:
    """Un `job_id` que no existe es un 404 con el mismo código."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.get(
        "/api/erp/bank/verificaciones/11111111-1111-4111-8111-111111111111",
        headers=_headers("ger7", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"]["error_codigo"] == "job_no_encontrado"


# --- El router está montado en la app de producción ---


def test_la_app_de_produccion_monta_el_router_bancario() -> None:
    """La ruta existe en la app real (si no, el front no tiene contrato)."""
    from motoshop_api.main import app as production_app

    paths = {getattr(route, "path", "") for route in production_app.routes}
    assert "/api/erp/bank/verificaciones" in paths


def test_post_verificaciones_tras_un_fallo_es_un_reintento_nuevo(tmp_path: Path) -> None:
    """Después de un job fallido, el POST no devuelve el intento muerto.

    Con la fila de dominio reutilizada tal cual, el front recibía `202` con
    `estado: fallido` y el error viejo pegado: la factura quedaba sin forma de
    reintentar cuando el portal o el OTP habían fallado.
    """
    jobs = FakeVerificationJobStore()
    despachados: list = []
    client = _cliente(
        tmp_path,
        jobs=jobs,
        config=_config_nodo(tmp_path),
        despachados=despachados,
    )
    headers = _headers("ger1", "gerente", ("erp-cash",))
    primero = client.post("/api/erp/bank/verificaciones", json=BODY, headers=headers).json()
    jobs.update_job(
        TENANT_ID,
        primero["job_id"],
        EstadoJob.FALLIDO,
        error_codigo="credencial_ausente",
    )

    response = client.post("/api/erp/bank/verificaciones", json=BODY, headers=headers)

    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["job_id"] != primero["job_id"]
    assert payload["estado"] == EstadoJob.EN_COLA.value
    guardado = jobs.get_job(TENANT_ID, payload["job_id"])
    assert guardado is not None
    assert guardado.error_codigo is None
    assert guardado.resultado is None
    assert [job.job_id for job in despachados] == [primero["job_id"], payload["job_id"]]


# --- Modo "pago": el POS todavía no tiene factura ---


def test_post_modo_pago_crea_el_job_sin_factura(tmp_path: Path) -> None:
    """Sin `factura_id` el job es de modo pago y guarda NIT y nombre."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={
            "valor": "115000.00",
            "nitter": "900123456",
            "nombre_esperado": "Valeria Castrillón",
        },
        headers=_headers("ger1", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    guardado = jobs.get_job(TENANT_ID, response.json()["job_id"])
    assert guardado is not None
    assert guardado.factura_id == ""
    assert guardado.valor == Decimal("115000.00")
    assert guardado.solicitud == {
        "modo": "pago",
        "nitter": "900123456",
        "nombre_esperado": "Valeria Castrillón",
    }


def test_post_modo_pago_sin_nit_ni_nombre_tambien_entra(tmp_path: Path) -> None:
    """El POS puede verificar sólo por importe: los datos del cliente son opcionales."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "62000.00"},
        headers=_headers("ger1", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    guardado = jobs.get_job(TENANT_ID, response.json()["job_id"])
    assert guardado is not None
    assert guardado.solicitud == {"modo": "pago"}


def test_post_modo_factura_explicito_es_el_de_siempre(tmp_path: Path) -> None:
    """`modo="factura"` con factura_id se comporta igual que antes (sin solicitud)."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "factura", **BODY},
        headers=_headers("ger1", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    guardado = jobs.get_job(TENANT_ID, response.json()["job_id"])
    assert guardado is not None
    assert guardado.factura_id == "FVP-100"
    assert guardado.solicitud is None


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"modo": "pago", "valor": "1000.00", "factura_id": "FVP-1"},
        {"modo": "factura", "valor": "1000.00"},
        {"factura_id": "FVP-1", "valor": "1000.00", "nitter": "900123456"},
        {"valor": "1000.00", "campo_desconocido": "x"},
        {"modo": "otro", "valor": "1000.00"},
    ],
)
def test_post_rechaza_combinaciones_incoherentes(tmp_path: Path, cuerpo: dict) -> None:
    """`extra="forbid"` y la coherencia de modo: 422 y ningún job creado."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json=cuerpo,
        headers=_headers("ger1", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 422, response.text
    assert jobs.jobs == {}


# ── Ventana por job: verificar el pago de ayer ────────────────────────────
#
# El portal del banco publica los movimientos de varios días, pero la ventana
# del nodo es el día en curso. `fecha` mueve la ventana de UN job para poder
# cerrar hoy una venta de ayer.


def test_post_verificaciones_con_fecha_de_ayer_la_guarda_en_la_solicitud(
    tmp_path: Path,
) -> None:
    """`fecha` viaja al job: es lo que el worker usa para mover la ventana."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))
    ayer = datetime.date.today() - datetime.timedelta(days=1)

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "30000.00", "fecha": ayer.isoformat()},
        headers=_headers("ger10", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    guardado = jobs.get_job(TENANT_ID, response.json()["job_id"])
    assert guardado is not None
    assert guardado.solicitud == {"modo": "pago", "fecha": ayer.isoformat()}


def test_post_verificaciones_sin_fecha_no_cambia_el_contrato(tmp_path: Path) -> None:
    """Sin `fecha` la solicitud es la histórica: el día en curso sigue igual."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "30000.00"},
        headers=_headers("ger11", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 202, response.text
    guardado = jobs.get_job(TENANT_ID, response.json()["job_id"])
    assert guardado is not None
    assert guardado.solicitud == {"modo": "pago"}


def test_post_verificaciones_rechaza_fecha_futura(tmp_path: Path) -> None:
    """Una fecha futura no tiene movimientos: 422 y ningún job creado."""
    jobs = FakeVerificationJobStore()
    client = _cliente(tmp_path, jobs=jobs, config=_config_nodo(tmp_path))
    manana = datetime.date.today() + datetime.timedelta(days=1)

    response = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "30000.00", "fecha": manana.isoformat()},
        headers=_headers("ger12", "gerente", ("erp-cash",)),
    )

    assert response.status_code == 422, response.text
    assert jobs.jobs == {}


def test_post_verificaciones_mismo_valor_en_dos_dias_son_dos_jobs(
    tmp_path: Path,
) -> None:
    """La idempotencia es por importe Y día: el de ayer no tapa al de hoy."""
    jobs = FakeVerificationJobStore()
    despachados: list = []
    client = _cliente(
        tmp_path, jobs=jobs, config=_config_nodo(tmp_path), despachados=despachados
    )
    ayer = datetime.date.today() - datetime.timedelta(days=1)
    headers = _headers("ger13", "gerente", ("erp-cash",))

    hoy_job = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "30000.00"},
        headers=headers,
    )
    ayer_job = client.post(
        "/api/erp/bank/verificaciones",
        json={"modo": "pago", "valor": "30000.00", "fecha": ayer.isoformat()},
        headers=headers,
    )

    assert hoy_job.status_code == 202, hoy_job.text
    assert ayer_job.status_code == 202, ayer_job.text
    assert hoy_job.json()["job_id"] != ayer_job.json()["job_id"]
    assert len(jobs.jobs) == 2
    assert len(despachados) == 2
