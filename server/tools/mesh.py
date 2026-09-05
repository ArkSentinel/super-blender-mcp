"""Fase 2 — Mesh Advanced: bmesh ops + validate."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers.connection import send_to_supermcp


def _unwrap(resp: dict) -> dict:
    if resp.get("status") in ("success", "ok"):
        return resp.get("result", resp)
    return resp


def register(mcp: FastMCP) -> None:

    @mcp.tool(annotations=ToolAnnotations(title="Mesh Operation (bmesh)", destructiveHint=True))
    def mesh_operation(object_name: str, operation: str, params: dict | None = None) -> dict:
        """
        bmesh operation on a mesh. operation: subdivide (params {cuts}), bevel ({offset, segments}), triangulate, decimate ({angle_limit}), merge_by_distance ({distance}), recalc_normals.
        """
        return _unwrap(send_to_supermcp({"type": "mesh_operation", "params": {"object_name": object_name, "operation": operation, "params": params or {}}}))

    @mcp.tool(annotations=ToolAnnotations(title="Validate Mesh", readOnlyHint=True))
    def validate_mesh(object_name: str) -> dict:
        """Stats for mesh: ngons/tris/quads, degenerate, UV, scale. Returns needs_cure flag."""
        return _unwrap(send_to_supermcp({"type": "validate_mesh", "params": {"object_name": object_name}}))
