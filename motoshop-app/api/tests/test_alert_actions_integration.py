"""
Pruebas de integración con Docker MySQL 8.4.

Requiere:
  - Docker MySQL 8.4 en localhost:3306 (password root: 12345)
  - Ejecutar: python -m pytest api/tests/test_alert_actions_integration.py -v --tb=short

El fixture setUp crea el usuario app_writer y las tablas app_alert_actions
y app_audit_log en una DB de test, y las destruye al finalizar.
"""

from __future__ import annotations

import os
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from motoshop_api.app_writes.repo import (
    AuditRepo,
    RealAlertActionsRepo,
    get_alert_actions_repo,
    get_audit_repo,
)
from motoshop_api.app_writes.schemas import AlertActionRequest

# ─── Config ─────────────────────────────────────────────────────────────────

DOCKER_MYSQL_HOST = "127.0.0.1"
DOCKER_ROOT_PASS = "12345"
DOCKER_APP_WRITER_PASS = os.getenv("MYSQL_APP_WRITER_PASSWORD", "app_writer_test_pass")
TEST_DB = "motoshop_test"


def _docker_exec(sql: str, db: str = "") -> str:
    """Ejecuta SQL en Docker MySQL y devuelve stdout."""
    db_arg = [f"-D{db}"] if db else []
    args = ["docker", "exec", "-i", "mysql2", "mysql", f"-uroot", f"-p{DOCKER_ROOT_PASS}"] + db_arg + ["-e", sql]
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def _setup_integration():
    """Crea el usuario app_writer, la DB de test y las tablas.

    Corresponde a F5-001 + F5-002 + F5-003 para la DB de test.
    """
    # Verificar conectividad
    try:
        _docker_exec("SELECT 1")
    except Exception as e:
        pytest.skip(f"Docker MySQL no disponible: {e}")

    # 1. Crear DB de test
    _docker_exec(f"CREATE DATABASE IF NOT EXISTS {TEST_DB} CHARACTER SET utf8 COLLATE utf8_general_ci")

    # 2. Crear usuario app_writer si no existe
    result = _docker_exec("SELECT COUNT(*) FROM mysql.user WHERE user='app_writer' AND host='%'")
    if "0" in result or not result:
        _docker_exec(
            f"CREATE USER 'app_writer'@'%' IDENTIFIED BY '{DOCKER_APP_WRITER_PASS}'"
        )
    _docker_exec(f"GRANT ALL PRIVILEGES ON {TEST_DB}.* TO 'app_writer'@'%'")
    _docker_exec("FLUSH PRIVILEGES")

    # 3. Crear tablas (F5-001: app_alert_actions)
    _docker_exec(
        f"CREATE TABLE IF NOT EXISTS {TEST_DB}.app_alert_actions ("
        f"id BIGINT AUTO_INCREMENT PRIMARY KEY,"
        f"alert_id VARCHAR(50) NOT NULL,"
        f"sku VARCHAR(50) NOT NULL,"
        f"user_id VARCHAR(100) NOT NULL,"
        f"action_type ENUM('ordered','dismissed','postponed') NOT NULL,"
        f"quantity DECIMAL(10,2) DEFAULT NULL,"
        f"supplier VARCHAR(255) DEFAULT NULL,"
        f"reason VARCHAR(500) DEFAULT NULL,"
        f"postponed_to DATE DEFAULT NULL,"
        f"notes TEXT DEFAULT NULL,"
        f"idempotency_key VARCHAR(36) NOT NULL,"
        f"created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        f"request_id VARCHAR(36) NOT NULL,"
        f"UNIQUE KEY uq_idempotency (idempotency_key),"
        f"INDEX idx_alert_id (alert_id),"
        f"INDEX idx_user_id (user_id),"
        f"INDEX idx_created_at (created_at)"
        f") ENGINE=InnoDB DEFAULT CHARSET=utf8",
        db=TEST_DB,
    )

    # 4. Crear tabla audit (F5-002: app_audit_log)
    _docker_exec(
        f"CREATE TABLE IF NOT EXISTS {TEST_DB}.app_audit_log ("
        f"id BIGINT AUTO_INCREMENT PRIMARY KEY,"
        f"user_id VARCHAR(100) NOT NULL,"
        f"user_role VARCHAR(50) NOT NULL,"
        f"action VARCHAR(50) NOT NULL,"
        f"target_type VARCHAR(50) NOT NULL,"
        f"target_id VARCHAR(100) NOT NULL,"
        f"request_id VARCHAR(36) NOT NULL,"
        f"ip_address VARCHAR(45) DEFAULT NULL,"
        f"user_agent VARCHAR(500) DEFAULT NULL,"
        f"payload TEXT DEFAULT NULL,"
        f"status VARCHAR(20) NOT NULL DEFAULT 'success',"
        f"error_msg TEXT DEFAULT NULL,"
        f"created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        f"INDEX idx_audit_user (user_id),"
        f"INDEX idx_audit_action (action),"
        f"INDEX idx_audit_created (created_at)"
        f") ENGINE=InnoDB DEFAULT CHARSET=utf8",
        db=TEST_DB,
    )

    yield

    # Teardown: limpiar
    try:
        _docker_exec(f"DROP DATABASE IF EXISTS {TEST_DB}")
    except Exception:
        pass


@pytest.fixture()
def _patch_settings():
    """Parchea settings para apuntar a Docker MySQL con app_writer."""
    from motoshop_api.db.engine import reset_engine

    from motoshop_api.config import settings as _s

    _s.mysql_app_writer_password = DOCKER_APP_WRITER_PASS
    _s.mysql_host = DOCKER_MYSQL_HOST
    _s.mysql_database = TEST_DB
    reset_engine()  # fuerza recreación del writer engine con nueva URL
    yield
    reset_engine()


