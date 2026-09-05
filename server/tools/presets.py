"""Fase 6 — Presets 4 + Godot Polish 4."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

def _u(r): return r.get("result",r) if r.get("status") in ("success","ok") else r

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Apply Preset"))
    def preset_apply(preset: str = "studio_lighting") -> dict:
        """Presets: studio_lighting, turntable, character_base."""
        return _u(send_to_supermcp({"type":"preset_apply","params":{"preset":preset}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Presets", readOnlyHint=True))
    def preset_list() -> dict:
        return _u(send_to_supermcp({"type":"preset_list","params":{}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create Preset from Scene"))
    def preset_create_from_scene(preset_name: str = "MyPreset") -> dict:
        return _u(send_to_supermcp({"type":"preset_create_from_scene","params":{"preset_name":preset_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get AI Hint", readOnlyHint=True))
    def preset_get_hint(context: str = "modeling") -> dict:
        """Contexts: modeling, texturing, rigging, export."""
        return _u(send_to_supermcp({"type":"preset_get_hint","params":{"context":context}}))

    @mcp.tool(annotations=ToolAnnotations(title="Godot Setup Collision"))
    def godot_setup_collision(object_name: str, collision_type: str = "-colonly") -> dict:
        """collision_type: -col, -convcol, -colonly, -convcolonly. Duplicates mesh as Godot collision via suffix."""
        return _u(send_to_supermcp({"type":"godot_setup_collision","params":{"object_name":object_name,"collision_type":collision_type}}))

    @mcp.tool(annotations=ToolAnnotations(title="Godot Setup LOD"))
    def godot_setup_lod(object_name: str, levels: list = [0.5,0.25]) -> dict:
        return _u(send_to_supermcp({"type":"godot_setup_lod","params":{"object_name":object_name,"levels":levels}}))

    @mcp.tool(annotations=ToolAnnotations(title="Godot Material Compatibility", readOnlyHint=True))
    def godot_check_material_compatibility(object_name: str = "") -> dict:
        """Empty object_name checks all meshes."""
        return _u(send_to_supermcp({"type":"godot_check_material_compatibility","params":{"object_name":object_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Godot Batch Export"))
    def godot_batch_export(directory: str = "/tmp/godot_batch", export_format: str = "GLB") -> dict:
        return _u(send_to_supermcp({"type":"godot_batch_export","params":{"directory":directory,"export_format":export_format}}))
