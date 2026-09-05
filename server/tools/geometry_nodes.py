"""Fase 2 — Geometry Nodes: create, add_node, link, set_param, templates."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from server.tools_helpers import parse_param_value
from server.tools_helpers.connection import send_to_supermcp


from server.tools_helpers import unwrap_response as _unwrap


def register(mcp: FastMCP) -> None:

    @mcp.tool(annotations=ToolAnnotations(title="Create Geometry Nodes Modifier", destructiveHint=False))
    def geometry_nodes_create(object_name: str, modifier_name: str = "GeometryNodes", node_group_name: str = "") -> dict:
        """Create a Geometry Nodes modifier with a new or existing node group."""
        return _unwrap(send_to_supermcp({"type": "geometry_nodes_create", "params": {"object_name": object_name, "modifier_name": modifier_name, "node_group_name": node_group_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Add Geometry Node", destructiveHint=False))
    def geometry_nodes_add_node(node_group_name: str, node_type: str) -> dict:
        """Add a node to a geometry node group. e.g. GeometryNodeMeshCube, GeometryNodeSubdivideMesh, GeometryNodeDistributePointsOnFaces."""
        return _unwrap(send_to_supermcp({"type": "geometry_nodes_add_node", "params": {"node_group_name": node_group_name, "node_type": node_type}}))

    @mcp.tool(annotations=ToolAnnotations(title="Link Geometry Nodes", destructiveHint=False))
    def geometry_nodes_link(node_group_name: str, from_node: str, from_socket: str = "Geometry", to_node: str = "", to_socket: str = "Geometry") -> dict:
        """Link two nodes in a geometry node group by socket names."""
        return _unwrap(send_to_supermcp({"type": "geometry_nodes_link", "params": {"node_group_name": node_group_name, "from_node": from_node, "from_socket": from_socket, "to_node": to_node, "to_socket": to_socket}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Geometry Node Param", destructiveHint=False))
    def geometry_nodes_set_param(node_group_name: str, node_name: str, param: str, value: str = "") -> dict:
        """Set a param on a node (property or input default_value). value is string-coerced."""
        # Try to parse value as int/float/bool if possible
        parsed: object = value
        if value.lower() in ("true", "false"):
            parsed = value.lower() == "true"
        else:
            try:
                if "." in value:
                    parsed = float(value)
                else:
                    parsed = int(value)
            except:
                parsed = value
        return _unwrap(send_to_supermcp({"type": "geometry_nodes_set_param", "params": {"node_group_name": node_group_name, "node_name": node_name, "param": param, "value": parsed}}))

    @mcp.tool(annotations=ToolAnnotations(title="Geometry Nodes Templates", readOnlyHint=True))
    def geometry_nodes_templates() -> dict:
        """List 8 curated Geometry Nodes templates (scatter, extrude, boolean, etc.)."""
        return _unwrap(send_to_supermcp({"type": "geometry_nodes_templates", "params": {}}))
