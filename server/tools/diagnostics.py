"""Fase 6 — Diagnostics (4) + Scene Utils (4)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Check Rig Health", readOnlyHint=True))
    def diag_check_rig_health(armature_name: str) -> dict:
        return _u(send_to_supermcp({"type":"diag_check_rig_health","params":{"armature_name":armature_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Validate Armature", readOnlyHint=True))
    def diag_validate_armature(armature_name: str) -> dict:
        return _u(send_to_supermcp({"type":"diag_validate_armature","params":{"armature_name":armature_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Fix Rig Issues"))
    def diag_fix_rig(armature_name: str) -> dict:
        return _u(send_to_supermcp({"type":"diag_fix_rig","params":{"armature_name":armature_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get Rig Report", readOnlyHint=True))
    def diag_get_rig_report(armature_name: str) -> dict:
        return _u(send_to_supermcp({"type":"diag_get_rig_report","params":{"armature_name":armature_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Clean Scene (purge)"))
    def scene_clean(purge_unused: bool = True) -> dict:
        return _u(send_to_supermcp({"type":"scene_clean","params":{"purge_unused":purge_unused}}))

    @mcp.tool(annotations=ToolAnnotations(title="Organize Collections"))
    def scene_organize_collections(prefix: str = "GEO_") -> dict:
        return _u(send_to_supermcp({"type":"scene_organize_collections","params":{"prefix":prefix}}))

    @mcp.tool(annotations=ToolAnnotations(title="Merge Blend File"))
    def scene_merge(blend_filepath: str, link: bool = False) -> dict:
        return _u(send_to_supermcp({"type":"scene_merge","params":{"blend_filepath":blend_filepath,"link":link}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get Scene Stats", readOnlyHint=True))
    def scene_get_stats() -> dict:
        return _u(send_to_supermcp({"type":"scene_get_stats","params":{}}))
