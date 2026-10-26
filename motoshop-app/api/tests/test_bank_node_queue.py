"""Plano de control del nodo (F0/F1): candado por cuenta, cola y dos relojes.

Dos capas de prueba, a proposito:

1. **API** (`test_*_api*`) con un `NodoStore` de mentira: cubre el contrato
   HTTP (token, 401/503, 409, 422) y el modo de despacho sin tocar la base.
2. **SQL real** (`test_*_sql*`): el candado y los dos relojes viven en SQL
   (`INSERT ... ON DUPLICATE KEY UPDATE`, `UPDATE ... ORDER BY ... LIMIT`), y
   un doble en memoria probaria la mentira, no la regla. Corren contra la
   MySQL del nodo y se saltean solos donde no hay base:

       pytest tests/test_bank_node_queue.py -m integration
       BANK_TEST_MYSQL=1 pytest tests/test_bank_node_queue.py

   Cada test usa tenants `t-queue-*` y limpia lo suyo: no toca jobs reales.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from motoshop_api.erp.bankreconciliation import node_router
from motoshop_api.erp.bankreconciliation.node_router import (
    CODIGO_SESION_CERRADA,
    CODIGO_SIN_NODO,
    EXEC_TTL_SEGUNDOS,
    LOCK_TTL_SEGUNDOS,
    QUEUE_TTL_SEGUNDOS,
    NodoStore,
    configurar_modo_despacho,
    modo_despacho,
)
from motoshop_api.erp.bankreconciliation.jobs import RealVerificationJobStore

# --- fixtures --------------------------------------------------------------

TOKEN = "token-de-prueba-del-nodo"


@pytest.fixture()
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    """Token del agente para toda la sesion de tests."""
    monkeypatch.setenv("BANK_NODE_TOKEN", TOKEN)
    return TOKEN


class StoreFalso:
    """Doble en memoria del contrato del store (solo para la capa HTTP)."""

    def __init__(self) -> None:
        self.nodos: dict[str, dict[str, Any]] = {}
        self.locks: dict[str, tuple[str, datetime]] = {}
        self.jobs: list[dict[str, Any]] = []
        self.publicados: list[tuple[str, str, str, str | None]] = []

    def heartbeat(self, node_id, tenants, *, slots_libres, slots_ocupados, version=None, ahora=None):
        self.nodos[node_id] = {"tenants": list(tenants), "latida_en": ahora or datetime.utcnow()}

    def tenants_en_linea(self, ahora=None):
        return {t: [n] for n, datos in self.nodos.items() for t in datos["tenants"]}

    def adquirir_lock(self, tenant, node_id, *, ahora=None):
        instante = ahora or datetime.utcnow()
        dueño = self.locks.get(tenant)
        if dueño and dueño[0] != node_id and dueño[1] > instante:
            return False
        self.locks[tenant] = (node_id, instante + timedelta(seconds=LOCK_TTL_SEGUNDOS))
        return True

    def renovar_lock(self, tenant, node_id, *, ahora=None):
        dueño = self.locks.get(tenant)
        if not dueño or dueño[0] != node_id:
            return False
        self.locks[tenant] = (node_id, (ahora or datetime.utcnow()) + timedelta(seconds=LOCK_TTL_SEGUNDOS))
        return True

    def liberar_lock(self, tenant, node_id):
        dueño = self.locks.get(tenant)
        if dueño and dueño[0] == node_id:
            self.locks.pop(tenant, None)

    def claim(self, tenant, node_id, *, ahora=None):
        for job in self.jobs:
            if job["tenant"] == tenant and job["estado"] == "en_cola":
                job["estado"] = "ejecutando"
                job["nodo"] = node_id
                return dict(job)
        return None

    def publicar(self, tenant, node_id, job_id, estado, *, resultado=None, error_codigo=None, ahora=None):
        if estado not in node_router.ESTADOS_PUBLICABLES:
            raise ValueError(f"estado no publicable: {estado}")
        self.publicados.append((tenant, node_id, job_id, estado))
        return True


@pytest.fixture()
def app_control(token: str, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, StoreFalso]:
    """App minima con el router del nodo y el store de mentira inyectado."""
    store = StoreFalso()
    app = FastAPI()
    app.include_router(node_router.router, prefix="/api/erp/bank/node")
    app.dependency_overrides[node_router.get_nodo_store] = lambda: store
    return TestClient(app), store


# --- modo de despacho ------------------------------------------------------


def test_modo_por_defecto_es_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin variable (o con basura) el despacho es el de siempre."""
    monkeypatch.delenv("BANK_DISPATCH_MODE", raising=False)
    assert modo_despacho() == node_router.MODO_LOCAL
    monkeypatch.setenv("BANK_DISPATCH_MODE", "cualquier-cosa")
    assert modo_despacho() == node_router.MODO_LOCAL


