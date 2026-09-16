"""Tests unitarios, de seguridad y de integración para reportes y descargas."""

from __future__ import annotations

import io
import time

import pytest
from fastapi.testclient import TestClient

from motoshop_api.auth.hash import hash_password
from motoshop_api.auth.users import User, _users_cache
from motoshop_api.llm.tools import ToolExecutor
from motoshop_api.main import app
from motoshop_api.reports.generator import ReportData, generate_excel, generate_pdf, generate_word
from motoshop_api.reports.storage import ReportStorage


@pytest.fixture()
def tenant_users():
    """Usuarios restringidos por tenant para probar el aislamiento de descargas."""
    _users_cache.clear()
    users = {
        "moto_user": User(
            username="moto_user",
            hashed_password=hash_password("moto123"),
            email="moto@test.com",
            role="gerente",
            tenants_allowed=["motoshop"],
            source="supabase",
        ),
        "other_moto_user": User(
            username="other_moto_user",
            hashed_password=hash_password("moto456"),
            email="other-moto@test.com",
            role="gerente",
            tenants_allowed=["motoshop"],
            source="supabase",
        ),
        "vital_user": User(
            username="vital_user",
            hashed_password=hash_password("vital123"),
            email="vital@test.com",
            role="gerente",
            tenants_allowed=["masvital"],
            source="supabase",
        ),
    }
    _users_cache.update(users)
    yield users
    _users_cache.clear()


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


# ── Generadores: binarios válidos ─────────────────────────────────────────────


def test_generate_excel_creates_valid_xlsx():
    data = ReportData(
        title="Reporte Ventas Test",
        subtitle="Período analizado: 2024-07-01 a 2026-06-30 (histórico completo)",
        tenant_name="MotoShop",
        brand_color="#7B1818",
        columns=["SKU", "Producto", "Total"],
        rows=[["SKU-1", "Batería", 150000.0], ["SKU-2", "Aceite", 45000.0]],
        summary_metrics={"Total": "$195.000 COP"},
    )
    raw = generate_excel(data)
    assert len(raw) > 1000
    import zipfile

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert "xl/workbook.xml" in zf.namelist()


def test_generate_pdf_creates_valid_pdf():
    data = ReportData(
        title="Reporte Ventas Test",
        subtitle="Período analizado: 2026-06-01 a 2026-06-30 (últimos 30 días)",
        tenant_name="MasVital",
        brand_color="#16A34A",
        columns=["SKU", "Producto", "Total"],
        rows=[["SKU-1", "Kefir", 25000.0]],
    )
    raw = generate_pdf(data)
    assert raw.startswith(b"%PDF")
    assert len(raw) > 500


def test_generate_word_creates_valid_docx():
    data = ReportData(
        title="Reporte Word Test",
        subtitle="Foto al corte 2026-06-30 (sin ventana temporal)",
        tenant_name="MotoShop",
        columns=["SKU", "Producto", "Stock"],
        rows=[["SKU-1", "Pastillas", 12]],
    )
    raw = generate_word(data)
    assert len(raw) > 1000
    import zipfile

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert "word/document.xml" in zf.namelist()


# ── Storage: aislamiento persistente y sweeper ────────────────────────────────


def test_storage_recover_tenant_from_filename(tmp_path):
    """Tras un reinicio (índice perdido), el tenant se recupera del nombre de archivo."""
    storage = ReportStorage(base_dir=tmp_path)
    rec = storage.save_report(b"data", "reporte.xlsx", "application/pdf", "motoshop", "u1")
    report_id = rec.report_id

    # Simular reinicio: nueva instancia, mismo directorio
    storage2 = ReportStorage(base_dir=tmp_path)
    recovered = storage2.get_report(report_id)
    assert recovered is not None
    assert recovered.tenant == "motoshop"


def test_storage_rejects_glob_injection(tmp_path):
    storage = ReportStorage(base_dir=tmp_path)
    storage.save_report(b"data", "reporte.xlsx", "application/pdf", "motoshop", "u1")
    assert storage.get_report("rep_*") is None
    assert storage.get_report("../../etc/passwd") is None
    assert storage.get_report("rep_abcdefghijkl!") is None


def test_storage_sweeper_removes_expired_files(tmp_path):
    storage = ReportStorage(base_dir=tmp_path)
    rec = storage.save_report(b"data", "reporte_viejo.xlsx", "application/pdf", "motoshop", "u1")
    # Simular que el archivo tiene más de 24h
    old = time.time() - (86400 + 60)
    import os

    os.utime(rec.file_path, (old, old))

    removed = storage.sweep_expired_files()
    assert removed == 1
    assert not rec.file_path.exists()


def test_storage_does_not_serve_an_expired_indexed_report(tmp_path):
    storage = ReportStorage(base_dir=tmp_path)
    rec = storage.save_report(b"expired", "expired.xlsx", "application/pdf", "motoshop", "u1")
    old = time.time() - (86400 + 60)
    import os

    os.utime(rec.file_path, (old, old))

    assert storage.get_report(rec.report_id) is None


# ── Tool generate_report: ventanas de fecha ────────────────────────────────────


