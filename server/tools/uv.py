"""Fase 3 — UV Tools (6 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _unwrap

def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="UV Unwrap"))
    def uv_unwrap(object_name: str, method: str = "SMART_PROJECT", margin: float = 0.02) -> dict:
        """Unwrap UV: SMART_PROJECT, CUBE_PROJECT, UNWRAP."""
        return _unwrap(send_to_supermcp({"type":"uv_unwrap","params":{"object_name":object_name,"method":method,"margin":margin}}))

    @mcp.tool(annotations=ToolAnnotations(title="UV Add Layer"))
    def uv_add_layer(object_name: str, layer_name: str = "UVMap") -> dict:
        return _unwrap(send_to_supermcp({"type":"uv_add_layer","params":{"object_name":object_name,"layer_name":layer_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="UV Pack Islands"))
    def uv_pack_islands(object_name: str, margin: float = 0.02) -> dict:
        return _unwrap(send_to_supermcp({"type":"uv_pack_islands","params":{"object_name":object_name,"margin":margin}}))

    @mcp.tool(annotations=ToolAnnotations(title="UV Get Info", readOnlyHint=True))
    def uv_get_info(object_name: str) -> dict:
        return _unwrap(send_to_supermcp({"type":"uv_get_info","params":{"object_name":object_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="UV Export Layout"))
    def uv_export_layout(object_name: str, filepath: str = "/tmp/uv_layout.png", size: int = 1024) -> dict:
        return _unwrap(send_to_supermcp({"type":"uv_export_layout","params":{"object_name":object_name,"filepath":filepath,"size":size}}))

    @mcp.tool(annotations=ToolAnnotations(title="UV Validate", readOnlyHint=True))
    def uv_validate(object_name: str) -> dict:
        return _unwrap(send_to_supermcp({"type":"uv_validate","params":{"object_name":object_name}}))
