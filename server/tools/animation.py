"""Fase 4 — Animation & Keyframes (12 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Insert Keyframe"))
    def anim_insert_keyframe(object_name: str, data_path: str = "location", frame: int = 1, value: list = None) -> dict:
        return _u(send_to_supermcp({"type":"anim_insert_keyframe","params":{"object_name":object_name,"data_path":data_path,"frame":frame,"value":value}}))

    @mcp.tool(annotations=ToolAnnotations(title="Delete Keyframe"))
    def anim_delete_keyframe(object_name: str, data_path: str = "location", frame: int = 1) -> dict:
        return _u(send_to_supermcp({"type":"anim_delete_keyframe","params":{"object_name":object_name,"data_path":data_path,"frame":frame}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Timeline"))
    def anim_set_timeline(frame_start: int = 1, frame_end: int = 250, current_frame: int = 1, fps: int = 24) -> dict:
        return _u(send_to_supermcp({"type":"anim_set_timeline","params":{"frame_start":frame_start,"frame_end":frame_end,"current_frame":current_frame,"fps":fps}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create Action"))
    def anim_create_action(object_name: str, action_name: str = "Action") -> dict:
        return _u(send_to_supermcp({"type":"anim_create_action","params":{"object_name":object_name,"action_name":action_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Assign Action"))
    def anim_assign_action(object_name: str, action_name: str = "") -> dict:
        return _u(send_to_supermcp({"type":"anim_assign_action","params":{"object_name":object_name,"action_name":action_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Interpolation"))
    def anim_set_interpolation(object_name: str, data_path: str = "location", interpolation: str = "BEZIER") -> dict:
        """interpolation: BEZIER, LINEAR, CONSTANT."""
        return _u(send_to_supermcp({"type":"anim_set_interpolation","params":{"object_name":object_name,"data_path":data_path,"interpolation":interpolation}}))

    @mcp.tool(annotations=ToolAnnotations(title="Bake Animation"))
    def anim_bake(object_name: str, frame_start: int = 1, frame_end: int = 60) -> dict:
        return _u(send_to_supermcp({"type":"anim_bake","params":{"object_name":object_name,"frame_start":frame_start,"frame_end":frame_end}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create NLA Strip"))
    def anim_create_nla_strip(object_name: str, strip_name: str = "Strip", frame_start: int = 1) -> dict:
        """Push action to NLA. Use -loop suffix for Godot looping."""
        return _u(send_to_supermcp({"type":"anim_create_nla_strip","params":{"object_name":object_name,"strip_name":strip_name,"frame_start":frame_start}}))

    @mcp.tool(annotations=ToolAnnotations(title="Copy Keyframes"))
    def anim_copy_keyframes(source_object: str, target_object: str, data_path: str = "location") -> dict:
        return _u(send_to_supermcp({"type":"anim_copy_keyframes","params":{"source_object":source_object,"target_object":target_object,"data_path":data_path}}))

    @mcp.tool(annotations=ToolAnnotations(title="Clear Animation", destructiveHint=True))
    def anim_clear(object_name: str) -> dict:
        return _u(send_to_supermcp({"type":"anim_clear","params":{"object_name":object_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get Animation Info", readOnlyHint=True))
    def anim_get_info(object_name: str) -> dict:
        return _u(send_to_supermcp({"type":"anim_get_info","params":{"object_name":object_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Graph Handles"))
    def anim_set_graph_handles(object_name: str, handle_type: str = "AUTO_CLAMPED") -> dict:
        return _u(send_to_supermcp({"type":"anim_set_graph_handles","params":{"object_name":object_name,"handle_type":handle_type}}))
