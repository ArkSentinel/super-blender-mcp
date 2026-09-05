"""Fase 4 — Rigging & Armatures (8 tools)."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

def _u(r): return r.get("result",r) if r.get("status") in ("success","ok") else r

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Create Armature"))
    def rig_create_armature(name: str = "Armature", location: list = [0,0,0]) -> dict:
        return _u(send_to_supermcp({"type":"rig_create_armature","params":{"name":name,"location":location}}))

    @mcp.tool(annotations=ToolAnnotations(title="Add Bone"))
    def rig_add_bone(armature_name: str, bone_name: str = "Bone", head: list = [0,0,0], tail: list = [0,1,0], parent: str = "") -> dict:
        return _u(send_to_supermcp({"type":"rig_add_bone","params":{"armature_name":armature_name,"bone_name":bone_name,"head":head,"tail":tail,"parent":parent}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Bone Params"))
    def rig_set_bone_params(armature_name: str, bone_name: str, params: dict = {}) -> dict:
        return _u(send_to_supermcp({"type":"rig_set_bone_params","params":{"armature_name":armature_name,"bone_name":bone_name,"params":params}}))

    @mcp.tool(annotations=ToolAnnotations(title="Parent to Armature"))
    def rig_parent_to_armature(object_name: str, armature_name: str, with_weights: str = "ARMATURE_AUTO") -> dict:
        """with_weights: ARMATURE_AUTO, ARMATURE_ENVELOPE, or ARMATURE."""
        return _u(send_to_supermcp({"type":"rig_parent_to_armature","params":{"object_name":object_name,"armature_name":armature_name,"with_weights":with_weights}}))

    @mcp.tool(annotations=ToolAnnotations(title="Add IK Constraint"))
    def rig_add_ik_constraint(armature_name: str, bone_name: str, target_object: str, chain_count: int = 2) -> dict:
        return _u(send_to_supermcp({"type":"rig_add_ik_constraint","params":{"armature_name":armature_name,"bone_name":bone_name,"target_object":target_object,"chain_count":chain_count}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create Rig Preset"))
    def rig_create_preset(preset: str = "basic_chain", name: str = "RigPreset") -> dict:
        """preset: basic_chain (3 bones)."""
        return _u(send_to_supermcp({"type":"rig_create_preset","params":{"preset":preset,"name":name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Weight Transfer"))
    def rig_weight_transfer(source_object: str, target_object: str) -> dict:
        return _u(send_to_supermcp({"type":"rig_weight_transfer","params":{"source_object":source_object,"target_object":target_object}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Armatures", readOnlyHint=True))
    def rig_list_armatures() -> dict:
        return _u(send_to_supermcp({"type":"rig_list_armatures","params":{}}))
