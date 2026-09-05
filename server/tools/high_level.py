"""Insights Free — Tools nativas de alto nivel + traceback estructurado."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Reset Scene Clean", destructiveHint=True))
    def reset_scene_clean() -> dict:
        """Limpia mallas/materiales/texturas sin read_factory_settings (sandbox-safe)."""
        return _u(send_to_supermcp({"type":"reset_scene_clean","params":{}}))

    @mcp.tool(annotations=ToolAnnotations(title="Auto Frame Camera"))
    def auto_frame_camera(camera_name: str = "", target_objects: list = None, margin: float = 1.2) -> dict:
        """Calcula AABB y posiciona cámara en ángulo ideal antes de captura. Usa temp_override."""
        params = {"camera_name": camera_name, "margin": margin}
        if target_objects:
            params["target_objects"] = target_objects
        return _u(send_to_supermcp({"type":"auto_frame_camera","params":params}))

    @mcp.tool(annotations=ToolAnnotations(title="Render Object Preview"))
    def render_object_preview(object_name: str = "", filepath: str = "/tmp/supermcp_preview.png", resolution: int = 512, margin: float = 1.2) -> dict:
        """Renderiza miniatura de objeto en 1 paso: auto_frame + render EEVEE."""
        return _u(send_to_supermcp({"type":"render_object_preview","params":{"object_name":object_name,"filepath":filepath,"resolution":resolution,"margin":margin}}))

    @mcp.tool(annotations=ToolAnnotations(title="Export Godot GLB (high-level)", destructiveHint=False))
    def export_godot_glb(filepath: str = "/tmp/export_godot.glb", use_selection: bool = False, auto_cure: bool = True, compression: bool = False) -> dict:
        """Alias PBR-compat de godot_export_glb con compresión opcional para Godot/Redot."""
        return _u(send_to_supermcp({"type":"export_godot_glb","params":{"filepath":filepath,"use_selection":use_selection,"auto_cure":auto_cure,"compression":compression}}))
