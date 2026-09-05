"""Fase 2 — Modifier Stack (22 tipos) + Move/Apply."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers.connection import send_to_supermcp


def _unwrap(resp: dict) -> dict:
    if resp.get("status") in ("success", "ok"):
        return resp.get("result", resp)
    return resp


def register(mcp: FastMCP) -> None:

    @mcp.tool(annotations=ToolAnnotations(title="Add Modifier", destructiveHint=False))
    def add_modifier(object_name: str, modifier_type: str, name: str = "", params: dict | None = None) -> dict:
        """
        Add a modifier to a mesh. modifier_type: subsurf, bevel, boolean, array, mirror, solidify, decimate, remesh, weld, triangulate, shrinkwrap, weighted_normal, etc. Handles 22 types.
        params example: {"levels":2, "render_levels":3} for Subsurf, {"operation":"DIFFERENCE"} for Boolean, {"segments":3} for Bevel.
        """
        return _unwrap(send_to_supermcp({"type": "add_modifier", "params": {"object_name": object_name, "modifier_type": modifier_type, "name": name, "params": params or {}}}))

    @mcp.tool(annotations=ToolAnnotations(title="Remove Modifier", destructiveHint=True))
    def remove_modifier(object_name: str, modifier_name: str) -> dict:
        """Remove a modifier by name."""
        return _unwrap(send_to_supermcp({"type": "remove_modifier", "params": {"object_name": object_name, "modifier_name": modifier_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Modifier Params", destructiveHint=False))
    def set_modifier_params(object_name: str, modifier_name: str, params: dict) -> dict:
        """Update params on an existing modifier. Returns applied/failed."""
        return _unwrap(send_to_supermcp({"type": "set_modifier_params", "params": {"object_name": object_name, "modifier_name": modifier_name, "params": params}}))

    @mcp.tool(annotations=ToolAnnotations(title="Move Modifier", destructiveHint=False))
    def move_modifier(object_name: str, modifier_name: str, index: int) -> dict:
        """Reorder modifier stack to target index."""
        return _unwrap(send_to_supermcp({"type": "move_modifier", "params": {"object_name": object_name, "modifier_name": modifier_name, "index": index}}))

    @mcp.tool(annotations=ToolAnnotations(title="Apply Modifier", destructiveHint=True))
    def apply_modifier(object_name: str, modifier_name: str) -> dict:
        """Apply (bake) a modifier destructively."""
        return _unwrap(send_to_supermcp({"type": "apply_modifier", "params": {"object_name": object_name, "modifier_name": modifier_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Modifiers", readOnlyHint=True))
    def list_modifiers(object_name: str) -> dict:
        """List all modifiers on an object with index/type/visibility."""
        return _unwrap(send_to_supermcp({"type": "list_modifiers", "params": {"object_name": object_name}}))
