"""Fase 6 — IO 9 formatos (3 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Import File (9 formats)"))
    def io_import_file(filepath: str, format: str = "AUTO") -> dict:
        """AUTO detects .fbx/.gltf/.glb/.obj/.stl/.ply/.dae/.abc/.usd/.blend."""
        return _u(send_to_supermcp({"type":"io_import_file","params":{"filepath":filepath,"format":format}}))

    @mcp.tool(annotations=ToolAnnotations(title="Export File (9 formats)"))
    def io_export_file(filepath: str, format: str = "GLB", use_selection: bool = False) -> dict:
        """Formats: GLB, FBX, OBJ, STL, PLY, DAE, ABC, USD."""
        return _u(send_to_supermcp({"type":"io_export_file","params":{"filepath":filepath,"format":format,"use_selection":use_selection}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Supported Formats", readOnlyHint=True))
    def io_list_formats() -> dict:
        return _u(send_to_supermcp({"type":"io_list_formats","params":{}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get Import Options", readOnlyHint=True))
    def io_get_import_options(format: str = "FBX") -> dict:
        return _u(send_to_supermcp({"type":"io_get_import_options","params":{"format":format}}))
