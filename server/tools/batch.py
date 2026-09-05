"""Fase 6 — Batch (4 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Batch Execute on Objects"))
    def batch_execute_on_objects(code: str, only_selected: bool = False) -> dict:
        """Execute code with `obj` var on each object."""
        return _u(send_to_supermcp({"type":"batch_execute_on_objects","params":{"code":code,"only_selected":only_selected}}))

    @mcp.tool(annotations=ToolAnnotations(title="Batch Render Queue"))
    def batch_render_queue(filepaths: list | None = None) -> dict:
        if filepaths is None:
            filepaths = []
        return _u(send_to_supermcp({"type":"batch_render_queue","params":{"filepaths":filepaths}}))

    @mcp.tool(annotations=ToolAnnotations(title="Batch Import"))
    def batch_import(directory: str, pattern: str = "*.fbx") -> dict:
        """Import all files matching pattern from directory (fbx, gltf, obj, stl, etc)."""
        return _u(send_to_supermcp({"type":"batch_import","params":{"directory":directory,"pattern":pattern}}))

    @mcp.tool(annotations=ToolAnnotations(title="Batch Export"))
    def batch_export(directory: str = "/tmp/batch_export", export_format: str = "GLB", only_selected: bool = False) -> dict:
        """Export each MESH object as separate file."""
        return _u(send_to_supermcp({"type":"batch_export","params":{"directory":directory,"export_format":export_format,"only_selected":only_selected}}))

    @mcp.tool(annotations=ToolAnnotations(title="Batch Process Directory"))
    def batch_process_directory(directory: str, script_code: str = "") -> dict:
        """Process all .blend files in directory with script_code."""
        return _u(send_to_supermcp({"type":"batch_process_directory","params":{"directory":directory,"script_code":script_code}}))
