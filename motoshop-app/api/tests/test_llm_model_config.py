from __future__ import annotations

from pathlib import Path

import yaml

from motoshop_api.config import Settings


def test_deepseek_flash_is_the_default_open_code_model(monkeypatch) -> None:
    monkeypatch.delenv("GO_MODEL", raising=False)

    settings = Settings(_env_file=None)

    assert settings.go_model == "deepseek-v4-flash"


def test_render_blueprint_uses_the_same_open_code_model() -> None:
    blueprint = yaml.safe_load(Path("render.yaml").read_text(encoding="utf-8"))
    service = next(item for item in blueprint["services"] if item["name"] == "motoshop-cloud-api")
    env_vars = {item["key"]: item.get("value") for item in service["envVars"]}

    assert env_vars["GO_MODEL"] == "deepseek-v4-flash"
