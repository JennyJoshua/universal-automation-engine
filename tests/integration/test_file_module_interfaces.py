"""End-to-end checks for file automation through REST and MCP interfaces."""

import asyncio

from fastapi.testclient import TestClient
from mcp import Client

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.api import create_app
from universal_automation.interfaces.mcp import MCPAdapter
from universal_automation.modules.files import FileAutomationModule
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal

API_KEY = "file-module-integration-" + ("x" * 32)


def make_shared_engine(workspace):
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module = FileAutomationModule(workspace)
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="integration-user",
        permissions={"files.read"},
    )
    return registry, executor, principal


def test_file_tools_are_discoverable_and_executable_via_rest_and_mcp(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("The universal engine works.", encoding="utf-8")
    registry, executor, principal = make_shared_engine(tmp_path)

    app = create_app(registry, executor, {API_KEY: principal})
    rest = TestClient(app)
    headers = {"X-API-Key": API_KEY}

    listed = rest.get("/v1/capabilities", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 3

    rest_result = rest.post(
        "/v1/executions",
        headers=headers,
        json={
            "request_id": "rest-file-read",
            "plugin_id": "uae.file-tools",
            "capability_name": "read_text_file",
            "input_data": {"path": "notes.txt"},
        },
    )
    assert rest_result.status_code == 200
    assert rest_result.json()["output_data"]["content"] == "The universal engine works."

    mcp_adapter = MCPAdapter(registry, executor, local_principal=principal)

    async def mcp_scenario() -> None:
        async with Client(mcp_adapter._server) as client:
            tools = await client.list_tools()
            read_tool = next(tool for tool in tools.tools if tool.name.endswith("_read_text_file"))
            result = await client.call_tool(read_tool.name, {"path": "notes.txt"})

        assert result.is_error is False
        assert result.structured_content["content"] == "The universal engine works."

    asyncio.run(mcp_scenario())


def test_file_path_errors_are_safe_through_rest_and_mcp(tmp_path) -> None:
    (tmp_path / "notes.txt").write_text("workspace content", encoding="utf-8")
    registry, executor, principal = make_shared_engine(tmp_path)

    app = create_app(registry, executor, {API_KEY: principal})
    rest = TestClient(app)
    response = rest.post(
        "/v1/executions",
        headers={"X-API-Key": API_KEY},
        json={
            "request_id": "rest-file-traversal",
            "plugin_id": "uae.file-tools",
            "capability_name": "read_text_file",
            "input_data": {"path": "../outside.txt"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Parent-directory traversal is not allowed"

    mcp_adapter = MCPAdapter(registry, executor, local_principal=principal)

    async def mcp_scenario() -> None:
        async with Client(mcp_adapter._server) as client:
            tools = await client.list_tools()
            read_tool = next(tool for tool in tools.tools if tool.name.endswith("_read_text_file"))
            result = await client.call_tool(read_tool.name, {"path": "../outside.txt"})

        assert result.is_error is True
        assert result.content[0].text == "Parent-directory traversal is not allowed"

    asyncio.run(mcp_scenario())
