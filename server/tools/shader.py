"""Fase 3 — Shader Node Trees (10 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers import parse_param_value
from server.tools_helpers.connection import send_to_supermcp

def _unwrap(r): return r.get("result", r) if r.get("status") in ("success","ok") else r

def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations=ToolAnnotations(title="Shader Create Tree"))
    def shader_create_tree(material_name: str, clear_existing: bool = True) -> dict:
        """Ensure material has node tree. Create if not exists. clear_existing removes non-output nodes."""
        return _unwrap(send_to_supermcp({"type":"shader_create_tree","params":{"material_name":material_name,"clear_existing":clear_existing}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Add Node"))
    def shader_add_node(material_name: str, node_type: str, location_x: int = 0, location_y: int = 0) -> dict:
        """Add node e.g. ShaderNodeTexImage, ShaderNodeNormalMap, ShaderNodeSeparateColor to material."""
        return _unwrap(send_to_supermcp({"type":"shader_add_node","params":{"material_name":material_name,"node_type":node_type,"location_x":location_x,"location_y":location_y}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Remove Node"))
    def shader_remove_node(material_name: str, node_name: str) -> dict:
        return _unwrap(send_to_supermcp({"type":"shader_remove_node","params":{"material_name":material_name,"node_name":node_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Link Nodes"))
    def shader_link_nodes(material_name: str, from_node: str, from_socket: str, to_node: str, to_socket: str) -> dict:
        """Link two shader nodes by socket names."""
        return _unwrap(send_to_supermcp({"type":"shader_link_nodes","params":{"material_name":material_name,"from_node":from_node,"from_socket":from_socket,"to_node":to_node,"to_socket":to_socket}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Set Node Param"))
    def shader_set_node_param(material_name: str, node_name: str, param: str, value: str = "") -> dict:
        """Set param on shader node. For TEX_IMAGE image, pass image name or filepath."""
        # try parse value
        parsed = value
        if value.lower() in ("true","false"):
            parsed = value.lower()=="true"
        else:
            try:
                parsed = float(value) if "." in value else int(value)
            except: pass
        return _unwrap(send_to_supermcp({"type":"shader_set_node_param","params":{"material_name":material_name,"node_name":node_name,"param":param,"value":parsed}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Get Tree", readOnlyHint=True))
    def shader_get_tree(material_name: str) -> dict:
        """Get nodes and links of a material."""
        return _unwrap(send_to_supermcp({"type":"shader_get_tree","params":{"material_name":material_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Clear Tree", destructiveHint=True))
    def shader_clear_tree(material_name: str) -> dict:
        return _unwrap(send_to_supermcp({"type":"shader_clear_tree","params":{"material_name":material_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Duplicate Tree"))
    def shader_duplicate_tree(source_material: str, new_material_name: str = "") -> dict:
        return _unwrap(send_to_supermcp({"type":"shader_duplicate_tree","params":{"source_material":source_material,"new_material_name":new_material_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Arrange Nodes"))
    def shader_arrange_nodes(material_name: str) -> dict:
        """Auto-grid arrange nodes."""
        return _unwrap(send_to_supermcp({"type":"shader_arrange_nodes","params":{"material_name":material_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Shader Export as Code", readOnlyHint=True))
    def shader_export_as_code(material_name: str) -> dict:
        """Export shader tree as bpy Python code."""
        return _unwrap(send_to_supermcp({"type":"shader_export_as_code","params":{"material_name":material_name}}))
