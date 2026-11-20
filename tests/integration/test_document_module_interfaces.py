"""End-to-end tests for document creation through REST and MCP."""

import asyncio
import json

from fastapi.testclient import TestClient
from mcp import Client

from universal_automation.core.execution import CapabilityExecutor
from universal_automation.core.registry import PluginRegistry
from universal_automation.interfaces.api import create_app
from universal_automation.interfaces.mcp import MCPAdapter
from universal_automation.modules.documents import DocumentAutomationModule
from universal_automation.security import AuthorizationPolicy, ExecutionPrincipal

API_KEY = "document-module-integration-" + ("x" * 32)


def make_shared_engine(workspace):
    registry = PluginRegistry()
    executor = CapabilityExecutor(registry, AuthorizationPolicy())
    module = DocumentAutomationModule(workspace)
    module.register(registry, executor)
    principal = ExecutionPrincipal(
        subject_id="document-integration-user",
        permissions={"documents.create"},
    )
    return registry, executor, principal


def test_documents_are_discoverable_and_creatable_via_rest_and_mcp(tmp_path) -> None:
    registry, executor, principal = make_shared_engine(tmp_path)
    app = create_app(registry, executor, {API_KEY: principal})
    rest = TestClient(app)
    headers = {"X-API-Key": API_KEY}

    capabilities = rest.get("/v1/capabilities", headers=headers)
    assert capabilities.status_code == 200
    document_capabilities = [
        item for item in capabilities.json()
        if item["plugin_id"] == "uae.document-tools"
    ]
    assert len(document_capabilities) == 3

    rest_result = rest.post(
        "/v1/executions",
        headers=headers,
        json={
            "request_id": "rest-create-markdown",
            "plugin_id": "uae.document-tools",
            "capability_name": "create_markdown_document",
            "input_data": {
                "path": "rest-report.md",
                "title": "REST Report",
                "content": "Created through the REST API.",
            },
        },
    )
    assert rest_result.status_code == 200
    assert (tmp_path / "rest-report.md").read_text(encoding="utf-8") == (
        "# REST Report\n\nCreated through the REST API.\n"
    )

    mcp_adapter = MCPAdapter(registry, executor, local_principal=principal)

    async def mcp_scenario() -> None:
        async with Client(mcp_adapter._server) as client:
            tools = await client.list_tools()
            json_tool = next(
                tool for tool in tools.tools
                if tool.name.endswith("_create_json_document")
            )
            result = await client.call_tool(
                json_tool.name,
                {
                    "path": "mcp-result.json",
                    "data": {"status": "created", "count": 2},
                },
            )

        assert result.is_error is False
        assert result.structured_content["created"] is True

    asyncio.run(mcp_scenario())

    assert json.loads((tmp_path / "mcp-result.json").read_text(encoding="utf-8")) == {
        "status": "created",
        "count": 2,
    }


def test_document_overwrite_is_denied_through_rest_and_mcp(tmp_path) -> None:
    (tmp_path / "existing.txt").write_text("original", encoding="utf-8")
    registry, executor, principal = make_shared_engine(tmp_path)
    app = create_app(registry, executor, {API_KEY: principal})
    rest = TestClient(app)

    response = rest.post(
        "/v1/executions",
        headers={"X-API-Key": API_KEY},
        json={
            "request_id": "rest-overwrite",
            "plugin_id": "uae.document-tools",
            "capability_name": "create_text_document",
            "input_data": {"path": "existing.txt", "content": "replacement"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File already exists; overwriting is not supported"

    mcp_adapter = MCPAdapter(registry, executor, local_principal=principal)

    async def mcp_scenario() -> None:
        async with Client(mcp_adapter._server) as client:
            tools = await client.list_tools()
            text_tool = next(
                tool for tool in tools.tools
                if tool.name.endswith("_create_text_document")
            )
            result = await client.call_tool(
                text_tool.name,
                {"path": "existing.txt", "content": "replacement"},
            )

        assert result.is_error is True
        assert result.content[0].text == "File already exists; overwriting is not supported"

    asyncio.run(mcp_scenario())
    assert (tmp_path / "existing.txt").read_text(encoding="utf-8") == "original"
