"""
MCP server exposing EKS log tools to OpenWebUI over Streamable HTTP.
Requires OpenWebUI >= v0.6.31 (native MCP / Streamable HTTP support).
Run with: python mcp_server.py
"""
from mcp.server.fastmcp import FastMCP

import log_service

mcp = FastMCP("eks-log-server", host="0.0.0.0", port=8001)


@mcp.tool()
def list_namespaces() -> list[str]:
    """List namespaces available for log monitoring."""
    return log_service.NAMESPACE_ALLOWLIST


@mcp.tool()
def list_pods(namespace: str) -> list[str]:
    """List pod names discoverable inside a single allow-listed namespace."""
    return log_service.list_pods(namespace)


@mcp.tool()
def get_namespace_logs(namespace: str, minutes: int = 60) -> dict:
    """Fetch recent logs for every pod inside a namespace ("system")."""
    return log_service.get_namespace_logs(namespace, minutes)


@mcp.tool()
def get_pod_logs(namespace: str, service: str, minutes: int = 60) -> dict:
    """Fetch recent logs for one specific service inside a namespace."""
    return log_service.get_pod_logs(namespace, service, minutes)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
