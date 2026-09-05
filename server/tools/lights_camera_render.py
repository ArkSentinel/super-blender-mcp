"""Fase 5 — Light 5 + Camera 7 + Render 4."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from server.tools_helpers.connection import send_to_supermcp

from server.tools_helpers import unwrap_response as _u

def register(mcp: FastMCP)->None:
    @mcp.tool(annotations=ToolAnnotations(title="Create Light"))
    def light_create(light_type: str = "POINT", name: str = "Light", location: list | None = None, energy: float = 1000, color: list | None = None) -> dict:
        """light_type: POINT, SUN, SPOT, AREA."""
        if location is None:
            location = [0,0,3]
        if color is None:
            color = [1,1,1]
        return _u(send_to_supermcp({"type":"light_create","params":{"light_type":light_type,"name":name,"location":location,"energy":energy,"color":color}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Light Params"))
    def light_set_params(light_name: str, params: dict | None = None) -> dict:
        if params is None:
            params = {}
        return _u(send_to_supermcp({"type":"light_set_params","params":{"light_name":light_name,"params":params}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set World HDRI"))
    def light_set_world_hdri(filepath: str = "", strength: float = 1.0) -> dict:
        return _u(send_to_supermcp({"type":"light_set_world_hdri","params":{"filepath":filepath,"strength":strength}}))

    @mcp.tool(annotations=ToolAnnotations(title="Setup Studio Lighting"))
    def light_setup_studio(preset: str = "3_point") -> dict:
        return _u(send_to_supermcp({"type":"light_setup_studio","params":{"preset":preset}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Lights", readOnlyHint=True))
    def light_list() -> dict:
        return _u(send_to_supermcp({"type":"light_list","params":{}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create Camera"))
    def camera_create(name: str = "Camera", location: list | None = None, rotation_euler: list | None = None, lens: float = 50) -> dict:
        if location is None:
            location = [7,-7,5]
        if rotation_euler is None:
            rotation_euler = [0.9,0,0.8]
        return _u(send_to_supermcp({"type":"camera_create","params":{"name":name,"location":location,"rotation_euler":rotation_euler,"lens":lens}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Camera Params"))
    def camera_set_params(camera_name: str, params: dict | None = None) -> dict:
        """params: lens, clip_start, clip_end, etc."""
        if params is None:
            params = {}
        return _u(send_to_supermcp({"type":"camera_set_params","params":{"camera_name":camera_name,"params":params}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Active Camera View"))
    def camera_set_view(camera_name: str) -> dict:
        return _u(send_to_supermcp({"type":"camera_set_view","params":{"camera_name":camera_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Camera Track To"))
    def camera_track_to(camera_name: str, target_object: str) -> dict:
        return _u(send_to_supermcp({"type":"camera_track_to","params":{"camera_name":camera_name,"target_object":target_object}}))

    @mcp.tool(annotations=ToolAnnotations(title="Create Camera Rig"))
    def camera_create_rig(target_object: str = "", rig_name: str = "CameraRig") -> dict:
        return _u(send_to_supermcp({"type":"camera_create_rig","params":{"target_object":target_object,"rig_name":rig_name}}))

    @mcp.tool(annotations=ToolAnnotations(title="Camera Render"))
    def camera_render(camera_name: str = "", filepath: str = "/tmp/camera_render.png") -> dict:
        return _u(send_to_supermcp({"type":"camera_render","params":{"camera_name":camera_name,"filepath":filepath}}))

    @mcp.tool(annotations=ToolAnnotations(title="List Cameras", readOnlyHint=True))
    def camera_list() -> dict:
        return _u(send_to_supermcp({"type":"camera_list","params":{}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Render Engine"))
    def render_set_engine(engine: str = "CYCLES") -> dict:
        """engine: CYCLES or BLENDER_EEVEE."""
        return _u(send_to_supermcp({"type":"render_set_engine","params":{"engine":engine}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Render Settings"))
    def render_set_settings(resolution_x: int = 1920, resolution_y: int = 1080, resolution_percentage: int = 100, samples: int = 128, filepath: str = "/tmp/render.png") -> dict:
        return _u(send_to_supermcp({"type":"render_set_settings","params":{"resolution_x":resolution_x,"resolution_y":resolution_y,"resolution_percentage":resolution_percentage,"samples":samples,"filepath":filepath}}))

    @mcp.tool(annotations=ToolAnnotations(title="Set Render Output"))
    def render_set_output(filepath: str = "/tmp/render.png", file_format: str = "PNG") -> dict:
        return _u(send_to_supermcp({"type":"render_set_output","params":{"filepath":filepath,"file_format":file_format}}))

    @mcp.tool(annotations=ToolAnnotations(title="Get Render Info", readOnlyHint=True))
    def render_get_info() -> dict:
        return _u(send_to_supermcp({"type":"render_get_info","params":{}}))