"""Godot pipeline tools — validate + export glb with auto-cure."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers.connection import send_to_supermcp


from server.tools_helpers import unwrap_response as _unwrap


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        annotations=ToolAnnotations(title="Validate Scene for Godot", readOnlyHint=True),
    )
    def godot_validate_scene(only_selected: bool = False) -> dict:
        """
        Validate scene for Godot 4.x glTF export. Gate before godot_export_glb.

        Checks: scale !=1, ngons, missing UV, missing images, degenerate faces, armature scale.
        Returns {can_export, errors[], warnings[], infos[], mesh_count}.
        If can_export is false, fix errors before exporting. Warnings are auto-fixed by cure on export.
        """
        return _unwrap(send_to_supermcp({"type": "godot_validate_scene", "params": {"only_selected": only_selected}}))

    @mcp.tool(
        annotations=ToolAnnotations(title="Export GLB for Godot (auto-cure)", destructiveHint=False),
    )
    def godot_export_glb(
        filepath: str,
        export_format: str = "GLB",
        use_selection: bool = False,
        use_visible: bool = False,
        export_apply: bool = True,
        export_yup: bool = True,
        export_animations: bool = True,
        auto_cure: bool = True,
        cure_merge_distance: float = 0.0001,
        cure_recalc_outside: bool = True,
    ) -> dict:
        """
        Export to glTF 2.0 (.glb) for Godot 4.x with automatic curing before export.

        Pipeline when auto_cure=true (default):
          1. cure_scene (apply transforms → merge by distance → recalc normals) on targets
          2. godot_validate_scene (post-cure)
          3. bpy.ops.export_scene.gltf (GLB, Y-up, tangents, materials, skins)

        Set auto_cure=false to export raw (not recommended — Godot will show scale/normal artifacts).
        cure_merge_distance default 0.0001 (0.1mm at 1 unit=1m).

        Args:
          filepath: absolute path like /tmp/model.glb or /home/user/exports/prop.glb
          export_format: GLB (single file, recommended) or GLTF_SEPARATE / GLTF_EMBEDDED
          use_selection: only export selected objects
          auto_cure: run cure pipeline before export (recommended)

        Returns {success, filepath, file_size_bytes, cure_report, validation}.
        """
        return _unwrap(send_to_supermcp({
            "type": "godot_export_glb",
            "params": {
                "filepath": filepath,
                "export_format": export_format,
                "use_selection": use_selection,
                "use_visible": use_visible,
                "export_apply": export_apply,
                "export_yup": export_yup,
                "export_animations": export_animations,
                "auto_cure": auto_cure,
                "cure_merge_distance": cure_merge_distance,
                "cure_recalc_outside": cure_recalc_outside,
            },
        }))

    @mcp.tool(
        annotations=ToolAnnotations(title="Godot Export Info", readOnlyHint=True),
    )
    def get_godot_export_info() -> dict:
        """Info about SuperMCP Godot pipeline: ports, curing steps, formats."""
        return _unwrap(send_to_supermcp({"type": "get_godot_export_info", "params": {}}))

    @mcp.tool(
        annotations=ToolAnnotations(title="Get Scene Info (SuperMCP)", readOnlyHint=True),
    )
    def get_scene_info() -> dict:
        """List objects in current Blender scene (via SuperMCP port 9877)."""
        return _unwrap(send_to_supermcp({"type": "get_scene_info", "params": {}}))

    @mcp.tool(
        annotations=ToolAnnotations(title="Get Object Info (SuperMCP)", readOnlyHint=True),
    )
    def get_object_info(name: str) -> dict:
        """Details for one object, including curing hints (needs_apply_transforms, ngon_count)."""
        return _unwrap(send_to_supermcp({"type": "get_object_info", "params": {"name": name}}))

    @mcp.tool(
        annotations=ToolAnnotations(title="Execute Blender Code (SuperMCP)", destructiveHint=True),
    )
    def execute_blender_code(code: str) -> dict:
        """
        Execute arbitrary Blender Python (bpy, bmesh, mathutils) on SuperMCP port 9877.

        Assign result variable for return. Separate from Free's execute on 9876.
        """
        # Use raw execute framing
        from server.tools_helpers.connection import send_code
        return send_code(code, strict_json=False)
