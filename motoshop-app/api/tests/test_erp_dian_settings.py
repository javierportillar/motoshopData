"""Task 6.x tests: the DIAN provider configuration (operator onboarding).

- The default environment uses the STUB adapter: without a provider
  account the ERP keeps working exactly like the legacy desktop (the
  document is queued, the CUFE stays empty and the document is editable).
- A configured provider (base URL + credentials) selects the live adapter.
- The legacy QR URL is the official DIAN catalogue.
"""

from __future__ import annotations

import pytest

from motoshop_api.erp.dian.adapter import (
    DianStubAdapter,
    compute_pseudo_cufe,
    generate_qr_url,
)
from motoshop_api.erp.dian.live_adapters import DianDataicoAdapter
from motoshop_api.erp.dian.settings import (
    DianSettings,
    get_dian_adapter,
    get_dian_settings,
)


def test_default_environment_uses_the_stub(monkeypatch):
    for key in (
        "DIAN_PROVIDER",
        "DIAN_API_BASE",
        "DIAN_API_TOKEN",
        "DIAN_API_KEY",
        "DIAN_API_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = get_dian_settings()
    assert settings.provider == "stub"
    assert settings.is_live is False
    assert isinstance(get_dian_adapter(), DianStubAdapter)


def test_configured_provider_selects_the_live_adapter(monkeypatch):
    monkeypatch.setenv("DIAN_PROVIDER", "dataico")
    monkeypatch.setenv("DIAN_API_BASE", "https://api.dataico.com/direct/dataico_api/v2")
    monkeypatch.setenv("DIAN_API_TOKEN", "token-de-prueba")
    settings = get_dian_settings()
    assert settings.is_live is True
    assert settings.has_credentials is True
    adapter = get_dian_adapter()
    assert isinstance(adapter, DianDataicoAdapter)
    assert adapter.settings.api_base.endswith("/v2")


def test_provider_without_base_url_stays_on_the_stub(monkeypatch):
    monkeypatch.setenv("DIAN_PROVIDER", "dataico")
    monkeypatch.delenv("DIAN_API_BASE", raising=False)
    assert get_dian_settings().is_live is False
    assert isinstance(get_dian_adapter(), DianStubAdapter)


def test_dataico_endpoint_per_document_family():
    settings = DianSettings(
        provider="dataico",
        api_base="https://api.dataico.com/direct/dataico_api/v2",
        api_token="t",
    )
    adapter = DianDataicoAdapter(settings)
    assert adapter._endpoint({"family": "invoice"}).endswith("/invoices")
    assert adapter._endpoint({"family": "credit_note"}).endswith("/credit_notes")
    assert adapter._endpoint({"family": "support_doc"}).endswith("/support_docs")


def test_authorization_header_carries_the_token():
    settings = DianSettings(
        provider="dataico", api_base="https://x", api_token="tok", api_key="k"
    )
    headers = DianDataicoAdapter(settings)._headers()
    assert headers["Authorization"] == "Bearer tok"
    assert headers["X-Api-Key"] == "k"


def test_qr_url_is_the_official_dian_catalogue():
    assert generate_qr_url("CUFE-123") == (
        "https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey=CUFE-123"
    )


def test_pseudo_cufe_is_stable():
    first = compute_pseudo_cufe("501", "2026-03-10", "31350.90", "222222222222")
    second = compute_pseudo_cufe("501", "2026-03-10", "31350.90", "222222222222")
    assert first == second
    assert first
