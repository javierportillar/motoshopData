from pathlib import Path

import duckdb
import pytest
import yaml

from motoshop_api.llm.tools import ToolExecutor
from motoshop_api.tenants import load_tenants


@pytest.fixture
def tenant_fixtures(tmp_path: Path):
    config = {
        "tenants": [
            {
                "id": tenant,
                "nombre": tenant,
                "r2_object_key": f"{tenant}.duckdb",
                "local_db_path": str(tmp_path / f"{tenant}.duckdb"),
                "agent": {"enabled_tools": ["get_kpis_today"]},
            }
            for tenant in ("motoshop", "masvital")
        ]
    }
    config_path = tmp_path / "tenants.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    load_tenants(config_path)
    for tenant in config["tenants"]:
        database = Path(tenant["local_db_path"])
        with duckdb.connect(str(database)) as connection:
            connection.execute("CREATE TABLE marker (tenant VARCHAR)")
            connection.execute("INSERT INTO marker VALUES (?)", [tenant["id"]])
    yield tmp_path
    load_tenants(Path(__file__).parents[1] / "tenants.yaml")


def test_active_tenant_fixtures_do_not_register_purchase_tools(tenant_fixtures: Path) -> None:
    for tenant in ("motoshop", "masvital"):
        executor = ToolExecutor(
            tenant=tenant, duckdb_path=str(tenant_fixtures / f"{tenant}.duckdb")
        )
        assert executor.run("get_ultima_compra", {}) == {
            "error": "Tool not allowed for this tenant"
        }


def test_fixture_database_is_not_shared_between_tenants(tenant_fixtures: Path) -> None:
    moto = ToolExecutor(tenant="motoshop", duckdb_path=str(tenant_fixtures / "motoshop.duckdb"))
    vital = ToolExecutor(tenant="masvital", duckdb_path=str(tenant_fixtures / "masvital.duckdb"))

    assert moto._con.execute("SELECT tenant FROM marker").fetchone() == ("motoshop",)
    assert vital._con.execute("SELECT tenant FROM marker").fetchone() == ("masvital",)
