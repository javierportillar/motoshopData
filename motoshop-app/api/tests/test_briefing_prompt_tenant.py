"""Tenant identity contract for the real briefing prompt builder."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from motoshop_api.llm import client as client_module
from motoshop_api.llm.briefing import BriefingGenerator


class _CapturingClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def complete(self, prompt: str, *, system: str, **_kwargs) -> dict[str, object]:
        self.calls.append({"prompt": prompt, "system": system})
        return {
            "text": "Resumen sin cifras",
            "tokens_used": 4,
            "tokens_input": 3,
            "tokens_output": 1,
            "model": "test-model",
            "cost_usd": 0.0,
        }


def _empty_duckdb(path: Path) -> None:
    duckdb.connect(str(path)).close()


def test_real_prompt_uses_tenant_company_without_cross_branding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _CapturingClient()
    monkeypatch.setattr(client_module, "get_llm_client", lambda: client)

    for tenant, company in (("motoshop", "MotoShop"), ("masvital", "MasVital")):
        db_path = tmp_path / f"{tenant}.duckdb"
        _empty_duckdb(db_path)
        generator = BriefingGenerator(
            duckdb_path=str(db_path),
            tenant=tenant,
            company_name=company,
        )
        try:
            generator.generate({"fecha": "2026-07-20", "empresa": company})
        finally:
            generator.close()

    motoshop_system = client.calls[0]["system"]
    masvital_system = client.calls[1]["system"]
    assert "MotoShop" in motoshop_system
    assert "MasVital" in masvital_system
    assert "MotoShop" not in masvital_system
    assert "motopartes" not in masvital_system.lower()
