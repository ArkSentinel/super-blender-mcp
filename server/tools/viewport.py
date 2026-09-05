"""Viewport screenshot — fix Bug #189 GPUOffScreen."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers.connection import send_to_supermcp


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        annotations=ToolAnnotations(title="Viewport Screenshot (SuperMCP)", readOnlyHint=True),
    )
    def get_viewport_screenshot(max_size: int = 800, filepath: str = "/tmp/supermcp_viewport.png", format: str = "png") -> dict:
        """
        Screenshot of 3D viewport via GPUOffScreen (fix Bug #189 — black when window not foreground).
        Falls back to window grab if GPU unavailable. Returns {success, width, height, filepath, method}.
        """
        resp = send_to_supermcp({
            "type": "get_viewport_screenshot",
            "params": {"max_size": max_size, "filepath": filepath, "format": format},
        })
        if resp.get("status") in ("success", "ok"):
            return resp.get("result", resp)
        return resp
