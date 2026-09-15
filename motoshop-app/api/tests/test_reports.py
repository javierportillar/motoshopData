"""Tests unitarios y de integración para la generación y descarga de reportes."""

from __future__ import annotations

import io
from fastapi.testclient import TestClient

from motoshop_api.main import app
from motoshop_api.reports.generator import (
    ReportData,
    generate_excel,
    generate_pdf,
    generate_word,
)
from motoshop_api.reports.storage import ReportStorage
from motoshop_api.llm.tools import ToolExecutor


def test_generate_excel_creates_valid_xlsx():
    data = ReportData(
        title="Reporte Ventas Test",
        subtitle="Al corte 2026-06-30",
        tenant_name="MotoShop",
        brand_color="#7B1818",
        columns=["SKU", "Producto", "Total"],
        rows=[["SKU-1", "Batería", 150000.0], ["SKU-2", "Aceite", 45000.0]],
        summary_metrics={"Total": "$195.000 COP"},
    )
    raw = generate_excel(data)
    assert len(raw) > 1000
    # Valida que es un zip/xlsx válido
    import zipfile
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert "xl/workbook.xml" in zf.namelist()


def test_generate_pdf_creates_valid_pdf():
    data = ReportData(
        title="Reporte Ventas Test",
        subtitle="Al corte 2026-06-30",
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
        subtitle="Al corte 2026-06-30",
        tenant_name="MotoShop",
        columns=["SKU", "Producto", "Stock"],
        rows=[["SKU-1", "Pastillas", 12]],
    )
    raw = generate_word(data)
    assert len(raw) > 1000
    import zipfile
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        assert "word/document.xml" in zf.namelist()


def test_storage_and_download_endpoint(tmp_path, monkeypatch):
    storage = ReportStorage(base_dir=tmp_path)
    monkeypatch.setattr("motoshop_api.reports.router.get_report_storage", lambda: storage)
    rec = storage.save_report(
        b"dummy content for report",
        "reporte_test.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "motoshop",
        "admin",
    )
    assert rec.report_id.startswith("rep_")
    assert rec.download_url == f"/api/reports/download/{rec.report_id}"

    client = TestClient(app)
    resp = client.get(f"/api/reports/download/{rec.report_id}")
    assert resp.status_code == 200
    assert "reporte_test.xlsx" in resp.headers.get("content-disposition", "")
    assert resp.content == b"dummy content for report"


def test_tool_executor_generate_report_all_formats():
    executor = ToolExecutor(tenant="motoshop")
    for fmt in ["excel", "pdf", "word"]:
        result = executor.run("generate_report", {"format": fmt, "report_type": "top_productos", "limit": 5})
        assert result["status"] == "success"
        assert result["format"] == fmt
        assert result["download_url"].startswith("/api/reports/download/")
        assert result["records_count"] > 0
