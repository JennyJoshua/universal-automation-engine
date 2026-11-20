"""Verify structured-data capabilities through REST and MCP."""

import asyncio

from fastapi.testclient import TestClient
from mcp import Client

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.api import create_app
from universal_automation.interfaces.mcp import MCPAdapter
from universal_automation.modules.data import StructuredDataModule
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal

API_KEY = "structured-data-integration-" + ("x" * 32)


def make_shared_engine(workspace):
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module = StructuredDataModule(workspace)
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="structured-data-integration-user",
        permissions={"files.read", "data.create", "data.transform"},
    )
    return registry, executor, principal


def test_structured_data_is_discoverable_and_executable_via_rest_and_mcp(tmp_path):
    (tmp_path / "people.csv").write_text("name,age\nAri,12\n", encoding="utf-8")
    registry, executor, principal = make_shared_engine(tmp_path)
    rest = TestClient(create_app(registry, executor, {API_KEY: principal}))
    headers = {"X-API-Key": API_KEY}

    listed = rest.get("/v1/capabilities", headers=headers)
    assert listed.status_code == 200
    names = {
        item["capability"]["name"]
        for item in listed.json()
        if item["plugin_id"] == StructuredDataModule.plugin_id
    }
    assert {"read_csv", "write_csv", "read_json", "write_json", "transform_records"} <= names

    response = rest.post(
        "/v1/executions",
        headers=headers,
        json={
            "request_id": "rest-data-read",
            "plugin_id": StructuredDataModule.plugin_id,
            "capability_name": "read_csv",
            "input_data": {"path": "people.csv"},
        },
    )
    assert response.status_code == 200
    assert response.json()["output_data"]["records"] == [{"name": "Ari", "age": "12"}]

    adapter = MCPAdapter(registry, executor, local_principal=principal)

    async def scenario():
        async with Client(adapter._server) as client:
            tools = await client.list_tools()
            tool = next(item for item in tools.tools if item.name.endswith("_read_csv"))
            result = await client.call_tool(tool.name, {"path": "people.csv"})
        assert result.is_error is False
        assert result.structured_content["records"] == [{"name": "Ari", "age": "12"}]

    asyncio.run(scenario())