def test_tool_generate_report_custom_date_range():
    """El reclamo del usuario: 'desde julio de 2024 hasta la última fecha'."""
    executor = ToolExecutor(tenant="motoshop")
    result = executor.run(
        "generate_report",
        {
            "format": "excel",
            "report_type": "top_productos",
            "period": "custom",
            "date_from": "2024-07-01",
            "limit": 10,
        },
    )
    assert result["status"] == "success"
    assert result["date_from"] == "2024-07-01"
    assert result["date_to"]  # última fecha con datos
    assert "2024-07-01" in result["period_label"]
    assert result["download_url"].startswith("/api/reports/download/")
    assert result["expires_at"]


def test_tool_generate_report_period_all():
    executor = ToolExecutor(tenant="motoshop")
    result = executor.run(
        "generate_report",
        {"format": "pdf", "report_type": "top_productos", "period": "all", "limit": 5},
    )
    assert result["status"] == "success"
    assert "histórico completo" in result["period_label"]


def test_tool_generate_report_rejects_inverted_range():
    executor = ToolExecutor(tenant="motoshop")
    result = executor.run(
        "generate_report",
        {"format": "excel", "period": "custom", "date_from": "2026-01-01", "date_to": "2024-01-01"},
    )
    assert "error" in result
    assert "no puede ser posterior" in result["error"]


def test_tool_generate_report_rejects_bad_date():
    executor = ToolExecutor(tenant="motoshop")
    result = executor.run(
        "generate_report", {"format": "excel", "period": "custom", "date_from": "julio-2024"}
    )
    assert "error" in result


def test_tool_generate_report_custom_requires_date_from():
    executor = ToolExecutor(tenant="motoshop")
    result = executor.run("generate_report", {"format": "excel", "period": "custom"})
    assert "error" in result
    assert "date_from" in result["error"]


def test_tool_executor_generate_report_all_formats():
    executor = ToolExecutor(tenant="motoshop")
    for fmt in ["excel", "pdf", "word"]:
        result = executor.run(
            "generate_report", {"format": fmt, "report_type": "top_productos", "limit": 5}
        )
        assert result["status"] == "success"
        assert result["format"] == fmt
        assert result["download_url"].startswith("/api/reports/download/")
        assert result["records_count"] > 0
        assert result["date_from"] and result["date_to"]


def test_purchase_tools_are_not_registered_for_active_tenant():
    executor = ToolExecutor(tenant="motoshop")
    assert executor.run("get_ultima_compra", {}) == {"error": "Tool not allowed for this tenant"}
    assert executor.run("get_compras_recientes", {}) == {
        "error": "Tool not allowed for this tenant"
    }


# ── Endpoint de descarga: autenticación y aislamiento por tenant ──────────────


def _save_report(tmp_path, monkeypatch, tenant="motoshop", user_id="moto_user"):
    storage = ReportStorage(base_dir=tmp_path)
    monkeypatch.setattr("motoshop_api.reports.router.get_report_storage", lambda: storage)
    return storage.save_report(
        b"dummy content for report",
        "reporte_test.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        tenant,
        user_id,
    )


def test_download_requires_token(tmp_path, monkeypatch, tenant_users):
    rec = _save_report(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get(f"/api/reports/download/{rec.report_id}")
    assert resp.status_code == 401


def test_download_rejects_invalid_token(tmp_path, monkeypatch, tenant_users):
    rec = _save_report(tmp_path, monkeypatch)
    client = TestClient(app)
    resp = client.get(
        f"/api/reports/download/{rec.report_id}", headers={"Authorization": "Bearer no-es-un-jwt"}
    )
    assert resp.status_code == 401


def test_download_owner_tenant_succeeds(tmp_path, monkeypatch, tenant_users):
    rec = _save_report(tmp_path, monkeypatch, tenant="motoshop")
    client = TestClient(app)
    token = _login(client, "moto_user", "moto123")
    resp = client.get(
        f"/api/reports/download/{rec.report_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert "reporte_test.xlsx" in resp.headers.get("content-disposition", "")
    assert resp.content == b"dummy content for report"


def test_download_cross_tenant_forbidden(tmp_path, monkeypatch, tenant_users):
    """Usuario de MasVital NO puede descargar un reporte de MotoShop."""
    rec = _save_report(tmp_path, monkeypatch, tenant="motoshop")
    client = TestClient(app)
    token = _login(client, "vital_user", "vital123")
    resp = client.get(
        f"/api/reports/download/{rec.report_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403


def test_download_same_tenant_different_user_forbidden(tmp_path, monkeypatch, tenant_users):
    rec = _save_report(tmp_path, monkeypatch, tenant="motoshop")
    client = TestClient(app)
    token = _login(client, "other_moto_user", "moto456")
    resp = client.get(
        f"/api/reports/download/{rec.report_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert resp.headers["content-type"] == "application/problem+json"


def test_download_with_query_token(tmp_path, monkeypatch, tenant_users):
    """El fallback ?token= (descarga directa en navegador) también funciona."""
    rec = _save_report(tmp_path, monkeypatch, tenant="masvital", user_id="vital_user")
    client = TestClient(app)
    token = _login(client, "vital_user", "vital123")
    resp = client.get(f"/api/reports/download/{rec.report_id}?token={token}")
    assert resp.status_code == 200
    assert resp.content == b"dummy content for report"


def test_download_missing_report_404(tmp_path, monkeypatch, tenant_users):
    client = TestClient(app)
    token = _login(client, "moto_user", "moto123")
    resp = client.get(
        "/api/reports/download/rep_000000000000", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404
