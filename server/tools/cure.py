"""Cure tools — apply transforms + merge by distance + recalc normals."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers.connection import send_to_supermcp


def register(mcp: FastMCP) -> None:

    @mcp.tool(
        annotations=ToolAnnotations(title="Cure Single Model", destructiveHint=False),
    )
    def cure_model(
        name: str,
        merge_distance: float = 0.0001,
        recalc_outside: bool = True,
        apply_location: bool = True,
        apply_rotation: bool = True,
        apply_scale: bool = True,
    ) -> dict:
        """
        Cure a single mesh before Godot export: apply transforms, merge vertices by distance, recalc normals.

        - Apply Transforms bakes location/rotation/scale into mesh (scale→1,1,1) — fixes Godot skinning/collision.
        - Merge by Distance removes duplicate vertices (bmesh remove_doubles).
        - Recalc Normals fixes inverted faces (bmesh recalc_face_normals outside).

        Use before godot_export_glb or let godot_export_glb auto-cure.
        """
        resp = send_to_supermcp({
            "type": "cure_model",
            "params": {
                "name": name,
                "merge_distance": merge_distance,
                "recalc_outside": recalc_outside,
                "apply_location": apply_location,
                "apply_rotation": apply_rotation,
                "apply_scale": apply_scale,
            },
        })
        # unwrap addon envelope {status, result}
        if resp.get("status") == "success":
            return resp.get("result", resp)
        if resp.get("status") == "ok":
            return resp.get("result", resp)
        return resp

    @mcp.tool(
        annotations=ToolAnnotations(title="Cure Entire Scene", destructiveHint=False),
    )
    def cure_scene(
        merge_distance: float = 0.0001,
        recalc_outside: bool = True,
        apply_location: bool = True,
        apply_rotation: bool = True,
        apply_scale: bool = True,
        only_selected: bool = False,
        only_meshes: bool = True,
    ) -> dict:
        """
        Cure every (or selected) mesh in the scene: apply transforms + merge by distance + recalc normals.

        This is the pre-export gate for Godot. Run explicitly to inspect cure Report, or rely on godot_export_glb auto-cure.

        Returns per-object reports and summary {cured_count, total_vertices_removed}.
        """
        resp = send_to_supermcp({
            "type": "cure_scene",
            "params": {
                "merge_distance": merge_distance,
                "recalc_outside": recalc_outside,
                "apply_location": apply_location,
                "apply_rotation": apply_rotation,
                "apply_scale": apply_scale,
                "only_selected": only_selected,
                "only_meshes": only_meshes,
            },
        })
        if resp.get("status") == "success":
            return resp.get("result", resp)
        if resp.get("status") == "ok":
            return resp.get("result", resp)
        return resp
