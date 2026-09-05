"""Fase 3 — PBR Materials + Bake + ORM (4+4)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _unwrap

def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="Create PBR Material"))
    def pbr_create_material(material_name: str, base_color: list | None = None, metallic: float = 0.0, roughness: float = 0.5) -> dict:
        """Create or update Principled BSDF material."""
        if base_color is None:
            base_color = [0.8,0.8,0.8,1.0]
        return _unwrap(send_to_supermcp({"type":"pbr_create_material","params":{"material_name":material_name,"base_color":base_color,"metallic":metallic,"roughness":roughness}}))

    @mcp.tool(annotations=ToolAnnotations(title="Assign Material to Object"))
    def pbr_assign_material(object_name: str, material_name: str, slot_index: int = 0) -> dict:
        return _unwrap(send_to_supermcp({"type":"pbr_assign_material","params":{"object_name":object_name,"material_name":material_name,"slot_index":slot_index}}))

    @mcp.tool(annotations=ToolAnnotations(title="Pack ORM Texture"))
    def pbr_pack_orm(ao_image_name: str = "", rough_image_name: str = "", metal_image_name: str = "", output_name: str = "ORM", width: int = 1024, height: int = 1024) -> dict:
        """Pack AO(R) + Rough(G) + Metal(B) into one ORM image for Godot (Non-Color)."""
        return _unwrap(send_to_supermcp({"type":"pbr_pack_orm","params":{"ao_image_name":ao_image_name,"rough_image_name":rough_image_name,"metal_image_name":metal_image_name,"output_name":output_name,"width":width,"height":height}}))

    @mcp.tool(annotations=ToolAnnotations(title="Bake Texture (Cycles)"))
    def pbr_bake_texture(object_name: str, bake_type: str = "AO", size: int = 1024, filepath: str = "/tmp/bake.png", samples: int = 32) -> dict:
        """Bake Cycles: AO, DIFFUSE, NORMAL, COMBINED, ROUGHNESS, EMIT. Saves to filepath."""
        return _unwrap(send_to_supermcp({"type":"pbr_bake_texture","params":{"object_name":object_name,"bake_type":bake_type,"size":size,"filepath":filepath,"samples":samples}}))