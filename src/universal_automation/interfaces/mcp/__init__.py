"""MCP integration for Universal Automation Engine."""

from universal_automation.interfaces.mcp.server import (
    MCPAdapter,
    MCPAdapterError,
    MCPAuthenticationError,
    principal_from_access_token,
)

__all__ = [
    "MCPAdapter",
    "MCPAdapterError",
    "MCPAuthenticationError",
    "principal_from_access_token",
]