def test_modo_local_no_toca_los_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """`local` es la red de seguridad: no debe registrar ningun override."""
    from motoshop_api.erp.bankreconciliation.router import get_despachador

    monkeypatch.delenv("BANK_DISPATCH_MODE", raising=False)
    app = FastAPI()
    configurar_modo_despacho(app)
    assert get_despachador not in app.dependency_overrides


def test_modo_queue_reemplaza_el_despacho_por_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """En `queue` el POST encola: el despachador no lanza hilo ni raspa."""
    from motoshop_api.erp.bankreconciliation.router import get_despachador

    monkeypatch.setenv("BANK_DISPATCH_MODE", "queue")
    app = FastAPI()
    configurar_modo_despacho(app)
    despachador = app.dependency_overrides[get_despachador]()
    assert despachador(None) is None  # no lanza, no raspa, no toca estados


# --- contrato HTTP ---------------------------------------------------------


def test_sin_token_configurado_falla_cerrado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin `BANK_NODE_TOKEN` el plano de control no atiende a nadie (503)."""
    monkeypatch.delenv("BANK_NODE_TOKEN", raising=False)
    app = FastAPI()
    app.include_router(node_router.router, prefix="/api/erp/bank/node")
    app.dependency_overrides[node_router.get_nodo_store] = lambda: StoreFalso()
    resp = TestClient(app).post(
        "/api/erp/bank/node/heartbeat", json={"node_id": "n1", "tenants": ["t"]}
    )
    assert resp.status_code == 503


def test_token_invalido_es_401(app_control: tuple[TestClient, StoreFalso]) -> None:
    cliente, _ = app_control
    resp = cliente.post(
        "/api/erp/bank/node/heartbeat",
        json={"node_id": "n1", "tenants": ["t"]},
        headers={"X-Node-Token": "otro"},
    )
    assert resp.status_code == 401


def test_heartbeat_registra_el_nodo(app_control: tuple[TestClient, StoreFalso], token: str) -> None:
    cliente, store = app_control
    resp = cliente.post(
        "/api/erp/bank/node/heartbeat",
        json={"node_id": "pc-1", "tenants": ["masvital"], "slots_libres": 1, "version": "1.0.0"},
        headers={"X-Node-Token": token},
    )
    assert resp.status_code == 200
    assert store.nodos["pc-1"]["tenants"] == ["masvital"]
    assert resp.json()["tenants_en_linea"] == {"masvital": ["pc-1"]}


def test_claim_entrega_el_job_y_toma_el_candado(
    app_control: tuple[TestClient, StoreFalso], token: str
) -> None:
    cliente, store = app_control
    store.jobs.append({"job_id": "j-1", "tenant": "masvital", "estado": "en_cola"})
    resp = cliente.post(
        "/api/erp/bank/node/claim",
        json={"node_id": "pc-1", "tenants": ["masvital"]},
        headers={"X-Node-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["job"]["job_id"] == "j-1"
    assert store.locks["masvital"][0] == "pc-1"


def test_claim_sin_candado_no_entrega_y_no_lo_toca(
    app_control: tuple[TestClient, StoreFalso], token: str
) -> None:
    """Nodo B con el candado en mano de A: no hay job y el portal ni se mira."""
    cliente, store = app_control
    store.jobs.append({"job_id": "j-1", "tenant": "masvital", "estado": "en_cola"})
    store.adquirir_lock("masvital", "pc-a")
    resp = cliente.post(
        "/api/erp/bank/node/claim",
        json={"node_id": "pc-b", "tenants": ["masvital"]},
        headers={"X-Node-Token": token},
    )
    assert resp.json() == {"job": None}
    assert store.jobs[0]["estado"] == "en_cola"


def test_renovar_sin_ser_dueño_es_409(
    app_control: tuple[TestClient, StoreFalso], token: str
) -> None:
    cliente, store = app_control
    store.adquirir_lock("masvital", "pc-a")
    resp = cliente.post(
        "/api/erp/bank/node/lock/renew",
        json={"node_id": "pc-b", "tenant": "masvital"},
        headers={"X-Node-Token": token},
    )
    assert resp.status_code == 409


def test_estado_no_publicable_es_422(
    app_control: tuple[TestClient, StoreFalso], token: str
) -> None:
    cliente, _ = app_control
    resp = cliente.post(
        "/api/erp/bank/node/jobs/j-1/result?tenant=masvital",
        json={"node_id": "pc-1", "estado": "inventado"},
        headers={"X-Node-Token": token},
    )
    assert resp.status_code == 422


def test_publicar_sesion_cerrada_devuelve_el_job_a_la_cola(
    app_control: tuple[TestClient, StoreFalso], token: str
) -> None:
    cliente, store = app_control
    resp = cliente.post(
        "/api/erp/bank/node/jobs/j-1/result?tenant=masvital",
        json={
            "node_id": "pc-1",
            "estado": "en_cola",
            "error_codigo": CODIGO_SESION_CERRADA,
        },
        headers={"X-Node-Token": token},
    )
    assert resp.status_code == 200
    assert store.publicados == [("masvital", "pc-1", "j-1", "en_cola")]


# --- SQL real (sólo con base) ---------------------------------------------


def _mysql_engine():
    from sqlalchemy import create_engine, text

    url = os.environ.get(
        "BANK_TEST_MYSQL_URL", "mysql+pymysql://root:@localhost:3306/masvital?charset=utf8"
    )
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - sin base, estos tests se saltean
        pytest.skip(f"sin MySQL para los tests de SQL: {exc}")
    return engine


@pytest.fixture()
def mysql():
    if os.environ.get("BANK_TEST_MYSQL") != "1":
        pytest.skip("BANK_TEST_MYSQL=1 para los tests de SQL real")
    from sqlalchemy import text

    engine = _mysql_engine()
    tenants = ("t-queue-a", "t-queue-b")
    with engine.connect() as conn:
        for tenant in tenants:
            conn.execute(
                text("DELETE FROM app_bank_verification_jobs WHERE tenant = :t"), {"t": tenant}
            )
            conn.execute(
                text("DELETE FROM app_bank_account_locks WHERE tenant = :t"), {"t": tenant}
            )
        conn.execute(text("DELETE FROM app_bank_nodes WHERE node_id LIKE 'tq-%'"))
        conn.commit()
    yield engine
    with engine.connect() as conn:
        for tenant in tenants:
            conn.execute(
                text("DELETE FROM app_bank_verification_jobs WHERE tenant = :t"), {"t": tenant}
            )
            conn.execute(
                text("DELETE FROM app_bank_account_locks WHERE tenant = :t"), {"t": tenant}
            )
        conn.execute(text("DELETE FROM app_bank_nodes WHERE node_id LIKE 'tq-%'"))
        conn.commit()
    engine.dispose()


def _crear_job(engine, tenant: str, *, estado: str, creado: datetime, actualizado: datetime | None = None,
               expira: datetime | None = None) -> str:
    from sqlalchemy import text

    job_id = str(uuid.uuid4())
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO app_bank_verification_jobs "
                "(id, job_id, tenant, factura_id, valor, estado, nodo, resultado_json, "
                " solicitud_json, error_codigo, creado_en, actualizado_en, expira_en, intentos) "
                "VALUES (:id, :job_id, :tenant, 'FV-1', 100.00, :estado, NULL, NULL, NULL, NULL, "
                " :creado, :actualizado, :expira, 0)"
            ),
            {
                "id": job_id,
                "job_id": job_id,
                "tenant": tenant,
                "estado": estado,
                "creado": creado,
                "actualizado": actualizado or creado,
                "expira": expira or (creado + timedelta(seconds=QUEUE_TTL_SEGUNDOS)),
            },
        )
        conn.commit()
    return job_id


def _estado(engine, job_id: str) -> dict[str, Any]:
    from sqlalchemy import text

    with engine.connect() as conn:
        fila = conn.execute(
            text(
                "SELECT estado, nodo, intentos, error_codigo FROM app_bank_verification_jobs "
                "WHERE job_id = :j"
            ),
            {"j": job_id},
        ).mappings().first()
    return dict(fila) if fila else {}


@pytest.mark.integration
def test_sql_candado_por_cuenta_y_liberacion(mysql) -> None:
    store = NodoStore(mysql)
    t0 = datetime(2026, 10, 23, 12, 0, 0)
    assert store.adquirir_lock("t-queue-a", "tq-1", ahora=t0) is True
    assert store.adquirir_lock("t-queue-a", "tq-2", ahora=t0) is False
    # El dueño renueva sin soltar.
    assert store.renovar_lock("t-queue-a", "tq-1", ahora=t0 + timedelta(seconds=20)) is True
    store.liberar_lock("t-queue-a", "tq-1")
    assert store.adquirir_lock("t-queue-a", "tq-2", ahora=t0 + timedelta(seconds=21)) is True


@pytest.mark.integration
def test_sql_candado_vencido_lo_toma_otro(mysql) -> None:
    store = NodoStore(mysql)
    t0 = datetime(2026, 10, 23, 12, 0, 0)
    assert store.adquirir_lock("t-queue-a", "tq-1", ahora=t0) is True
    # Dentro del TTL: no.
    assert store.adquirir_lock("t-queue-a", "tq-2", ahora=t0 + timedelta(seconds=LOCK_TTL_SEGUNDOS - 1)) is False
    # Pasado el TTL: si.
    assert store.adquirir_lock("t-queue-a", "tq-2", ahora=t0 + timedelta(seconds=LOCK_TTL_SEGUNDOS + 1)) is True
    assert store.lock_de("t-queue-a")["node_id"] == "tq-2"


@pytest.mark.integration
def test_sql_claim_fifo_y_reloj_de_ejecucion(mysql) -> None:
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    viejo = _crear_job(mysql, "t-queue-a", estado="en_cola", creado=ahora - timedelta(minutes=5))
    nuevo = _crear_job(mysql, "t-queue-a", estado="en_cola", creado=ahora - timedelta(minutes=1))
    assert store.adquirir_lock("t-queue-a", "tq-1", ahora=ahora) is True
    job = store.claim("t-queue-a", "tq-1", ahora=ahora)
    assert job is not None and job["job_id"] == viejo
    fila = _estado(mysql, viejo)
    assert fila["estado"] == "ejecutando" and fila["nodo"] == "tq-1"
    # El segundo job sigue en la cola (un scrape por cuenta a la vez).
    assert _estado(mysql, nuevo)["estado"] == "en_cola"


@pytest.mark.integration
def test_sql_rescate_de_ejecutando_vencido_dos_intentos(mysql) -> None:
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    job_id = _crear_job(
        mysql,
        "t-queue-a",
        estado="ejecutando",
        creado=ahora - timedelta(minutes=10),
        actualizado=ahora - timedelta(seconds=EXEC_TTL_SEGUNDOS + 5),
    )
    assert store.rescatar_vencidos(ahora=ahora) == 1
    fila = _estado(mysql, job_id)
    assert fila["estado"] == "en_cola" and fila["nodo"] is None and fila["intentos"] == 1
    # Segundo vencimiento: se corta el bucle, queda fallido.
    from sqlalchemy import text

    with mysql.connect() as conn:
        conn.execute(
            text(
                "UPDATE app_bank_verification_jobs SET estado='ejecutando', nodo='tq-1', "
                "actualizado_en=:a WHERE job_id=:j"
            ),
            {"a": ahora - timedelta(seconds=EXEC_TTL_SEGUNDOS + 5), "j": job_id},
        )
        conn.commit()
    assert store.rescatar_vencidos(ahora=ahora) == 1
    fila = _estado(mysql, job_id)
    assert fila["estado"] == "fallido" and fila["intentos"] == 2


@pytest.mark.integration
def test_sql_cola_vencida_es_expirado_sin_nodo(mysql) -> None:
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    job_id = _crear_job(
        mysql,
        "t-queue-a",
        estado="en_cola",
        creado=ahora - timedelta(seconds=QUEUE_TTL_SEGUNDOS + 5),
    )
    assert store.expirar_cola(ahora=ahora) == 1
    fila = _estado(mysql, job_id)
    assert fila["estado"] == "expirado" and fila["error_codigo"] == CODIGO_SIN_NODO


@pytest.mark.integration
def test_sql_el_barrido_de_jobs_escribe_sin_nodo_sobre_la_cola_vencida(mysql) -> None:
    """El `SET` va ordenado: `error_codigo` tiene que ver el `estado` viejo.

    MySQL 5.0 evalua las asignaciones del `UPDATE` de izquierda a derecha. Con
    `estado = 'expirado'` primero, el `CASE` ve `expirado` y el motivo se
    pierde en silencio (la fila queda expirada sin decir por que).
    """
    store = RealVerificationJobStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    vencido = _crear_job(
        mysql,
        "t-queue-a",
        estado="en_cola",
        creado=ahora - timedelta(seconds=901),
        expira=ahora - timedelta(seconds=1),
    )
    viva = _crear_job(
        mysql,
        "t-queue-a",
        estado="en_cola",
        creado=ahora,
        expira=ahora + timedelta(seconds=900),
    )

    assert store.expire_stale_jobs(ahora) >= 1

    assert _estado(mysql, vencido)["estado"] == "expirado"
    assert _estado(mysql, vencido)["error_codigo"] == CODIGO_SIN_NODO
    assert _estado(mysql, viva)["estado"] == "en_cola"


@pytest.mark.integration
def test_sql_publicar_sesion_cerrada_y_ajeno(mysql) -> None:
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    job_id = _crear_job(mysql, "t-queue-a", estado="en_cola", creado=ahora - timedelta(minutes=1))
    assert store.adquirir_lock("t-queue-a", "tq-1", ahora=ahora) is True
    assert store.claim("t-queue-a", "tq-1", ahora=ahora)["job_id"] == job_id
    # Otro nodo no puede publicar el job ajeno.
    assert store.publicar("t-queue-a", "tq-2", job_id, "resuelto", ahora=ahora) is False
    # El dueño sí, y "sesión cerrada" lo devuelve a la cola sin dueño.
    assert (
        store.publicar(
            "t-queue-a",
            "tq-1",
            job_id,
            "en_cola",
            error_codigo=CODIGO_SESION_CERRADA,
            ahora=ahora,
        )
        is True
    )
    fila = _estado(mysql, job_id)
    assert fila["estado"] == "en_cola" and fila["nodo"] is None
    assert fila["error_codigo"] == CODIGO_SESION_CERRADA


@pytest.mark.integration
def test_sql_heartbeat_y_ventana_de_caida(mysql) -> None:
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    store.heartbeat("tq-1", ["t-queue-a"], slots_libres=1, slots_ocupados=0, ahora=ahora)
    store.heartbeat("tq-2", ["t-queue-b"], slots_libres=1, slots_ocupados=0, ahora=ahora - timedelta(seconds=120))
    en_linea = store.tenants_en_linea(ahora=ahora)
    assert en_linea == {"t-queue-a": ["tq-1"]}


@pytest.mark.integration
def test_sql_dos_tenants_no_se_estorban(mysql) -> None:
    """Dos cuentas distintas sí pueden tener un scrape cada una a la vez."""
    store = NodoStore(mysql)
    ahora = datetime(2026, 10, 23, 12, 0, 0)
    a = _crear_job(mysql, "t-queue-a", estado="en_cola", creado=ahora - timedelta(minutes=2))
    b = _crear_job(mysql, "t-queue-b", estado="en_cola", creado=ahora - timedelta(minutes=1))
    assert store.adquirir_lock("t-queue-a", "tq-1", ahora=ahora) is True
    assert store.adquirir_lock("t-queue-b", "tq-2", ahora=ahora) is True
    assert store.claim("t-queue-a", "tq-1", ahora=ahora)["job_id"] == a
    assert store.claim("t-queue-b", "tq-2", ahora=ahora)["job_id"] == b
