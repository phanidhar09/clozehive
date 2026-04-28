"""
Shared health-check helper for all MCP servers.
Adds a /health HTTP endpoint alongside the SSE transport.
"""

from __future__ import annotations

from datetime import UTC, datetime


def health_payload(service_name: str, tools: list[str], version: str = "2.0.0") -> dict:
    return {
        "status": "ok",
        "service": service_name,
        "version": version,
        "tools": tools,
        "timestamp": datetime.now(UTC).isoformat(),
    }