@pytest.fixture()
def real_repo(_setup_integration, _patch_settings) -> RealAlertActionsRepo:
    return RealAlertActionsRepo()


@pytest.fixture()
def audit_repo(_setup_integration, _patch_settings) -> AuditRepo:
    return AuditRepo()


# ─── Tests ──────────────────────────────────────────────────────────────────


class TestRealRepoDockerMySQL:
    def test_create_and_get_by_idempotency(self, real_repo: RealAlertActionsRepo) -> None:
        key = "00000000-0000-4000-a000-000000000001"
        result = real_repo.create_action(
            alert_id="INTEG-001", sku="INTEG-001",
            user_id="test_user", request_id="req-001",
            body=AlertActionRequest(action_type="dismissed", reason="test"),
            idempotency_key=key,
        )
        assert result.id == 1
        assert result.alert_id == "INTEG-001"
        assert result.action_type == "dismissed"
        assert result.user_id == "test_user"

        same = real_repo.get_action_by_idempotency_key(key)
        assert same is not None
        assert same.id == result.id

    def test_idempotency_replay_returns_same(self, real_repo: RealAlertActionsRepo) -> None:
        key = "00000000-0000-4000-a000-000000000002"
        request = AlertActionRequest(action_type="ordered", quantity=Decimal("10"), supplier="Test")
        first = real_repo.create_action(
            alert_id="INTEG-002", sku="INTEG-002",
            user_id="admin", request_id="req-002",
            body=request, idempotency_key=key,
        )
        second = real_repo.create_action(
            alert_id="INTEG-002", sku="INTEG-002",
            user_id="admin", request_id="req-002",
            body=request, idempotency_key=key,
        )
        assert first.id == second.id
        assert first.created_at == second.created_at

    def test_list_user_actions(self, real_repo: RealAlertActionsRepo) -> None:
        user = "list_user"
        for i in range(3):
            real_repo.create_action(
                alert_id=f"LIST-{i:03d}", sku=f"LIST-{i:03d}",
                user_id=user, request_id=f"req-list-{i}",
                body=AlertActionRequest(action_type="dismissed", reason=f"razón {i}"),
                idempotency_key=f"00000000-0000-4000-a000-00000000001{i}",
            )

        result = real_repo.list_user_actions(user_id=user, limit=10, offset=0)
        assert result.total == 3
        assert len(result.items) == 3

    def test_list_actions_with_date_filter(self, real_repo: RealAlertActionsRepo) -> None:
        today = date.today()
        result = real_repo.list_user_actions(
            user_id="any_user", date_from=today, date_to=today,
        )
        assert result.total >= 0
        assert isinstance(result.items, list)

    def test_create_ordered_with_quantity(self, real_repo: RealAlertActionsRepo) -> None:
        key = "00000000-0000-4000-a000-000000000020"
        result = real_repo.create_action(
            alert_id="INTEG-003", sku="INTEG-003",
            user_id="admin", request_id="req-020",
            body=AlertActionRequest(
                action_type="ordered",
                quantity=Decimal("25.5"),
                supplier="Proveedor Z",
                notes="Nota de prueba",
            ),
            idempotency_key=key,
        )
        assert result.action_type == "ordered"

    def test_create_postponed(self, real_repo: RealAlertActionsRepo) -> None:
        key = "00000000-0000-4000-a000-000000000021"
        result = real_repo.create_action(
            alert_id="INTEG-004", sku="INTEG-004",
            user_id="admin", request_id="req-021",
            body=AlertActionRequest(
                action_type="postponed",
                postponed_to=date(2026, 7, 1),
            ),
            idempotency_key=key,
        )
        assert result.action_type == "postponed"

    def test_audit_log(self, audit_repo: AuditRepo) -> None:
        audit_repo.log(
            user_id="test_user", user_role="admin",
            action="create_action", target_type="alert",
            target_id="AUDIT-001", request_id="req-audit-001",
            ip_address="127.0.0.1", user_agent="pytest",
            payload={"action_type": "dismissed", "reason": "test"},
        )
        assert True

    def test_create_through_http_endpoint(self) -> None:
        """End-to-end: FastAPI → RealAlertActionsRepo via HTTP."""
        import uuid

        from motoshop_api.auth.hash import hash_password
        from motoshop_api.auth.users import _users_cache, User
        from motoshop_api.main import app

        _users_cache.clear()
        _users_cache["admin"] = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            email="admin@test.com",
            role="admin",
        )

        app.dependency_overrides[get_alert_actions_repo] = lambda: RealAlertActionsRepo()
        app.dependency_overrides[get_audit_repo] = lambda: AuditRepo()

        client = TestClient(app, raise_server_exceptions=False)
        token = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).json()["access_token"]

        key = str(uuid.uuid4())
        resp = client.post(
            "/api/alerts/HTTP-TEST/action",
            json={"action_type": "dismissed", "reason": "test"},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        assert resp.status_code == 201, f"resp={resp.status_code} body={resp.text[:200]}"
        body = resp.json()
        assert body["alert_id"] == "HTTP-TEST"

        # Replay
        resp2 = client.post(
            "/api/alerts/HTTP-TEST/action",
            json={"action_type": "dismissed", "reason": "test"},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        )
        assert resp2.status_code == 200, f"resp={resp2.status_code} body={resp2.text[:200]}"
        assert resp2.json() == body
