# SuperMCP for Blender — Separate from Free (port 9877)
# SPDX-FileCopyrightText: 2025 SuperMCP
# SPDX-License-Identifier: GPL-3.0-or-later

import bpy
import bmesh
import mathutils
import json
import threading
import socket
import time
import traceback
import os
import io
from contextlib import redirect_stdout

bl_info = {
    "name": "SuperMCP",
    "author": "SuperMCP",
    "version": (0, 1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > SuperMCP",
    "description": "SuperMCP — Advanced mesh curing, PBR texturing, Godot pipeline. Port 9877 (Free uses 9876).",
    "category": "Interface",
}

SUPER_MCP_DEFAULT_HOST = "localhost"
SUPER_MCP_DEFAULT_PORT = 9877


# ── Curing helpers (pure bpy/bmesh, no ops where possible) ──────────────

def _apply_transforms_for_object(obj, do_location=True, do_rotation=True, do_scale=True):
    """Apply transforms by baking matrix into mesh data. Returns dict with before/after."""
    before_scale = tuple(float(v) for v in obj.scale)
    before_loc = tuple(float(v) for v in obj.location)
    before_rot = tuple(float(v) for v in obj.rotation_euler)

    # Only meshes and curves need matrix baking; others just reset delta
    if obj.type == 'MESH' and obj.data:
        # Use bmesh transform to avoid deps on ops
        mesh = obj.data
        mat = obj.matrix_world.copy()
        # We apply by transforming mesh vertices by obj.matrix_basis and resetting obj transform
        # Simpler: use bpy.ops.object.transform_apply via temp override — more reliable for all cases
        # Fallback to matrix baking if ops unavailable
        try:
            # Need to be in object mode and selected
            prev_mode = obj.mode if hasattr(obj, 'mode') else 'OBJECT'
            # Use context override
            ctx = bpy.context.copy()
            ctx['object'] = obj
            ctx['active_object'] = obj
            # Select only this object
            for o in bpy.context.view_layer.objects:
                o.select_set(o == obj)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.transform_apply(location=do_location, rotation=do_rotation, scale=do_scale)
            # Restore mode if needed
            if prev_mode != 'OBJECT':
                try:
                    bpy.ops.object.mode_set(mode=prev_mode)
                except:
                    pass
            applied_via = "ops"
        except Exception as e:
            # Fallback: bake matrix into mesh manually
            applied_via = f"matrix_fallback:{e}"
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.transform(bm, matrix=obj.matrix_basis, verts=bm.verts)
            bm.to_mesh(mesh)
            bm.free()
            mesh.update()
            if do_location:
                obj.location = (0, 0, 0)
            if do_rotation:
                obj.rotation_euler = (0, 0, 0)
            if do_scale:
                obj.scale = (1, 1, 1)
            # Reset matrix_basis deltas
            obj.delta_location = (0, 0, 0)
            obj.delta_rotation_euler = (0, 0, 0)
            obj.delta_scale = (1, 1, 1)
    else:
        if do_location:
            obj.location = (0, 0, 0)
        if do_rotation:
            obj.rotation_euler = (0, 0, 0)
        if do_scale:
            obj.scale = (1, 1, 1)
        applied_via = "direct_reset"

    return {
        "name": obj.name,
        "type": obj.type,
        "before": {"location": before_loc, "rotation": before_rot, "scale": before_scale},
        "after": {"location": tuple(float(v) for v in obj.location),
                  "rotation": tuple(float(v) for v in obj.rotation_euler),
                  "scale": tuple(float(v) for v in obj.scale)},
        "method": applied_via,
    }


def _merge_by_distance_for_object(obj, distance=0.0001):
    """Merge vertices by distance on a mesh object. Returns stats."""
    if obj.type != 'MESH' or not obj.data:
        return {"name": obj.name, "skipped": True, "reason": f"type {obj.type} not mesh"}
    mesh = obj.data
    before_verts = len(mesh.vertices)
    # Use bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    # Ensure lookup tables
    bm.verts.ensure_lookup_table()
    result = bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=distance)
    # bmesh remove_doubles doesn't return count, compute diff
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    after_verts = len(mesh.vertices)
    removed = before_verts - after_verts
    return {
        "name": obj.name,
        "before_verts": before_verts,
        "after_verts": after_verts,
        "removed": removed,
        "distance": distance,
    }


def _recalc_normals_for_object(obj, inside=False, fix_inverted=True):
    """Recalculate normals, detect and fix inverted. Returns stats."""
    if obj.type != 'MESH' or not obj.data:
        return {"name": obj.name, "skipped": True, "reason": f"type {obj.type} not mesh"}
    mesh = obj.data
    # Count faces with inverted normals before (use polygon normal vs calc)
    # Simple heuristic: check if mesh has custom normals or use bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    # Recalculate
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # Optionally ensure normals outside
    if fix_inverted:
        # bmesh recalc already does outside
        pass
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    # Ensure auto smooth and calc
    try:
        mesh.calc_normals()
    except:
        pass
    # Count after: check for loose/degenerate
    degenerate = sum(1 for p in mesh.polygons if p.area < 1e-8)
    return {
        "name": obj.name,
        "recalculated": True,
        "inside": inside,
        "degenerate_faces": degenerate,
        "polygons": len(mesh.polygons),
        "vertices": len(mesh.vertices),
    }


def _cure_single_object(obj, merge_distance=0.0001, recalc_outside=True, apply_location=True, apply_rotation=True, apply_scale=True):
    """Full cure for one object: apply transforms → merge → recalc normals. Returns combined report."""
    if obj.type not in ('MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'ARMATURE', 'EMPTY', 'LIGHT', 'CAMERA'):
        return {"name": obj.name, "type": obj.type, "skipped": True}

    # For non-mesh, only apply transforms
    if obj.type != 'MESH':
        t = _apply_transforms_for_object(obj, apply_location, apply_rotation, apply_scale)
        return {"name": obj.name, "type": obj.type, "transform": t, "note": "non-mesh: only transforms"}

    t = _apply_transforms_for_object(obj, apply_location, apply_rotation, apply_scale)
    m = _merge_by_distance_for_object(obj, distance=merge_distance)
    n = _recalc_normals_for_object(obj, inside=not recalc_outside, fix_inverted=True)

    # Weighted normal mod check: if bevel-like sharp edges, suggest weighted normal
    # We don't auto-add but report
    has_sharp = any(not p.use_smooth for p in obj.data.polygons) if obj.data else False

    return {
        "name": obj.name,
        "type": obj.type,
        "transform": t,
        "merge": m,
        "normals": n,
        "has_sharp_edges": has_sharp,
    }


# ── Server ────────────────────────────────────────────────────────────────

class SuperMCPServer:
    def __init__(self, host=SUPER_MCP_DEFAULT_HOST, port=SUPER_MCP_DEFAULT_PORT):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if bpy.app.background:
            print("SuperMCP: cannot start server in background mode — use GUI or xvfb-run")
            return
        if self.running:
            print("SuperMCP: already running")
            return
        self.running = True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            print(f"SuperMCP server started on {self.host}:{self.port} (Free is 9876, Super is 9877)")
        except Exception as e:
            print(f"SuperMCP failed to start: {e}")
            self.stop()

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        if self.server_thread and self.server_thread.is_alive():
            try:
                self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None
        print("SuperMCP server stopped")

    def _server_loop(self):
        print("SuperMCP server thread started")
        if self.socket:
            self.socket.settimeout(1.0)
        while self.running:
            try:
                try:
                    client, address = self.socket.accept()
                    print(f"SuperMCP: client {address}")
                    t = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
                    t.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"SuperMCP accept error: {e}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"SuperMCP loop error: {e}")
                if not self.running:
                    break
                time.sleep(0.5)
        print("SuperMCP server thread stopped")

    def _handle_client(self, client):
        client.settimeout(None)
        buffer = b''
        try:
            while self.running:
                try:
                    data = client.recv(8192)
                    if not data:
                        break
                    buffer += data
                    # Try null-delimited (blmcp style) or plain JSON
                    # Support both: if buffer contains \0, split, else try json
                    if b'\0' in buffer:
                        raw, _, rest = buffer.partition(b'\0')
                        buffer = rest
                        command = json.loads(raw.decode('utf-8'))
                    else:
                        try:
                            command = json.loads(buffer.decode('utf-8'))
                            buffer = b''
                        except json.JSONDecodeError:
                            # Check for newline delimited
                            if b'\n' in buffer and buffer.strip().startswith(b'{'):
                                # try line
                                lines = buffer.split(b'\n')
                                for i, line in enumerate(lines):
                                    if not line.strip():
                                        continue
                                    try:
                                        command = json.loads(line.decode('utf-8'))
                                        buffer = b'\n'.join(lines[i+1:])
                                        raise StopIteration  # break to execute
                                    except:
                                        continue
                                continue
                            else:
                                continue

                    def execute_wrapper():
                        try:
                            response = self.execute_command(command)
                            payload = (json.dumps(response) + "\0").encode('utf-8')
                            try:
                                client.sendall(payload)
                            except:
                                print("SuperMCP: failed to send response")
                        except Exception as e:
                            traceback.print_exc()
                            try:
                                client.sendall((json.dumps({"status": "error", "message": str(e)}) + "\0").encode('utf-8'))
                            except:
                                pass
                        return None

                    bpy.app.timers.register(execute_wrapper, first_interval=0.0)

                    # For legacy free-style command without null delimiter, need to detect old style
                    # Already handled above

                except StopIteration:
                    # executed via inner handler above — continue loop for next command handling
                    # Need to re-trigger wrapper properly: we used exception to break, but better to handle here
                    # Actually command already executed via wrapper registration, so just continue
                    continue
                except Exception as e:
                    print(f"SuperMCP recv error: {e}")
                    break
        except Exception as e:
            print(f"SuperMCP client handler error: {e}")
        finally:
            try:
                client.close()
            except:
                pass

    def _structured_error(self, e):
        tb = traceback.format_exc()
        # Extract line number of user code if present
        line_no = None
        try:
            tb_list = traceback.extract_tb(e.__traceback__)
            if tb_list:
                line_no = tb_list[-1].lineno
        except:
            pass
        return {
            "status": "error",
            "exception": type(e).__name__,
            "message": str(e),
            "line_number": line_no,
            "traceback": tb,
        }

    def _get_3d_override(self):
        """Return VIEW_3D context override dict or None for background safety."""
        try:
            screen = getattr(bpy.context, "screen", None)
            window = getattr(bpy.context, "window", None)
            if not screen:
                return None
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    space = area.spaces.active if hasattr(area, "spaces") else None
                    if region and space:
                        return {"window": window, "screen": screen, "area": area, "region": region, "space_data": space}
        except:
            pass
        return None

    def execute_command(self, command):
        try:
            return self._execute_command_internal(command)
        except Exception as e:
            traceback.print_exc()
            err = self._structured_error(e)
            err["handler"] = command.get("type", "unknown")
            return err

    def _execute_command_internal(self, command):
        # Support both free-style {"type","params"} and blmcp-style {"code","strict_json"} and direct {"type":"execute"}
        if "code" in command and "type" not in command:
            # blmcp send_code style: {"type":"execute","code":...} or just {"code":...}
            code = command.get("code", "")
            strict = command.get("strict_json", False)
            # This is execute path
            return self._handle_execute_code(code, strict)

        cmd_type = command.get("type")
        params = command.get("params", {})

        # Alias for blmcp execute
        if cmd_type == "execute":
            code = params.get("code") if isinstance(params, dict) else command.get("code", "")
            if not code:
                code = command.get("code", "")
            return self._handle_execute_code(code, command.get("strict_json", False))

        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self._handle_execute_code_wrapper,
            "cure_model": self.cure_model,
            "cure_scene": self.cure_scene,
            "godot_validate_scene": self.godot_validate_scene,
            "godot_export_glb": self.godot_export_glb,
            "get_godot_export_info": self.get_godot_export_info,
            # Fase 2 — modifiers / mesh / geo nodes
            "add_modifier": self.add_modifier,
            "remove_modifier": self.remove_modifier,
            "set_modifier_params": self.set_modifier_params,
            "move_modifier": self.move_modifier,
            "apply_modifier": self.apply_modifier,
            "list_modifiers": self.list_modifiers,
            "mesh_operation": self.mesh_operation,
            "validate_mesh": self.validate_mesh,
            "geometry_nodes_create": self.geometry_nodes_create,
            "geometry_nodes_add_node": self.geometry_nodes_add_node,
            "geometry_nodes_link": self.geometry_nodes_link,
            "geometry_nodes_set_param": self.geometry_nodes_set_param,
            "geometry_nodes_templates": self.geometry_nodes_templates,
            # Fase 3 — shader / uv / pbr
            "shader_create_tree": self.shader_create_tree,
            "shader_add_node": self.shader_add_node,
            "shader_remove_node": self.shader_remove_node,
            "shader_link_nodes": self.shader_link_nodes,
            "shader_set_node_param": self.shader_set_node_param,
            "shader_get_tree": self.shader_get_tree,
            "shader_clear_tree": self.shader_clear_tree,
            "shader_duplicate_tree": self.shader_duplicate_tree,
            "shader_arrange_nodes": self.shader_arrange_nodes,
            "shader_export_as_code": self.shader_export_as_code,
            "uv_unwrap": self.uv_unwrap,
            "uv_add_layer": self.uv_add_layer,
            "uv_pack_islands": self.uv_pack_islands,
            "uv_get_info": self.uv_get_info,
            "uv_export_layout": self.uv_export_layout,
            "uv_validate": self.uv_validate,
            "pbr_create_material": self.pbr_create_material,
            "pbr_assign_material": self.pbr_assign_material,
            "pbr_pack_orm": self.pbr_pack_orm,
            "pbr_bake_texture": self.pbr_bake_texture,
            # Fase 6 — batch / io / diagnostics / scene / presets / godot polish
            "batch_execute_on_objects": self.batch_execute_on_objects,
            "batch_render_queue": self.batch_render_queue,
            "batch_import": self.batch_import,
            "batch_export": self.batch_export,
            "io_import_file": self.io_import_file,
            "io_export_file": self.io_export_file,
            "io_list_formats": self.io_list_formats,
            "diag_check_rig_health": self.diag_check_rig_health,
            "diag_validate_armature": self.diag_validate_armature,
            "diag_fix_rig": self.diag_fix_rig,
            "diag_get_rig_report": self.diag_get_rig_report,
            "scene_clean": self.scene_clean,
            "scene_organize_collections": self.scene_organize_collections,
            "scene_merge": self.scene_merge,
            "scene_get_stats": self.scene_get_stats,
            "preset_apply": self.preset_apply,
            "preset_list": self.preset_list,
            "preset_create_from_scene": self.preset_create_from_scene,
            "preset_get_hint": self.preset_get_hint,
            "godot_setup_collision": self.godot_setup_collision,
            "godot_setup_lod": self.godot_setup_lod,
            "godot_check_material_compatibility": self.godot_check_material_compatibility,
            "godot_batch_export": self.godot_batch_export,
            # Insights Free — high-level native tools + alias
            "reset_scene_clean": self.reset_scene_clean,
            "auto_frame_camera": self.auto_frame_camera,
            "render_object_preview": self.render_object_preview,
            "export_godot_glb": self.export_godot_glb,
            # Fase 5 — lights / camera / render
            "light_create": self.light_create,
            "light_set_params": self.light_set_params,
            "light_set_world_hdri": self.light_set_world_hdri,
            "light_setup_studio": self.light_setup_studio,
            "light_list": self.light_list,
            "camera_create": self.camera_create,
            "camera_set_params": self.camera_set_params,
            "camera_set_view": self.camera_set_view,
            "camera_track_to": self.camera_track_to,
            "camera_create_rig": self.camera_create_rig,
            "camera_render": self.camera_render,
            "camera_list": self.camera_list,
            "render_set_engine": self.render_set_engine,
            "render_set_settings": self.render_set_settings,
            "render_set_output": self.render_set_output,
            "render_get_info": self.render_get_info,
            # Fase 4 — rigging / animation
            "rig_create_armature": self.rig_create_armature,
            "rig_add_bone": self.rig_add_bone,
            "rig_set_bone_params": self.rig_set_bone_params,
            "rig_parent_to_armature": self.rig_parent_to_armature,
            "rig_add_ik_constraint": self.rig_add_ik_constraint,
            "rig_create_preset": self.rig_create_preset,
            "rig_weight_transfer": self.rig_weight_transfer,
            "rig_list_armatures": self.rig_list_armatures,
            "anim_insert_keyframe": self.anim_insert_keyframe,
            "anim_delete_keyframe": self.anim_delete_keyframe,
            "anim_set_timeline": self.anim_set_timeline,
            "anim_create_action": self.anim_create_action,
            "anim_assign_action": self.anim_assign_action,
            "anim_set_interpolation": self.anim_set_interpolation,
            "anim_bake": self.anim_bake,
            "anim_create_nla_strip": self.anim_create_nla_strip,
            "anim_copy_keyframes": self.anim_copy_keyframes,
            "anim_clear": self.anim_clear,
            "anim_get_info": self.anim_get_info,
            "anim_set_graph_handles": self.anim_set_graph_handles,
        }
        handler = handlers.get(cmd_type)
        if handler:
            print(f"SuperMCP: executing {cmd_type}")
            # Context Override wrapper — fixes bpy.context.active_object == None in background/API
            override = self._get_3d_override()
            try:
                if override:
                    with bpy.context.temp_override(**override):
                        result = handler(**params) if isinstance(params, dict) else handler()
                else:
                    result = handler(**params) if isinstance(params, dict) else handler()
            except Exception as e:
                traceback.print_exc()
                err = self._structured_error(e)
                err["handler"] = cmd_type
                return err
            print(f"SuperMCP: {cmd_type} done")
            return {"status": "success", "result": result}
        else:
            return {"status": "error", "exception": "UnknownCommand", "message": f"Unknown SuperMCP command: {cmd_type}. Available: {list(handlers.keys())}", "traceback": ""}

    def _handle_execute_code(self, code, strict_json=False):
        # Structured JSON traceback: exception + line_number + traceback
        try:
            namespace = {"bpy": bpy, "bmesh": bmesh, "mathutils": mathutils}
            capture = io.StringIO()
            # Also wrap with 3D override if available
            override = self._get_3d_override()
            with redirect_stdout(capture):
                if override:
                    with bpy.context.temp_override(**override):
                        exec(code, namespace)
                else:
                    exec(code, namespace)
            out = capture.getvalue()
            result = namespace.get("result", out)
            try:
                json.dumps(result)
            except:
                result = str(result) if not isinstance(result, dict) else {k: str(v) for k, v in result.items()}
            return {"status": "ok", "result": result, "stdout": out}
        except Exception as e:
            traceback.print_exc()
            err = self._structured_error(e)
            err["code_snippet"] = code.splitlines()[err["line_number"]-1] if err["line_number"] and 1 <= err["line_number"] <= len(code.splitlines()) else ""
            return err

    def _handle_execute_code_wrapper(self, code=""):
        return self._handle_execute_code(code)

    # ── Handlers ──────────────────────────────────────────────────────────

    def get_scene_info(self):
        scene = bpy.context.scene
        info = {
            "name": scene.name,
            "object_count": len(scene.objects),
            "objects": [],
            "materials_count": len(bpy.data.materials),
            "port": self.port,
            "server": "SuperMCP",
        }
        for i, obj in enumerate(scene.objects):
            if i >= 20:
                break
            info["objects"].append({
                "name": obj.name,
                "type": obj.type,
                "location": [round(float(obj.location.x), 4), round(float(obj.location.y), 4), round(float(obj.location.z), 4)],
                "scale": [round(float(obj.scale.x), 4), round(float(obj.scale.y), 4), round(float(obj.scale.z), 4)],
            })
        return info

    def get_object_info(self, name=""):
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        info = {
            "name": obj.name,
            "type": obj.type,
            "location": [float(obj.location.x), float(obj.location.y), float(obj.location.z)],
            "rotation": [float(obj.rotation_euler.x), float(obj.rotation_euler.y), float(obj.rotation_euler.z)],
            "scale": [float(obj.scale.x), float(obj.scale.y), float(obj.scale.z)],
            "visible": obj.visible_get(),
            "materials": [s.material.name for s in obj.material_slots if s.material],
        }
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            info["mesh"] = {"vertices": len(mesh.vertices), "edges": len(mesh.edges), "polygons": len(mesh.polygons)}
            # Quick curing hints
            non_uniform = any(abs(s - 1.0) > 1e-4 for s in info["scale"])
            ngons = sum(1 for p in mesh.polygons if len(p.vertices) > 4)
            info["curing_hints"] = {
                "needs_apply_transforms": non_uniform or any(abs(v) > 1e-4 for v in info["location"]),
                "ngon_count": ngons,
                "needs_triangulate": ngons > 0,
                "uv_layers": len(mesh.uv_layers),
                "has_uv": len(mesh.uv_layers) > 0,
            }
        return info

    def get_viewport_screenshot(self, max_size=800, filepath="/tmp/supermcp_viewport.png", format="png"):
        # Copy fix from addon.py free but on SuperMCP port
        try:
            if not filepath:
                return {"error": "No filepath"}
            area = region = space = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    space = a.spaces.active
                    region = next((r for r in a.regions if r.type == 'WINDOW'), None)
                    break
            if not area or region is None or space is None:
                return {"error": "No 3D viewport found"}
            method = "offscreen"
            try:
                import gpu
                import numpy as np
                r3d = space.region_3d
                src_w, src_h = region.width, region.height
                if max(src_w, src_h) > max_size:
                    s = max_size / max(src_w, src_h)
                    width, height = max(1, int(src_w * s)), max(1, int(src_h * s))
                else:
                    width, height = src_w, src_h
                offscreen = gpu.types.GPUOffScreen(width, height)
                try:
                    offscreen.draw_view3d(bpy.context.scene, bpy.context.view_layer, space, region, r3d.view_matrix, r3d.window_matrix, do_color_management=True)
                    buf = offscreen.texture_color.read()
                finally:
                    offscreen.free()
                buf.dimensions = width * height * 4
                pixels = np.asarray(buf, dtype=np.float32) / 255.0
                image = bpy.data.images.new("supermcp_viewport", width, height, alpha=True)
                image.pixels.foreach_set(pixels.ravel())
                image.filepath_raw = filepath
                image.file_format = format.upper()
                image.save()
                bpy.data.images.remove(image)
            except Exception as e:
                print(f"SuperMCP offscreen failed {e}, fallback window grab")
                method = "window_grab"
                with bpy.context.temp_override(area=area):
                    bpy.ops.screen.screenshot_area(filepath=filepath)
                img = bpy.data.images.load(filepath)
                width, height = img.size
                if max(width, height) > max_size:
                    s = max_size / max(width, height)
                    width, height = int(width * s), int(height * s)
                    img.scale(width, height)
                    img.file_format = format.upper()
                    img.save()
                bpy.data.images.remove(img)
            return {"success": True, "width": width, "height": height, "filepath": filepath, "method": method}
        except Exception as e:
            return {"error": str(e)}

    def cure_model(self, name="", merge_distance=0.0001, recalc_outside=True, apply_location=True, apply_rotation=True, apply_scale=True):
        """Cure a single mesh: apply transforms + merge by distance + recalc normals."""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        # Ensure object mode
        try:
            if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
        result = _cure_single_object(obj, merge_distance, recalc_outside, apply_location, apply_rotation, apply_scale)
        return result

    def cure_scene(self, merge_distance=0.0001, recalc_outside=True, apply_location=True, apply_rotation=True, apply_scale=True, only_selected=False, only_meshes=True):
        """Cure every (or selected) object in scene. Returns per-object report + summary."""
        try:
            if bpy.context.view_layer.objects.active and bpy.context.view_layer.objects.active.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
        targets = []
        if only_selected:
            targets = list(bpy.context.selected_objects)
            if not targets:
                # fallback to active
                if bpy.context.view_layer.objects.active:
                    targets = [bpy.context.view_layer.objects.active]
        else:
            targets = list(bpy.context.scene.objects)

        if only_meshes:
            targets = [o for o in targets if o.type == 'MESH']

        reports = []
        total_removed = 0
        cured_count = 0
        for obj in targets:
            r = _cure_single_object(obj, merge_distance, recalc_outside, apply_location, apply_rotation, apply_scale)
            reports.append(r)
            if "merge" in r and "removed" in r["merge"]:
                total_removed += r["merge"]["removed"]
            if not r.get("skipped"):
                cured_count += 1

        return {
            "cured_count": cured_count,
            "total_targets": len(targets),
            "total_vertices_removed": total_removed,
            "merge_distance": merge_distance,
            "recalc_outside": recalc_outside,
            "reports": reports,
        }

    def godot_validate_scene(self, only_selected=False):
        """Validate scene for Godot export. Returns errors/warnings/can_export."""
        errors = []
        warnings = []
        infos = []
        objects = bpy.context.selected_objects if only_selected else list(bpy.context.scene.objects)
        meshes = [o for o in objects if o.type == 'MESH']

        if not meshes:
            warnings.append("No mesh objects in selection/scene — export would be empty")

        for obj in meshes:
            mesh = obj.data
            # Scale check
            if any(abs(s - 1.0) > 1e-4 for s in obj.scale):
                warnings.append(f"{obj.name}: scale {tuple(round(float(s),4) for s in obj.scale)} != (1,1,1) — needs Apply Transforms (auto-fixed on export)")
            if any(abs(v) > 1e-3 for v in obj.location) and obj.location.length > 0.001:
                # Only warn if not at origin? Not error, but hint
                infos.append(f"{obj.name}: location {tuple(round(float(v),3) for v in obj.location)} will be baked on apply")
            # Ngons
            ngons = sum(1 for p in mesh.polygons if len(p.vertices) > 4)
            if ngons:
                warnings.append(f"{obj.name}: {ngons} ngons — Godot triangulates unpredictably, cure will handle")
            # UV
            if len(mesh.uv_layers) == 0:
                # Only warn if has material with texture
                has_tex = any(s.material and s.material.use_nodes for s in obj.material_slots)
                if has_tex:
                    warnings.append(f"{obj.name}: no UV layers but has material — needs unwrap")
            # Missing images
            for slot in obj.material_slots:
                if slot.material and slot.material.use_nodes:
                    for node in slot.material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            img = node.image
                            if img.source == 'FILE' and img.filepath:
                                abs_path = bpy.path.abspath(img.filepath)
                                if abs_path and not os.path.exists(abs_path) and not img.packed_file:
                                    errors.append(f"{obj.name}/{slot.material.name}: missing image {img.name} → {abs_path}")
            # Degenerate
            degenerate = sum(1 for p in mesh.polygons if p.area < 1e-8)
            if degenerate:
                warnings.append(f"{obj.name}: {degenerate} degenerate faces (area ~0)")

        # Global: units
        unit_scale = bpy.context.scene.unit_settings.scale_length
        if abs(unit_scale - 1.0) > 1e-4:
            infos.append(f"Unit scale {unit_scale} — Godot 1 unit = 1 meter, check scale")

        # Anim check
        armatures = [o for o in objects if o.type == 'ARMATURE']
        for arm in armatures:
            if any(abs(s-1.0)>1e-4 for s in arm.scale):
                warnings.append(f"Armature {arm.name}: non-uniform scale — will break skinning, needs apply")

        can_export = len(errors) == 0
        return {
            "can_export": can_export,
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "mesh_count": len(meshes),
            "object_count": len(objects),
            "checks": {"errors": len(errors), "warnings": len(warnings), "infos": len(infos)},
        }

    def godot_export_glb(self, filepath="", export_format="GLB", use_selection=False, use_visible=False, export_apply=True, export_yup=True, export_animations=True, auto_cure=True, cure_merge_distance=0.0001, cure_recalc_outside=True):
        """Export to glTF/GLB with optional auto-cure. Cure runs BEFORE export."""
        if not filepath:
            raise ValueError("filepath required (e.g. /tmp/model.glb)")
        # Ensure .glb extension
        if export_format == "GLB" and not filepath.lower().endswith(".glb"):
            filepath = filepath + ".glb"

        cure_report = None
        if auto_cure:
            # Cure scene (or selection if use_selection)
            cure_report = self.cure_scene(
                merge_distance=cure_merge_distance,
                recalc_outside=cure_recalc_outside,
                only_selected=use_selection,
                only_meshes=True,
            )

        # Validate after cure
        validation = self.godot_validate_scene(only_selected=use_selection)

        # Perform export
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            # Blender glTF exporter
            result = bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format=export_format,
                export_yup=export_yup,
                export_apply=export_apply,
                export_texcoords=True,
                export_normals=True,
                export_tangents=True,
                export_materials='EXPORT',
                export_images=True,
                export_cameras=False,
                export_lights=False,
                use_selection=use_selection,
                use_visible=use_visible,
                export_animations=export_animations,
                export_frame_step=1,
                export_force_sampling=True,
                export_nla_strips=True,
                export_def_bones=False,
                export_skins=True,
                export_morph=True,
            )
            # bpy.ops returns {'FINISHED'} on success
            success = result == {'FINISHED'} or 'FINISHED' in str(result)
        except Exception as e:
            traceback.print_exc()
            return {
                "success": False,
                "filepath": filepath,
                "error": str(e),
                "cure_report": cure_report,
                "validation": validation,
            }

        # Check file exists
        exists = os.path.exists(filepath)
        size = os.path.getsize(filepath) if exists else 0
        return {
            "success": bool(success and exists),
            "filepath": filepath,
            "file_exists": exists,
            "file_size_bytes": size,
            "cure_report": cure_report,
            "validation": validation,
            "export_settings": {
                "export_format": export_format,
                "export_yup": export_yup,
                "export_apply": export_apply,
                "export_tangents": True,
                "auto_cure": auto_cure,
            }
        }

    def get_godot_export_info(self):
        return {
            "server": "SuperMCP",
            "port": self.port,
            "free_port": 9876,
            "export_format": "glTF 2.0 (.glb) — Godot 4.x native",
            "curing": {
                "apply_transforms": "location+rotation+scale → (1,1,1)",
                "merge_by_distance": "bmesh.ops.remove_doubles, default 0.0001",
                "recalc_normals": "bmesh.ops.recalc_face_normals outside",
            },
            "auto_cure_on_export": True,
            "validation_gates": ["scale !=1", "ngons", "missing UV", "missing images", "degenerate faces", "armature scale"],
        }


    # ── Fase 2: Modifiers / Mesh / Geometry Nodes ─────────────────────

    # Modifier helpers
    _MODIFIER_TYPE_MAP = {
        "subsurf": "SUBSURF", "subdivision": "SUBSURF",
        "bevel": "BEVEL", "boolean": "BOOLEAN", "array": "ARRAY",
        "mirror": "MIRROR", "solidify": "SOLIDIFY", "decimate": "DECIMATE",
        "remesh": "REMESH", "weld": "WELD", "triangulate": "TRIANGULATE",
        "shrinkwrap": "SHRINKWRAP", "weighted_normal": "WEIGHTED_NORMAL",
        "data_transfer": "DATA_TRANSFER", "lattice": "LATTICE",
        "displace": "DISPLACE", "smooth": "SMOOTH", "laplacian_smooth": "LAPLACIANSMOOTH",
        "simple_deform": "SIMPLE_DEFORM", "screw": "SCREW", "skin": "SKIN",
        "wireframe": "WIREFRAME", "nodes": "NODES", "geometry_nodes": "NODES",
    }

    def _resolve_modifier_type(self, t):
        key = t.lower().strip()
        return self._MODIFIER_TYPE_MAP.get(key, t.upper())

    def add_modifier(self, object_name="", modifier_type="SUBSURF", name="", params=None):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        mtype = self._resolve_modifier_type(modifier_type)
        mod_name = name or f"{mtype.title()}"
        try:
            mod = obj.modifiers.new(name=mod_name, type=mtype)
        except Exception as e:
            raise ValueError(f"Failed to add modifier {mtype} on {object_name}: {e}")
        # Apply params if provided
        if params and isinstance(params, dict):
            for k, v in params.items():
                try:
                    # Handle special nested like levels
                    if hasattr(mod, k):
                        setattr(mod, k, v)
                    else:
                        # Try case variations
                        # e.g. "levels" vs "render_levels"
                        pass
                except Exception as e:
                    print(f"SuperMCP: set_modifier param {k}={v} failed: {e}")
        return {
            "object": obj.name,
            "modifier": mod.name,
            "type": mod.type,
            "params_applied": params or {},
            "total_modifiers": len(obj.modifiers),
        }

    def remove_modifier(self, object_name="", modifier_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise ValueError(f"Modifier not found: {modifier_name} on {object_name}")
        obj.modifiers.remove(mod)
        return {"object": obj.name, "removed": modifier_name, "remaining": len(obj.modifiers)}

    def set_modifier_params(self, object_name="", modifier_name="", params=None):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise ValueError(f"Modifier not found: {modifier_name}")
        applied = {}
        failed = {}
        for k, v in (params or {}).items():
            try:
                if hasattr(mod, k):
                    setattr(mod, k, v)
                    applied[k] = v
                else:
                    failed[k] = f"no attribute {k} on {mod.type}"
            except Exception as e:
                failed[k] = str(e)
        return {"object": obj.name, "modifier": mod.name, "type": mod.type, "applied": applied, "failed": failed}

    def move_modifier(self, object_name="", modifier_name="", index=0):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise ValueError(f"Modifier not found: {modifier_name}")
        # Find current index
        cur = list(obj.modifiers).index(mod)
        target = max(0, min(index, len(obj.modifiers)-1))
        # Move via bpy.ops.object.modifier_move_to_index
        try:
            # Need active object context
            prev_active = bpy.context.view_layer.objects.active
            for o in bpy.context.view_layer.objects:
                o.select_set(o == obj)
            bpy.context.view_layer.objects.active = obj
            # Use override
            with bpy.context.temp_override(object=obj):
                # Move step by step
                while list(obj.modifiers).index(mod) < target:
                    bpy.ops.object.modifier_move_down(modifier=mod.name)
                while list(obj.modifiers).index(mod) > target:
                    bpy.ops.object.modifier_move_up(modifier=mod.name)
            if prev_active:
                bpy.context.view_layer.objects.active = prev_active
        except Exception as e:
            # Fallback: report error but don't crash
            return {"object": obj.name, "modifier": mod.name, "from": cur, "to": target, "error": str(e)}
        return {"object": obj.name, "modifier": mod.name, "from": cur, "to": target}

    def apply_modifier(self, object_name="", modifier_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise ValueError(f"Modifier not found: {modifier_name}")
        try:
            prev_active = bpy.context.view_layer.objects.active
            for o in bpy.context.view_layer.objects:
                o.select_set(o == obj)
            bpy.context.view_layer.objects.active = obj
            with bpy.context.temp_override(object=obj):
                bpy.ops.object.modifier_apply(modifier=mod.name)
            if prev_active:
                bpy.context.view_layer.objects.active = prev_active
        except Exception as e:
            raise RuntimeError(f"Failed to apply {modifier_name}: {e}")
        return {"object": obj.name, "applied": modifier_name, "remaining": len(obj.modifiers)}

    def list_modifiers(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        out = []
        for i, m in enumerate(obj.modifiers):
            out.append({
                "index": i,
                "name": m.name,
                "type": m.type,
                "show_viewport": m.show_viewport,
                "show_render": m.show_render,
                "is_active": i == 0,
            })
        return {"object": obj.name, "modifiers": out, "count": len(out)}

    def mesh_operation(self, object_name="", operation="subdivide", params=None):
        """Mesh ops via bmesh/bpy.ops.mesh. Supports: bevel, subdivide, triangulate, decimate, bridge, dissolve."""
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh object not found: {object_name}")
        params = params or {}
        mesh = obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        op = operation.lower()
        info = {"operation": op}
        try:
            if op in ("subdivide", "subdivision"):
                cuts = int(params.get("cuts", 1))
                # Use bmesh subdivide
                bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=cuts, use_grid_fill=True)
                info["cuts"] = cuts
            elif op == "bevel":
                offset = float(params.get("offset", 0.1))
                segments = int(params.get("segments", 1))
                # Bevel needs edges; use all edges if not specified
                bmesh.ops.bevel(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], offset=offset, segments=segments, profile=0.7)
                info["offset"] = offset
                info["segments"] = segments
            elif op in ("triangulate", "triangulate_mesh"):
                # Triangulate all faces
                bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='BEAUTY', ngon_method='BEAUTY')
                info["triangulated"] = True
            elif op == "decimate":
                # Decimate via modifier preview not bmesh; use dissolve + weld as placeholder
                # For real decimate we suggest modifier; here do limited dissolve
                angle = float(params.get("angle_limit", 0.087))
                bmesh.ops.dissolve_limit(bm, angle_limit=angle, verts=bm.verts, edges=bm.edges)
                info["angle_limit"] = angle
            elif op == "merge_by_distance":
                dist = float(params.get("distance", 0.0001))
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
                info["distance"] = dist
            elif op == "recalc_normals":
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                info["recalculated"] = True
            else:
                raise ValueError(f"Unknown mesh operation: {operation}. Supported: subdivide, bevel, triangulate, decimate, merge_by_distance, recalc_normals")
        except Exception as e:
            bm.free()
            raise RuntimeError(f"mesh_operation {op} failed: {e}")
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        info["object"] = obj.name
        info["vertices"] = len(mesh.vertices)
        info["polygons"] = len(mesh.polygons)
        return info

    def validate_mesh(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh object not found: {object_name}")
        mesh = obj.data
        ngons = tris = quads = degenerate = 0
        for p in mesh.polygons:
            n = len(p.vertices)
            if n > 4:
                ngons += 1
            elif n == 3:
                tris += 1
            elif n == 4:
                quads += 1
            if p.area < 1e-8:
                degenerate += 1
        has_uv = len(mesh.uv_layers) > 0
        non_uniform_scale = any(abs(s - 1.0) > 1e-4 for s in obj.scale)
        return {
            "object": obj.name,
            "vertices": len(mesh.vertices),
            "polygons": len(mesh.polygons),
            "ngons": ngons,
            "tris": tris,
            "quads": quads,
            "degenerate_faces": degenerate,
            "has_uv": has_uv,
            "uv_layers": len(mesh.uv_layers),
            "non_uniform_scale": non_uniform_scale,
            "scale": [float(s) for s in obj.scale],
            "needs_cure": non_uniform_scale or ngons > 0 or degenerate > 0,
        }

    # Geometry Nodes
    def geometry_nodes_create(self, object_name="", modifier_name="GeometryNodes", node_group_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        # Create or reuse node group
        if node_group_name:
            ng = bpy.data.node_groups.get(node_group_name)
            if not ng:
                ng = bpy.data.node_groups.new(name=node_group_name, type='GeometryNodeTree')
        else:
            ng = bpy.data.node_groups.new(name=f"{object_name}_GeoNodes", type='GeometryNodeTree')
        # Ensure Group Input/Output
        if not any(n.type == 'GROUP_INPUT' for n in ng.nodes):
            ng.nodes.new('NodeGroupInput')
        if not any(n.type == 'GROUP_OUTPUT' for n in ng.nodes):
            ng.nodes.new('NodeGroupOutput')
        # Add modifier
        mod = obj.modifiers.new(name=modifier_name, type='NODES')
        mod.node_group = ng
        return {"object": obj.name, "modifier": mod.name, "node_group": ng.name, "nodes": len(ng.nodes)}

    def geometry_nodes_add_node(self, node_group_name="", node_type="GeometryNodeMeshCube"):
        ng = bpy.data.node_groups.get(node_group_name)
        if not ng:
            raise ValueError(f"Node group not found: {node_group_name}")
        node = ng.nodes.new(type=node_type)
        node.location = (len(ng.nodes) * 20, 0)
        return {"node_group": ng.name, "node": node.name, "type": node.type, "total_nodes": len(ng.nodes)}

    def geometry_nodes_link(self, node_group_name="", from_node="", from_socket="Geometry", to_node="", to_socket="Geometry"):
        ng = bpy.data.node_groups.get(node_group_name)
        if not ng:
            raise ValueError(f"Node group not found: {node_group_name}")
        fn = ng.nodes.get(from_node)
        tn = ng.nodes.get(to_node)
        if not fn or not tn:
            raise ValueError(f"Node not found: {from_node} or {to_node}")
        # Find sockets by name
        out_sock = None
        for s in fn.outputs:
            if s.name == from_socket or from_socket in s.name:
                out_sock = s
                break
        if not out_sock and fn.outputs:
            out_sock = fn.outputs[0]
        in_sock = None
        for s in tn.inputs:
            if s.name == to_socket or to_socket in s.name:
                in_sock = s
                break
        if not in_sock and tn.inputs:
            in_sock = tn.inputs[0]
        link = ng.links.new(out_sock, in_sock)
        return {"node_group": ng.name, "link": f"{fn.name}.{out_sock.name} -> {tn.name}.{in_sock.name}"}

    def geometry_nodes_set_param(self, node_group_name="", node_name="", param="", value=None):
        ng = bpy.data.node_groups.get(node_group_name)
        if not ng:
            raise ValueError(f"Node group not found: {node_group_name}")
        node = ng.nodes.get(node_name)
        if not node:
            raise ValueError(f"Node not found: {node_name}")
        # Try inputs then properties
        if hasattr(node, param):
            setattr(node, param, value)
            return {"node": node.name, "param": param, "value": value, "target": "property"}
        # Search inputs
        for inp in node.inputs:
            if inp.name == param or param.lower() in inp.name.lower():
                try:
                    inp.default_value = value
                    return {"node": node.name, "param": param, "value": value, "target": f"input:{inp.name}"}
                except Exception as e:
                    return {"node": node.name, "param": param, "error": str(e)}
        raise ValueError(f"Param {param} not found on {node_name}")

    def geometry_nodes_templates(self):
        return {
            "templates": [
                {"name": "scatter_points", "nodes": ["DistributePointsOnFaces", "InstanceOnPoints"], "use": "Scatter objects on surface"},
                {"name": "extrude_mesh", "nodes": ["ExtrudeMesh", "ScaleElements"], "use": "Procedural extrusion"},
                {"name": "subdivide_mesh", "nodes": ["SubdivideMesh", "SetShadeSmooth"], "use": "Smooth subdivision"},
                {"name": "boolean_mesh", "nodes": ["MeshBoolean", "JoinGeometry"], "use": "Procedural booleans"},
                {"name": "triangulate", "nodes": ["Triangulate"], "use": "Triangulation for export"},
                {"name": "merge_by_distance", "nodes": ["MergeByDistance"], "use": "Cleanup duplicates"},
                {"name": "instance_on_points", "nodes": ["InstanceOnPoints", "RealizeInstances"], "use": "Instancing"},
                {"name": "noise_displace", "nodes": ["SetPosition", "NoiseTexture"], "use": "Noise displacement"},
            ]
        }

    # ── Fase 3: Shader Nodes / UV / PBR ──────────────────────────────

    def shader_create_tree(self, material_name="", clear_existing=True):
        """Ensure material has node tree and return info. Create if not exists."""
        mat = bpy.data.materials.get(material_name)
        if not mat:
            mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nt = mat.node_tree
        if clear_existing:
            # Keep only output + principled if clearing
            for n in list(nt.nodes):
                if n.type not in ('OUTPUT_MATERIAL',):
                    nt.nodes.remove(n)
            if not any(n.type == 'BSDF_PRINCIPLED' for n in nt.nodes):
                principled = nt.nodes.new(type='ShaderNodeBsdfPrincipled')
                principled.location = (0, 0)
                out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if out:
                    nt.links.new(principled.outputs[0], out.inputs[0])
        return {"material": mat.name, "nodes": len(nt.nodes), "links": len(nt.links)}

    def shader_add_node(self, material_name="", node_type="ShaderNodeTexImage", location_x=0, location_y=0):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found or no node tree: {material_name}")
        nt = mat.node_tree
        node = nt.nodes.new(type=node_type)
        node.location = (location_x, location_y)
        return {"material": mat.name, "node": node.name, "type": node.type, "total_nodes": len(nt.nodes)}

    def shader_remove_node(self, material_name="", node_name=""):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        node = nt.nodes.get(node_name)
        if not node:
            raise ValueError(f"Node not found: {node_name}")
        nt.nodes.remove(node)
        return {"material": mat.name, "removed": node_name, "remaining": len(nt.nodes)}

    def shader_link_nodes(self, material_name="", from_node="", from_socket="Color", to_node="", to_socket="Base Color"):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        fn = nt.nodes.get(from_node)
        tn = nt.nodes.get(to_node)
        if not fn or not tn:
            raise ValueError(f"Node not found: {from_node} or {to_node}")
        out_sock = next((s for s in fn.outputs if s.name == from_socket or from_socket.lower() in s.name.lower()), None)
        if not out_sock and fn.outputs:
            out_sock = fn.outputs[0]
        in_sock = next((s for s in tn.inputs if s.name == to_socket or to_socket.lower() in s.name.lower()), None)
        if not in_sock and tn.inputs:
            in_sock = tn.inputs[0]
        link = nt.links.new(out_sock, in_sock)
        return {"material": mat.name, "link": f"{fn.name}.{out_sock.name} -> {tn.name}.{in_sock.name}"}

    def shader_set_node_param(self, material_name="", node_name="", param="", value=None):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        node = nt.nodes.get(node_name)
        if not node:
            raise ValueError(f"Node not found: {node_name}")
        # Try property first
        if hasattr(node, param):
            setattr(node, param, value)
            return {"material": mat.name, "node": node.name, "param": param, "value": value, "target": "property"}
        # Inputs
        for inp in node.inputs:
            if inp.name == param or param.lower() in inp.name.lower():
                try:
                    # Handle color vector vs float
                    if hasattr(inp, "default_value"):
                        dv = inp.default_value
                        if hasattr(dv, "__len__") and isinstance(value, (list, tuple)):
                            dv[:] = value
                        else:
                            inp.default_value = value
                    return {"material": mat.name, "node": node.name, "param": param, "value": value}
                except Exception as e:
                    return {"material": mat.name, "node": node.name, "param": param, "error": str(e)}
        # Image assign special: param == "image" and value is filepath or image name
        if param == "image" and node.type == 'TEX_IMAGE':
            img = bpy.data.images.get(str(value))
            if img:
                node.image = img
                return {"material": mat.name, "node": node.name, "image": img.name}
            # Try load filepath
            try:
                img = bpy.data.images.load(str(value))
                node.image = img
                return {"material": mat.name, "node": node.name, "image": img.name, "loaded": str(value)}
            except Exception as e:
                raise ValueError(f"Cannot set image {value}: {e}")
        raise ValueError(f"Param {param} not found on {node_name}")

    def shader_get_tree(self, material_name=""):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        nodes = [{"name": n.name, "type": n.type, "location": [float(n.location.x), float(n.location.y)]} for n in nt.nodes]
        links = [{"from_node": l.from_node.name, "from_socket": l.from_socket.name, "to_node": l.to_node.name, "to_socket": l.to_socket.name} for l in nt.links]
        return {"material": mat.name, "nodes": nodes, "links": links, "counts": {"nodes": len(nodes), "links": len(links)}}

    def shader_clear_tree(self, material_name=""):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        return {"material": mat.name, "cleared": True, "nodes": 0}

    def shader_duplicate_tree(self, source_material="", new_material_name=""):
        src = bpy.data.materials.get(source_material)
        if not src:
            raise ValueError(f"Source material not found: {source_material}")
        new_mat = src.copy()
        new_mat.name = new_material_name or f"{src.name}_copy"
        return {"source": src.name, "new_material": new_mat.name, "nodes": len(new_mat.node_tree.nodes) if new_mat.node_tree else 0}

    def shader_arrange_nodes(self, material_name=""):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        # Simple grid arrangement
        for i, n in enumerate(nt.nodes):
            n.location = ( (i % 4) * 300 - 600, (i // 4) * -250 + 300 )
        return {"material": mat.name, "arranged": len(nt.nodes)}

    def shader_export_as_code(self, material_name=""):
        mat = bpy.data.materials.get(material_name)
        if not mat or not mat.node_tree:
            raise ValueError(f"Material not found: {material_name}")
        nt = mat.node_tree
        lines = [f"# Shader tree for {mat.name}", f"mat = bpy.data.materials.new('{mat.name}_export')", "mat.use_nodes = True", "nt = mat.node_tree"]
        for n in nt.nodes:
            lines.append(f"n = nt.nodes.new(type='{n.bl_idname}')  # {n.name}")
        for l in nt.links:
            lines.append(f"nt.links.new(nt.nodes['{l.from_node.name}'].outputs['{l.from_socket.name}'], nt.nodes['{l.to_node.name}'].inputs['{l.to_socket.name}'])")
        return {"material": mat.name, "code": "\n".join(lines), "lines": len(lines)}

    # UV handlers
    def uv_unwrap(self, object_name="", method="SMART_PROJECT", margin=0.02):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        # Select and set active
        for o in bpy.context.view_layer.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        prev_mode = obj.mode
        if prev_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_all(action='SELECT')
            if method == "SMART_PROJECT":
                bpy.ops.uv.smart_project(angle_limit=66, island_margin=margin, use_aspect=True, stretch_to_bounds=True)
            elif method == "CUBE_PROJECT":
                bpy.ops.uv.cube_project(cube_size=2.0)
            elif method == "UNWRAP":
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=margin)
            else:
                raise ValueError(f"Unknown unwrap method: {method}")
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data
        return {"object": obj.name, "method": method, "uv_layers": len(mesh.uv_layers), "margin": margin}

    def uv_add_layer(self, object_name="", layer_name="UVMap"):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        mesh = obj.data
        uv = mesh.uv_layers.new(name=layer_name)
        return {"object": obj.name, "uv_layer": uv.name, "total": len(mesh.uv_layers)}

    def uv_pack_islands(self, object_name="", margin=0.02):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        for o in bpy.context.view_layer.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(margin=margin)
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"object": obj.name, "packed": True, "margin": margin}

    def uv_get_info(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        mesh = obj.data
        layers = [{"name": uv.name, "active": uv.active, "active_render": uv.active_render} for uv in mesh.uv_layers]
        return {"object": obj.name, "uv_layers": layers, "count": len(layers), "active": mesh.uv_layers.active.name if mesh.uv_layers.active else None}

    def uv_export_layout(self, object_name="", filepath="/tmp/uv_layout.png", size=1024):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        # Use bpy.ops.uv.export_layout
        for o in bpy.context.view_layer.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.export_layout(filepath=filepath, size=(size, size), opacity=0.25, export_all=True, mode='PNG')
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        exists = os.path.exists(filepath)
        return {"object": obj.name, "filepath": filepath, "exists": exists, "size": size}

    def uv_validate(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        mesh = obj.data
        if len(mesh.uv_layers) == 0:
            return {"object": obj.name, "valid": False, "reason": "no UV layers", "needs_unwrap": True}
        # Check for overlaps via uv area? Simple check: has uv data
        has_uv_data = False
        if mesh.uv_layers.active and mesh.uv_layers.active.data:
            has_uv_data = any(True for _ in mesh.uv_layers.active.data)
        return {"object": obj.name, "valid": True, "uv_layers": len(mesh.uv_layers), "has_data": has_uv_data}

    # PBR handlers
    def pbr_create_material(self, material_name="", base_color=(0.8, 0.8, 0.8, 1.0), metallic=0.0, roughness=0.5):
        mat = bpy.data.materials.get(material_name)
        if not mat:
            mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nt = mat.node_tree
        principled = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not principled:
            principled = nt.nodes.new(type='ShaderNodeBsdfPrincipled')
            principled.location = (0, 0)
            out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not out:
                out = nt.nodes.new(type='ShaderNodeOutputMaterial')
                out.location = (300, 0)
            nt.links.new(principled.outputs[0], out.inputs[0])
        principled.inputs['Base Color'].default_value = base_color if len(base_color)==4 else (*base_color, 1.0)
        principled.inputs['Metallic'].default_value = metallic
        principled.inputs['Roughness'].default_value = roughness
        return {"material": mat.name, "base_color": list(base_color), "metallic": metallic, "roughness": roughness}

    def pbr_assign_material(self, object_name="", material_name="", slot_index=0):
        obj = bpy.data.objects.get(object_name)
        mat = bpy.data.materials.get(material_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        if not mat:
            raise ValueError(f"Material not found: {material_name}")
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            # Ensure slot exists
            while len(obj.data.materials) <= slot_index:
                obj.data.materials.append(None)
            obj.data.materials[slot_index] = mat
        # Also set active
        obj.active_material_index = slot_index
        return {"object": obj.name, "material": mat.name, "slot": slot_index}

    def pbr_pack_orm(self, ao_image_name="", rough_image_name="", metal_image_name="", output_name="ORM", width=1024, height=1024):
        """Pack AO(R), Rough(G), Metal(B) into one ORM image for Godot."""
        import numpy as np
        imgs = {}
        for name in [ao_image_name, rough_image_name, metal_image_name]:
            if name:
                img = bpy.data.images.get(name)
                if img:
                    imgs[name] = img
        if not imgs:
            raise ValueError("No source images found for ORM pack")
        # Create output image
        orm = bpy.data.images.get(output_name)
        if orm:
            bpy.data.images.remove(orm)
        orm = bpy.data.images.new(name=output_name, width=width, height=height, alpha=False, float_buffer=False)
        # Simple: fill with combined channels — if single image, reuse
        # For now create placeholder and pack channels via pixels foreach_set
        # Use first image as base size
        pixels = [0.0] * (width * height * 4)
        # Fill R with AO, G with Rough, B with Metal (default 1.0 if missing)
        # If images exist, sample their pixels scaled (nearest)
        def get_pixel(img, x, y):
            # Clamp and sample
            if not img or not img.pixels:
                return 0.0
            w, h = img.size
            if w == 0 or h == 0:
                return 0.0
            sx = min(w-1, int(x * w / width))
            sy = min(h-1, int(y * h / height))
            idx = (sy * w + sx) * 4
            try:
                return float(img.pixels[idx])
            except:
                return 0.0
        ao_img = bpy.data.images.get(ao_image_name) if ao_image_name else None
        rough_img = bpy.data.images.get(rough_image_name) if rough_image_name else None
        metal_img = bpy.data.images.get(metal_image_name) if metal_image_name else None
        # Vectorized path with numpy when available, fallback to python loop
        try:
            import numpy as np
            # Pre-fetch source pixels as numpy arrays via foreach_get
            def fetch_pixels(img):
                if not img or not img.pixels:
                    return None
                w, h = img.size
                if w == 0 or h == 0:
                    return None
                arr = [0.0] * (w * h * 4)
                # Use foreach_get if available for speed
                try:
                    img.pixels.foreach_get(arr)
                except:
                    # Fallback sequential
                    for i in range(len(arr)):
                        try:
                            arr[i] = img.pixels[i]
                        except:
                            arr[i] = 0.0
                return np.array(arr, dtype=np.float32).reshape((h, w, 4))

            ao_arr = fetch_pixels(ao_img)
            rough_arr = fetch_pixels(rough_img)
            metal_arr = fetch_pixels(metal_img)

            # Build ORM via numpy for target size
            orm_pixels = [0.0] * (width * height * 4)
            # For simplicity, use nearest sampling via numpy indexing when sizes differ
            for y in range(height):
                for x in range(width):
                    idx = (y * width + x) * 4
                    # Sample source arrays with scaling
                    if ao_arr is not None:
                        ah, aw = ao_arr.shape[0], ao_arr.shape[1]
                        sy, sx = min(ah-1, int(y * ah / height)), min(aw-1, int(x * aw / width))
                        r = float(ao_arr[sy, sx, 0])
                    else:
                        r = 1.0
                    if rough_arr is not None:
                        rh, rw = rough_arr.shape[0], rough_arr.shape[1]
                        sy, sx = min(rh-1, int(y * rh / height)), min(rw-1, int(x * rw / width))
                        g = float(rough_arr[sy, sx, 0])
                    else:
                        g = 0.5
                    if metal_arr is not None:
                        mh, mw = metal_arr.shape[0], metal_arr.shape[1]
                        sy, sx = min(mh-1, int(y * mh / height)), min(mw-1, int(x * mw / width))
                        b = float(metal_arr[sy, sx, 0])
                    else:
                        b = 0.0
                    orm_pixels[idx] = r
                    orm_pixels[idx+1] = g
                    orm_pixels[idx+2] = b
                    orm_pixels[idx+3] = 1.0
            orm.pixels.foreach_set(orm_pixels)
        except Exception:
            # Fallback pure python (original)
            for y in range(height):
                for x in range(width):
                    idx = (y * width + x) * 4
                    r = get_pixel(ao_img, x, y) if ao_img else 1.0
                    g = get_pixel(rough_img, x, y) if rough_img else 0.5
                    b = get_pixel(metal_img, x, y) if metal_img else 0.0
                    pixels[idx] = r
                    pixels[idx+1] = g
                    pixels[idx+2] = b
                    pixels[idx+3] = 1.0
            orm.pixels.foreach_set(pixels)
        orm.pack()
        orm.colorspace_settings.name = 'Non-Color'
        return {"orm_image": orm.name, "width": width, "height": height, "sources": {"ao": ao_image_name, "rough": rough_image_name, "metal": metal_image_name}}

    def pbr_bake_texture(self, object_name="", bake_type="AO", size=1024, filepath="/tmp/bake.png", samples=32):
        """Bake Cycles texture for object. bake_type: AO, DIFFUSE, NORMAL, COMBINED etc."""
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        # Ensure cycles
        bpy.context.scene.render.engine = 'CYCLES'
        bpy.context.scene.cycles.samples = samples
        # Create image
        img_name = f"{object_name}_{bake_type}_bake"
        img = bpy.data.images.get(img_name)
        if img:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name=img_name, width=size, height=size, alpha=False, float_buffer=False)
        img.colorspace_settings.name = 'Non-Color' if bake_type in ('AO', 'NORMAL', 'ROUGHNESS') else 'sRGB'
        # Create temp material with image node for bake target
        mat = obj.active_material
        if not mat:
            mat = bpy.data.materials.new(name=f"{object_name}_bake_mat")
            mat.use_nodes = True
            obj.data.materials.append(mat)
        nt = mat.node_tree
        bake_node = nt.nodes.new(type='ShaderNodeTexImage')
        bake_node.image = img
        bake_node.select = True
        nt.nodes.active = bake_node
        # Select object
        for o in bpy.context.view_layer.objects:
            o.select_set(o == obj)
        bpy.context.view_layer.objects.active = obj
        # Map bake type
        bake_map = {"AO": "AO", "DIFFUSE": "DIFFUSE", "NORMAL": "NORMAL", "COMBINED": "COMBINED", "ROUGHNESS": "ROUGHNESS", "EMIT": "EMIT"}
        bt = bake_map.get(bake_type.upper(), "AO")
        try:
            bpy.ops.object.bake(type=bt, use_clear=True, margin=16)
        except Exception as e:
            # Cleanup node
            nt.nodes.remove(bake_node)
            raise RuntimeError(f"Bake failed ({bt}): {e}")
        # Save
        img.filepath_raw = filepath
        img.file_format = 'PNG'
        img.save()
        # Keep packed
        img.pack()
        # Remove temp bake node
        nt.nodes.remove(bake_node)
        return {"object": obj.name, "bake_type": bt, "image": img.name, "filepath": filepath, "size": size, "samples": samples}

    # ── Fase 4: Rigging & Animation ────────────────────────────────

    def rig_create_armature(self, name="Armature", location=(0,0,0)):
        arm_data = bpy.data.armatures.new(name)
        obj = bpy.data.objects.new(name, arm_data)
        obj.location = location
        bpy.context.collection.objects.link(obj)
        return {"armature": obj.name, "data": arm_data.name, "bones": 0}

    def rig_add_bone(self, armature_name="", bone_name="Bone", head=(0,0,0), tail=(0,1,0), parent=""):
        obj = bpy.data.objects.get(armature_name)
        if not obj or obj.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        bpy.context.view_layer.objects.active = obj
        prev_mode = bpy.context.mode
        if prev_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        try:
            eb = obj.data.edit_bones.new(bone_name)
            eb.head = head
            eb.tail = tail
            if parent:
                pb = obj.data.edit_bones.get(parent)
                if pb:
                    eb.parent = pb
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
        return {"armature": obj.name, "bone": bone_name, "parent": parent, "bones": len(obj.data.bones)}

    def rig_set_bone_params(self, armature_name="", bone_name="", params=None):
        obj = bpy.data.objects.get(armature_name)
        if not obj or obj.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        bone = obj.pose.bones.get(bone_name) or obj.data.bones.get(bone_name)
        if not bone:
            raise ValueError(f"Bone not found: {bone_name}")
        applied = {}
        for k, v in (params or {}).items():
            try:
                if hasattr(bone, k):
                    setattr(bone, k, v)
                    applied[k] = v
            except Exception as e:
                applied[k] = f"error: {e}"
        return {"armature": obj.name, "bone": bone_name, "applied": applied}

    def rig_parent_to_armature(self, object_name="", armature_name="", with_weights="ARMATURE_AUTO"):
        obj = bpy.data.objects.get(object_name)
        arm = bpy.data.objects.get(armature_name)
        if not obj or not arm:
            raise ValueError(f"Object or armature not found: {object_name}, {armature_name}")
        for o in bpy.context.view_layer.objects:
            o.select_set(o in (obj, arm))
        bpy.context.view_layer.objects.active = arm
        try:
            if with_weights == "ARMATURE_AUTO":
                bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            elif with_weights == "ARMATURE_ENVELOPE":
                bpy.ops.object.parent_set(type='ARMATURE_ENVELOPE')
            else:
                obj.parent = arm
                mod = obj.modifiers.new(name="Armature", type='ARMATURE')
                mod.object = arm
        except Exception as e:
            raise RuntimeError(f"Parent to armature failed: {e}")
        return {"object": obj.name, "armature": arm.name, "method": with_weights}

    def rig_add_ik_constraint(self, armature_name="", bone_name="", target_object="", chain_count=2):
        obj = bpy.data.objects.get(armature_name)
        if not obj or obj.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        pb = obj.pose.bones.get(bone_name)
        if not pb:
            raise ValueError(f"Pose bone not found: {bone_name}")
        target = bpy.data.objects.get(target_object)
        c = pb.constraints.new(type='IK')
        c.target = target
        c.chain_count = chain_count
        return {"armature": obj.name, "bone": bone_name, "constraint": c.name, "target": target_object, "chain_count": chain_count}

    def rig_create_preset(self, preset="basic_chain", name="RigPreset"):
        # Simple presets: basic_chain (3 bones), leg, arm
        if preset == "basic_chain":
            arm = self.rig_create_armature(name=name)
            self.rig_add_bone(arm["armature"], "Bone", (0,0,0), (0,1,0))
            self.rig_add_bone(arm["armature"], "Bone.001", (0,1,0), (0,2,0), parent="Bone")
            self.rig_add_bone(arm["armature"], "Bone.002", (0,2,0), (0,3,0), parent="Bone.001")
            return {"armature": arm["armature"], "preset": preset, "bones": 3}
        raise ValueError(f"Unknown rig preset: {preset}. Available: basic_chain")

    def rig_weight_transfer(self, source_object="", target_object=""):
        src = bpy.data.objects.get(source_object)
        dst = bpy.data.objects.get(target_object)
        if not src or not dst:
            raise ValueError(f"Objects not found: {source_object}, {target_object}")
        # Use data transfer modifier for weights
        for o in bpy.context.view_layer.objects:
            o.select_set(o in (src, dst))
        bpy.context.view_layer.objects.active = dst
        try:
            mod = dst.modifiers.new(name="DataTransfer", type='DATA_TRANSFER')
            mod.object = src
            mod.use_vert_data = True
            mod.data_types_verts = {'VGROUP_WEIGHTS'}
            mod.vert_mapping = 'NEAREST'
            bpy.ops.object.datalayout_transfer(modifier=mod.name)
            dst.modifiers.remove(mod)
        except Exception as e:
            raise RuntimeError(f"Weight transfer failed: {e}")
        return {"source": src.name, "target": dst.name, "transferred": True}

    def rig_list_armatures(self):
        arms = [{"name": o.name, "bones": len(o.data.bones) if o.type=='ARMATURE' and o.data else 0} for o in bpy.data.objects if o.type=='ARMATURE']
        return {"armatures": arms, "count": len(arms)}

    # Animation handlers
    def anim_insert_keyframe(self, object_name="", data_path="location", frame=1, value=None):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        # Set value if provided
        if value is not None:
            try:
                # Handle location/rotation/scale tuple
                if data_path in ("location", "rotation_euler", "scale"):
                    getattr(obj, data_path)[:] = value
                elif "." in data_path:
                    # Nested like pose.bones["Bone"].location
                    pass
                else:
                    setattr(obj, data_path, value)
            except: pass
        bpy.context.view_layer.objects.active = obj
        obj.keyframe_insert(data_path=data_path, frame=frame)
        return {"object": obj.name, "data_path": data_path, "frame": frame, "value": value}

    def anim_delete_keyframe(self, object_name="", data_path="location", frame=1):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        obj.keyframe_delete(data_path=data_path, frame=frame)
        return {"object": obj.name, "data_path": data_path, "frame": frame, "deleted": True}

    def anim_set_timeline(self, frame_start=1, frame_end=250, current_frame=1, fps=24):
        scene = bpy.context.scene
        scene.frame_start = frame_start
        scene.frame_end = frame_end
        scene.frame_current = current_frame
        scene.render.fps = fps
        return {"frame_start": frame_start, "frame_end": frame_end, "current": current_frame, "fps": fps}

    def anim_create_action(self, object_name="", action_name="Action"):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        action = bpy.data.actions.new(name=action_name)
        if not obj.animation_data:
            obj.animation_data_create()
        obj.animation_data.action = action
        return {"object": obj.name, "action": action.name}

    def anim_assign_action(self, object_name="", action_name=""):
        obj = bpy.data.objects.get(object_name)
        action = bpy.data.actions.get(action_name)
        if not obj or not action:
            raise ValueError(f"Object or action not found: {object_name}, {action_name}")
        if not obj.animation_data:
            obj.animation_data_create()
        obj.animation_data.action = action
        return {"object": obj.name, "action": action.name}

    def anim_set_interpolation(self, object_name="", data_path="location", interpolation="BEZIER"):
        obj = bpy.data.objects.get(object_name)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            raise ValueError(f"No animation data for {object_name}")
        action = obj.animation_data.action
        updated = 0
        for fc in action.fcurves:
            if data_path in fc.data_path:
                for kp in fc.keyframe_points:
                    kp.interpolation = interpolation
                    updated += 1
        return {"object": obj.name, "data_path": data_path, "interpolation": interpolation, "updated": updated}

    def anim_bake(self, object_name="", frame_start=1, frame_end=60):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        bpy.context.view_layer.objects.active = obj
        # Use bpy.ops.nla.bake
        try:
            bpy.ops.nla.bake(frame_start=frame_start, frame_end=frame_end, only_selected=False, visual_keying=True, clear_constraints=False, bake_types={'OBJECT'})
        except Exception as e:
            raise RuntimeError(f"Bake failed: {e}")
        return {"object": obj.name, "baked": True, "frames": [frame_start, frame_end]}

    def anim_create_nla_strip(self, object_name="", strip_name="Strip", frame_start=1):
        obj = bpy.data.objects.get(object_name)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            raise ValueError(f"No action to push for {object_name}")
        action = obj.animation_data.action
        if not obj.animation_data.nla_tracks:
            track = obj.animation_data.nla_tracks.new()
        else:
            track = obj.animation_data.nla_tracks[0]
        # Push action to NLA
        track.strips.new(name=strip_name, start=frame_start, action=action)
        # Optionally add -loop suffix for Godot
        return {"object": obj.name, "strip": strip_name, "action": action.name, "frame_start": frame_start}

    def anim_copy_keyframes(self, source_object="", target_object="", data_path="location"):
        src = bpy.data.objects.get(source_object)
        dst = bpy.data.objects.get(target_object)
        if not src or not dst:
            raise ValueError(f"Objects not found: {source_object}, {target_object}")
        if not src.animation_data or not src.animation_data.action:
            raise ValueError(f"No action on source {source_object}")
        # Simple: assign same action
        action = src.animation_data.action
        if not dst.animation_data:
            dst.animation_data_create()
        dst.animation_data.action = action
        return {"source": src.name, "target": dst.name, "action": action.name, "data_path": data_path}

    def anim_clear(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        if obj.animation_data:
            obj.animation_data_clear()
        return {"object": obj.name, "cleared": True}

    def anim_get_info(self, object_name=""):
        obj = bpy.data.objects.get(object_name)
        if not obj:
            raise ValueError(f"Object not found: {object_name}")
        info = {"object": obj.name, "has_animation_data": bool(obj.animation_data)}
        if obj.animation_data:
            ad = obj.animation_data
            info["action"] = ad.action.name if ad.action else None
            info["nla_tracks"] = len(ad.nla_tracks)
            if ad.action:
                info["fcurves"] = len(ad.action.fcurves)
                info["frame_range"] = [float(ad.action.frame_range[0]), float(ad.action.frame_range[1])]
        return info

    def anim_set_graph_handles(self, object_name="", handle_type="AUTO_CLAMPED"):
        # Set handle type for all keyframes
        obj = bpy.data.objects.get(object_name)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            raise ValueError(f"No animation for {object_name}")
        updated = 0
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.handle_left_type = handle_type
                kp.handle_right_type = handle_type
                updated += 1
        return {"object": obj.name, "handle_type": handle_type, "updated": updated}

    # ── Fase 5: Lights / Camera / Render ──────────────────────────

    def light_create(self, light_type="POINT", name="Light", location=(0,0,3), energy=1000, color=(1,1,1)):
        data = bpy.data.lights.new(name=name, type=light_type)
        data.energy = energy
        data.color = color
        obj = bpy.data.objects.new(name=name, object_data=data)
        obj.location = location
        bpy.context.collection.objects.link(obj)
        return {"light": obj.name, "type": light_type, "energy": energy, "color": list(color)}

    def light_set_params(self, light_name="", params=None):
        obj = bpy.data.objects.get(light_name)
        if not obj or obj.type != 'LIGHT':
            # Try data
            data = bpy.data.lights.get(light_name)
            if not data:
                raise ValueError(f"Light not found: {light_name}")
            target = data
            obj_name = data.name
        else:
            target = obj.data
            obj_name = obj.name
        applied = {}
        for k, v in (params or {}).items():
            try:
                if hasattr(target, k):
                    setattr(target, k, v)
                    applied[k] = v
                elif obj and hasattr(obj, k):
                    setattr(obj, k, v)
                    applied[k] = v
            except Exception as e:
                applied[k] = f"error: {e}"
        return {"light": obj_name, "applied": applied}

    def light_set_world_hdri(self, filepath="", strength=1.0):
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        # Find or create env tex
        env = next((n for n in nt.nodes if n.type == 'TEX_ENVIRONMENT'), None)
        if not env:
            env = nt.nodes.new(type='ShaderNodeTexEnvironment')
            env.location = (-300, 0)
            bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
            if bg:
                nt.links.new(env.outputs[0], bg.inputs[0])
        if filepath:
            try:
                img = bpy.data.images.load(filepath)
                env.image = img
            except Exception as e:
                return {"error": f"Failed to load HDRI {filepath}: {e}"}
        bg = next((n for n in nt.nodes if n.type == 'BACKGROUND'), None)
        if bg:
            bg.inputs[1].default_value = strength
        return {"world": world.name, "hdri": filepath, "strength": strength}

    def light_setup_studio(self, preset="3_point"):
        # Create 3-point classic
        created = []
        if preset == "3_point":
            for name, loc, energy in [("Key", (5,-5,5), 2000), ("Fill", (-5,-5,3), 800), ("Rim", (0,5,4), 1200)]:
                if name not in [o.name for o in bpy.data.objects]:
                    r = self.light_create("AREA", name, loc, energy)
                    created.append(r)
        return {"preset": preset, "created": created}

    def light_list(self):
        lights = [{"name": o.name, "type": o.data.type, "energy": o.data.energy} for o in bpy.data.objects if o.type=='LIGHT']
        return {"lights": lights, "count": len(lights), "world": bpy.context.scene.world.name if bpy.context.scene.world else None}

    def camera_create(self, name="Camera", location=(7,-7,5), rotation_euler=(0.9,0,0.8), lens=50):
        data = bpy.data.cameras.new(name=name)
        data.lens = lens
        obj = bpy.data.objects.new(name=name, object_data=data)
        obj.location = location
        obj.rotation_euler = rotation_euler
        bpy.context.collection.objects.link(obj)
        return {"camera": obj.name, "lens": lens, "location": list(location)}

    def camera_set_params(self, camera_name="", params=None):
        obj = bpy.data.objects.get(camera_name)
        if not obj or obj.type != 'CAMERA':
            raise ValueError(f"Camera not found: {camera_name}")
        cam = obj.data
        applied = {}
        for k, v in (params or {}).items():
            try:
                if hasattr(cam, k):
                    setattr(cam, k, v)
                    applied[k] = v
                elif hasattr(obj, k):
                    setattr(obj, k, v)
                    applied[k] = v
            except Exception as e:
                applied[k] = f"error: {e}"
        return {"camera": obj.name, "applied": applied}

    def camera_set_view(self, camera_name=""):
        obj = bpy.data.objects.get(camera_name)
        if not obj or obj.type != 'CAMERA':
            raise ValueError(f"Camera not found: {camera_name}")
        bpy.context.scene.camera = obj
        # Set viewport to camera
        for area in bpy.context.screen.areas if bpy.context.screen else []:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.camera = obj
                        space.region_3d.view_perspective = 'CAMERA'
        return {"camera": obj.name, "active": True}

    def camera_track_to(self, camera_name="", target_object=""):
        cam = bpy.data.objects.get(camera_name)
        target = bpy.data.objects.get(target_object)
        if not cam or not target:
            raise ValueError(f"Camera or target not found: {camera_name}, {target_object}")
        c = cam.constraints.new(type='TRACK_TO')
        c.target = target
        c.track_axis = 'TRACK_NEGATIVE_Z'
        c.up_axis = 'UP_Y'
        return {"camera": cam.name, "target": target.name, "constraint": c.name}

    def camera_create_rig(self, target_object="", rig_name="CameraRig"):
        # Create empty as target + camera parented
        empty = bpy.data.objects.new(name=rig_name, object_data=None)
        empty.empty_display_type = 'PLAIN_AXES'
        if target_object:
            target = bpy.data.objects.get(target_object)
            if target:
                empty.location = target.location
        bpy.context.collection.objects.link(empty)
        cam = self.camera_create(name=f"{rig_name}_Camera", location=(7,-7,5))
        cam_obj = bpy.data.objects.get(cam["camera"])
        cam_obj.parent = empty
        return {"rig": empty.name, "camera": cam_obj.name, "target": target_object}

    def camera_render(self, camera_name="", filepath="/tmp/camera_render.png"):
        if camera_name:
            obj = bpy.data.objects.get(camera_name)
            if obj and obj.type == 'CAMERA':
                bpy.context.scene.camera = obj
        bpy.context.scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        exists = os.path.exists(filepath)
        return {"camera": camera_name or (bpy.context.scene.camera.name if bpy.context.scene.camera else None), "filepath": filepath, "exists": exists}

    def camera_list(self):
        cams = [{"name": o.name, "lens": o.data.lens, "active": o == bpy.context.scene.camera} for o in bpy.data.objects if o.type=='CAMERA']
        return {"cameras": cams, "count": len(cams), "active": bpy.context.scene.camera.name if bpy.context.scene.camera else None}

    def render_set_engine(self, engine="CYCLES"):
        bpy.context.scene.render.engine = engine
        return {"engine": engine}

    def render_set_settings(self, resolution_x=1920, resolution_y=1080, resolution_percentage=100, samples=128, filepath="/tmp/render.png"):
        scene = bpy.context.scene
        scene.render.resolution_x = resolution_x
        scene.render.resolution_y = resolution_y
        scene.render.resolution_percentage = resolution_percentage
        if scene.render.engine == 'CYCLES':
            scene.cycles.samples = samples
        scene.render.filepath = filepath
        return {"resolution": [resolution_x, resolution_y], "percentage": resolution_percentage, "samples": samples, "filepath": filepath, "engine": scene.render.engine}

    def render_set_output(self, filepath="/tmp/render.png", file_format="PNG"):
        bpy.context.scene.render.filepath = filepath
        bpy.context.scene.render.image_settings.file_format = file_format
        return {"filepath": filepath, "format": file_format}

    def render_get_info(self):
        scene = bpy.context.scene
        return {"engine": scene.render.engine, "resolution": [scene.render.resolution_x, scene.render.resolution_y], "percentage": scene.render.resolution_percentage, "filepath": scene.render.filepath, "fps": scene.render.fps, "samples": scene.cycles.samples if scene.render.engine=='CYCLES' else None}

    # ── Fase 6: Batch / IO / Diagnostics / Scene Utils / Presets / Godot Polish ──

    def batch_execute_on_objects(self, code="", only_selected=False):
        """Execute code on each object (batch). code runs with variable `obj`."""
        targets = list(bpy.context.selected_objects) if only_selected else list(bpy.context.scene.objects)
        results = []
        for obj in targets:
            try:
                namespace = {"bpy": bpy, "bmesh": bmesh, "obj": obj}
                exec(code, namespace)
                results.append({"object": obj.name, "status": "ok"})
            except Exception as e:
                results.append({"object": obj.name, "status": "error", "error": str(e)})
        return {"total": len(targets), "results": results}

    def batch_render_queue(self, filepaths=None):
        """Render queue: set filepath per entry and render. Simplified."""
        filepaths = filepaths or []
        rendered = []
        for fp in filepaths:
            bpy.context.scene.render.filepath = fp
            try:
                bpy.ops.render.render(write_still=True)
                rendered.append({"filepath": fp, "success": os.path.exists(fp)})
            except Exception as e:
                rendered.append({"filepath": fp, "success": False, "error": str(e)})
        return {"queue": rendered, "count": len(rendered)}

    def batch_import(self, directory="", pattern="*.fbx"):
        """Import all matching files from directory."""
        import glob as _glob
        files = _glob.glob(os.path.join(directory, pattern))
        imported = []
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            try:
                if ext == ".fbx":
                    bpy.ops.import_scene.fbx(filepath=f)
                elif ext in (".gltf", ".glb"):
                    bpy.ops.import_scene.gltf(filepath=f)
                elif ext == ".obj":
                    bpy.ops.import_scene.obj(filepath=f)
                elif ext == ".stl":
                    bpy.ops.import_mesh.stl(filepath=f)
                elif ext == ".ply":
                    bpy.ops.import_mesh.ply(filepath=f)
                elif ext == ".dae":
                    bpy.ops.wm.collada_import(filepath=f)
                elif ext == ".abc":
                    bpy.ops.wm.alembic_import(filepath=f)
                elif ext == ".usd":
                    bpy.ops.wm.usd_import(filepath=f)
                elif ext == ".blend":
                    with bpy.data.libraries.load(f, link=False) as (data_from, data_to):
                        data_to.objects = data_from.objects
                    for obj in data_to.objects:
                        if obj:
                            bpy.context.collection.objects.link(obj)
                else:
                    continue
                imported.append({"file": f, "success": True})
            except Exception as e:
                imported.append({"file": f, "success": False, "error": str(e)})
        return {"directory": directory, "pattern": pattern, "imported": imported, "count": len(imported)}

    def batch_export(self, directory="/tmp/batch_export", export_format="GLB", only_selected=False):
        """Export each selected object as separate file."""
        os.makedirs(directory, exist_ok=True)
        targets = list(bpy.context.selected_objects) if only_selected else [o for o in bpy.context.scene.objects if o.type=='MESH']
        exported = []
        for obj in targets:
            for o in bpy.context.view_layer.objects:
                o.select_set(o == obj)
            bpy.context.view_layer.objects.active = obj
            fp = os.path.join(directory, f"{obj.name}.{export_format.lower()}")
            try:
                if export_format == "GLB":
                    bpy.ops.export_scene.gltf(filepath=fp, export_format='GLB', use_selection=True, export_apply=True)
                elif export_format == "FBX":
                    bpy.ops.export_scene.fbx(filepath=fp, use_selection=True, apply_scale_options='FBX_SCALE_NONE')
                elif export_format == "OBJ":
                    bpy.ops.export_scene.obj(filepath=fp, use_selection=True)
                elif export_format == "STL":
                    bpy.ops.export_mesh.stl(filepath=fp, use_selection=True)
                elif export_format == "PLY":
                    bpy.ops.export_mesh.ply(filepath=fp, use_selection=True)
                exported.append({"object": obj.name, "filepath": fp, "success": os.path.exists(fp)})
            except Exception as e:
                exported.append({"object": obj.name, "filepath": fp, "success": False, "error": str(e)})
        return {"directory": directory, "format": export_format, "exported": exported, "count": len(exported)}

    def io_import_file(self, filepath="", format="AUTO"):
        ext = os.path.splitext(filepath)[1].lower() if format=="AUTO" else f".{format.lower()}"
        try:
            if ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=filepath)
            elif ext in (".gltf",".glb"):
                bpy.ops.import_scene.gltf(filepath=filepath)
            elif ext == ".obj":
                bpy.ops.import_scene.obj(filepath=filepath)
            elif ext == ".stl":
                bpy.ops.import_mesh.stl(filepath=filepath)
            elif ext == ".ply":
                bpy.ops.import_mesh.ply(filepath=filepath)
            elif ext == ".dae":
                bpy.ops.wm.collada_import(filepath=filepath)
            elif ext == ".abc":
                bpy.ops.wm.alembic_import(filepath=filepath)
            elif ext == ".usd":
                bpy.ops.wm.usd_import(filepath=filepath)
            else:
                raise ValueError(f"Unsupported format: {ext}")
            return {"filepath": filepath, "format": ext, "success": True}
        except Exception as e:
            raise RuntimeError(f"Import failed {filepath}: {e}")

    def io_export_file(self, filepath="", format="GLB", use_selection=False):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        try:
            if format == "GLB":
                bpy.ops.export_scene.gltf(filepath=filepath, export_format='GLB', use_selection=use_selection, export_apply=True)
            elif format == "FBX":
                bpy.ops.export_scene.fbx(filepath=filepath, use_selection=use_selection)
            elif format == "OBJ":
                bpy.ops.export_scene.obj(filepath=filepath, use_selection=use_selection)
            elif format == "STL":
                bpy.ops.export_mesh.stl(filepath=filepath, use_selection=use_selection)
            elif format == "PLY":
                bpy.ops.export_mesh.ply(filepath=filepath, use_selection=use_selection)
            elif format == "DAE":
                bpy.ops.wm.collada_export(filepath=filepath, selected=use_selection)
            elif format == "ABC":
                bpy.ops.wm.alembic_export(filepath=filepath, selected=use_selection)
            elif format == "USD":
                bpy.ops.wm.usd_export(filepath=filepath, selected_objects_only=use_selection)
            else:
                raise ValueError(f"Unsupported export format: {format}")
            return {"filepath": filepath, "format": format, "success": os.path.exists(filepath), "size": os.path.getsize(filepath) if os.path.exists(filepath) else 0}
        except Exception as e:
            raise RuntimeError(f"Export failed {filepath}: {e}")

    def io_list_formats(self):
        return {"import": ["FBX","GLTF","GLB","OBJ","STL","PLY","DAE","ABC","USD","BLEND"], "export": ["GLB","GLTF_SEPARATE","FBX","OBJ","STL","PLY","DAE","ABC","USD"], "total": 9}

    def diag_check_rig_health(self, armature_name=""):
        obj = bpy.data.objects.get(armature_name)
        if not obj or obj.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        issues = []
        for bone in obj.data.bones:
            if not bone.use_deform:
                issues.append(f"{bone.name}: non-deform")
            if bone.length < 1e-4:
                issues.append(f"{bone.name}: zero length")
        # Check meshes parented (optimized: early exit, limit)
        for o in bpy.data.objects:
            if o.type=='MESH' and o.parent == obj:
                if not o.vertex_groups:
                    issues.append(f"{o.name}: no vertex groups")
                    continue
                # Check up to first unweighted verts, limited to avoid O(n^3)
                for v in o.data.vertices:
                    has_weight = False
                    for g in v.groups:
                        if g.weight > 0:
                            has_weight = True
                            break
                    if not has_weight:
                        issues.append(f"{o.name}: vertex {v.index} unweighted")
                        break
                if len(issues) > 20:
                    issues.append("... truncated, more issues omitted")
                    break
        return {"armature": obj.name, "issues": issues, "healthy": len(issues)==0, "bones": len(obj.data.bones)}

    def diag_validate_armature(self, armature_name=""):
        return self.diag_check_rig_health(armature_name)

    def diag_fix_rig(self, armature_name=""):
        obj = bpy.data.objects.get(armature_name)
        if not obj or obj.type != 'ARMATURE':
            raise ValueError(f"Armature not found: {armature_name}")
        fixed = []
        for bone in obj.data.bones:
            if bone.length < 1e-4:
                # Extend tail
                try:
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='EDIT')
                    eb = obj.data.edit_bones.get(bone.name)
                    if eb:
                        eb.tail = (eb.head.x, eb.head.y+0.1, eb.head.z)
                        fixed.append(bone.name)
                    bpy.ops.object.mode_set(mode='OBJECT')
                except: pass
        return {"armature": obj.name, "fixed": fixed, "count": len(fixed)}

    def diag_get_rig_report(self, armature_name=""):
        health = self.diag_check_rig_health(armature_name)
        obj = bpy.data.objects.get(armature_name)
        # Collect meshes
        meshes = [o.name for o in bpy.data.objects if o.type=='MESH' and o.parent == obj]
        return {"armature": armature_name, "health": health, "meshes": meshes, "vertex_groups": {o.name: len(o.vertex_groups) for o in bpy.data.objects if o.name in meshes}}

    def scene_clean(self, purge_unused=True):
        before = {"objects": len(bpy.data.objects), "materials": len(bpy.data.materials), "meshes": len(bpy.data.meshes), "images": len(bpy.data.images)}
        if purge_unused:
            bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        after = {"objects": len(bpy.data.objects), "materials": len(bpy.data.materials), "meshes": len(bpy.data.meshes), "images": len(bpy.data.images)}
        return {"before": before, "after": after, "purged": {k: before[k]-after[k] for k in before}}

    def scene_organize_collections(self, prefix="GEO_"):
        # Move meshes to collection named prefix
        col = bpy.data.collections.get(prefix) or bpy.data.collections.new(prefix)
        if col.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(col)
        moved = []
        for obj in bpy.data.objects:
            if obj.type=='MESH' and obj.name not in col.objects:
                # Move
                for c in obj.users_collection:
                    c.objects.unlink(obj)
                col.objects.link(obj)
                moved.append(obj.name)
        return {"collection": col.name, "moved": moved, "count": len(moved)}

    def scene_merge(self, blend_filepath="", link=False):
        if not os.path.exists(blend_filepath):
            raise ValueError(f"Blend file not found: {blend_filepath}")
        with bpy.data.libraries.load(blend_filepath, link=link) as (data_from, data_to):
            data_to.objects = data_from.objects
        linked = []
        for obj in data_to.objects:
            if obj:
                bpy.context.collection.objects.link(obj)
                linked.append(obj.name)
        return {"blend": blend_filepath, "imported": linked, "count": len(linked)}

    def scene_get_stats(self):
        return {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "armatures": len([o for o in bpy.data.objects if o.type=='ARMATURE']),
            "lights": len([o for o in bpy.data.objects if o.type=='LIGHT']),
            "cameras": len([o for o in bpy.data.objects if o.type=='CAMERA']),
            "images": len(bpy.data.images),
            "collections": len(bpy.data.collections),
            "is_dirty": bpy.data.is_dirty,
            "filepath": bpy.data.filepath,
        }

    def preset_apply(self, preset="studio_lighting"):
        if preset == "studio_lighting":
            return self.light_setup_studio("3_point")
        elif preset == "turntable":
            # Create turntable animation: rotate object 360 over 120 frames
            return {"preset": preset, "hint": "Use anim_insert_keyframe on Z rotation frame 1 and 120"}
        elif preset == "character_base":
            return self.rig_create_preset("basic_chain", "CharacterRig")
        raise ValueError(f"Unknown preset: {preset}. Available: studio_lighting, turntable, character_base")

    def preset_list(self):
        return {"presets": ["studio_lighting","turntable","character_base","godot_prop","godot_character"], "count": 5}

    def preset_create_from_scene(self, preset_name="MyPreset"):
        # Save current scene stats as preset json in data/presets
        stats = self.scene_get_stats()
        lights = self.light_list()
        # Write to file alongside addon
        path = os.path.join(os.path.dirname(__file__), "data", "presets", "custom", f"{preset_name}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"name": preset_name, "stats": stats, "lights": lights}, f, indent=2)
        return {"preset": preset_name, "filepath": path, "stats": stats}

    def preset_get_hint(self, context="modeling"):
        hints = {
            "modeling": "Use modifiers non-destructively; apply only before export. Triangulate before Godot.",
            "texturing": "Principled BSDF only survives glTF; bake procedurals. ORM pack Non-Color.",
            "rigging": "Apply armature scale before weight paint; 4 weights max for Godot.",
            "export": "Run cure_scene + godot_validate_scene before godot_export_glb. 1 unit = 1 meter.",
        }
        return {"context": context, "hint": hints.get(context, "No hint for this context")}

    # Godot polish
    def godot_setup_collision(self, object_name="", collision_type="-colonly"):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        # Duplicate and rename
        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        new_obj.name = f"{obj.name}{collision_type}"
        new_obj.data.name = f"{obj.data.name}{collision_type}"
        bpy.context.collection.objects.link(new_obj)
        # Decimate for collision simplification if -colonly
        if collision_type in ("-colonly","-convcolonly"):
            mod = new_obj.modifiers.new(name="Decimate", type='DECIMATE')
            mod.ratio = 0.3
            mod.decimate_type = 'COLLAPSE'
        return {"source": obj.name, "collision": new_obj.name, "type": collision_type, "note": "Godot imports as StaticBody3D/CollisionShape3D via suffix"}

    def godot_setup_lod(self, object_name="", levels=[0.5,0.25]):
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type != 'MESH':
            raise ValueError(f"Mesh not found: {object_name}")
        lods = []
        for i, ratio in enumerate(levels):
            lod = obj.copy()
            lod.data = obj.data.copy()
            lod.name = f"{obj.name}_LOD{i+1}"
            lod.data.name = f"{obj.data.name}_LOD{i+1}"
            bpy.context.collection.objects.link(lod)
            mod = lod.modifiers.new(name="Decimate", type='DECIMATE')
            mod.ratio = ratio
            mod.decimate_type = 'COLLAPSE'
            # Apply? Keep non-destructive
            lods.append({"name": lod.name, "ratio": ratio})
        return {"source": obj.name, "lods": lods, "count": len(lods)}

    def godot_check_material_compatibility(self, object_name=""):
        objs = [bpy.data.objects.get(object_name)] if object_name else [o for o in bpy.data.objects if o.type=='MESH']
        issues = []
        for obj in objs:
            if not obj: continue
            for slot in obj.material_slots:
                mat = slot.material
                if not mat or not mat.use_nodes:
                    issues.append(f"{obj.name}/{mat.name if mat else 'None'}: no nodes")
                    continue
                nt = mat.node_tree
                # Check Principled → Output
                principled = next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'), None)
                output = next((n for n in nt.nodes if n.type=='OUTPUT_MATERIAL'), None)
                if not principled:
                    issues.append(f"{obj.name}/{mat.name}: no Principled BSDF — won't export PBR")
                if not output:
                    issues.append(f"{obj.name}/{mat.name}: no Material Output")
                # Check procedural nodes that won't bake
                proc = [n for n in nt.nodes if n.type in ('TEX_NOISE','TEX_VORONOI','TEX_MUSGRAVE')]
                if proc:
                    issues.append(f"{obj.name}/{mat.name}: procedural {proc[0].type} needs bake")
        return {"checked": len(objs), "issues": issues, "compatible": len(issues)==0}

    def godot_batch_export(self, directory="/tmp/godot_batch", export_format="GLB"):
        return self.batch_export(directory=directory, export_format=export_format, only_selected=False)

    # ── Insights Free: high-level native tools ───────────────────────

    def reset_scene_clean(self):
        """Limpia mallas, materiales, texturas, luces, cámaras sin read_factory_settings (sandbox-safe)."""
        before = {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials), "images": len(bpy.data.images), "lights": len(bpy.data.lights), "cameras": len(bpy.data.cameras)}
        # Delete all objects (unlink from collections first)
        for obj in list(bpy.data.objects):
            # Unlink from all collections
            for col in list(obj.users_collection):
                try:
                    col.objects.unlink(obj)
                except: pass
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except: pass
        # Purge orphan data blocks (materials, meshes, images, etc.) — no read_factory_settings
        for _ in range(3):  # multiple passes for dependencies
            try:
                bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
            except:
                break
        # Ensure default world and collection
        if not bpy.context.scene.collection.children:
            pass
        # Create default cube light camera if scene empty? Keep empty per spec (clean)
        after = {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials), "images": len(bpy.data.images), "lights": len(bpy.data.lights), "cameras": len(bpy.data.cameras)}
        return {"before": before, "after": after, "cleaned": True, "note": "No read_factory_settings — sandbox-safe"}

    def _compute_aabb(self, objects=None):
        """Compute world-space AABB for given objects or all meshes."""
        if objects is None:
            objects = [o for o in bpy.data.objects if o.type == 'MESH']
        if not objects:
            return None
        min_co = mathutils.Vector((float('inf'), float('inf'), float('inf')))
        max_co = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
        for obj in objects:
            if obj.type != 'MESH' or not obj.data:
                continue
            # Use bound_box
            for corner in obj.bound_box:
                world_co = obj.matrix_world @ mathutils.Vector(corner)
                min_co.x = min(min_co.x, world_co.x)
                min_co.y = min(min_co.y, world_co.y)
                min_co.z = min(min_co.z, world_co.z)
                max_co.x = max(max_co.x, world_co.x)
                max_co.y = max(max_co.y, world_co.y)
                max_co.z = max(max_co.z, world_co.z)
        if min_co.x == float('inf'):
            return None
        center = (min_co + max_co) * 0.5
        size = max_co - min_co
        radius = max(size.x, size.y, size.z) * 0.5
        if radius < 1e-4:
            radius = 1.0
        return {"min": list(min_co), "max": list(max_co), "center": list(center), "size": list(size), "radius": radius}

    def auto_frame_camera(self, camera_name="", target_objects=None, margin=1.2, angle=(0.9, 0, 0.8)):
        """Calcula AABB de objetos y posiciona cámara en ángulo ideal antes de captura. Usa temp_override."""
        # Resolve camera
        cam_obj = None
        if camera_name:
            cam_obj = bpy.data.objects.get(camera_name)
            if not cam_obj or cam_obj.type != 'CAMERA':
                raise ValueError(f"Camera not found: {camera_name}")
        else:
            cam_obj = bpy.context.scene.camera
            if not cam_obj or cam_obj.type != 'CAMERA':
                # Create one
                cam_data = bpy.data.cameras.new(name="AutoFrameCamera")
                cam_obj = bpy.data.objects.new(name="AutoFrameCamera", object_data=cam_data)
                bpy.context.collection.objects.link(cam_obj)
                bpy.context.scene.camera = cam_obj

        # Resolve targets
        if target_objects and isinstance(target_objects, list):
            objs = [bpy.data.objects.get(n) for n in target_objects]
            objs = [o for o in objs if o]
        else:
            objs = None

        aabb = self._compute_aabb(objs)
        if not aabb:
            return {"error": "No mesh objects to frame", "camera": cam_obj.name}

        center = mathutils.Vector(aabb["center"])
        radius = aabb["radius"]
        cam = cam_obj.data
        # Distance from center based on FOV: distance = radius / sin(fov/2)
        import math
        fov = cam.angle if hasattr(cam, "angle") else math.radians(50)
        distance = (radius * margin) / math.sin(fov * 0.5) if math.sin(fov*0.5) > 1e-6 else radius * 3
        distance = max(distance, radius * 1.5)
        # Direction from angle (spherical)
        ax, ay, az = angle
        # Use Euler to direction: place camera on sphere around center
        # Simple: use provided angle as Euler, offset = direction * distance
        rot = mathutils.Euler((ax, ay, az), 'XYZ')
        direction = mathutils.Vector((0, 0, 1))
        direction.rotate(rot)
        # In Blender camera looks -Z, so position = center + direction * distance
        cam_obj.location = center + direction * distance
        # Look at center: track -Z to center
        look_dir = center - cam_obj.location
        # Set rotation via quaternion
        quat = look_dir.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = quat.to_euler()
        bpy.context.view_layer.update()

        return {
            "camera": cam_obj.name,
            "aabb": aabb,
            "center": list(center),
            "radius": radius,
            "distance": distance,
            "location": list(cam_obj.location),
            "rotation_euler": [float(v) for v in cam_obj.rotation_euler],
            "framed": True,
        }

    def render_object_preview(self, object_name="", filepath="/tmp/supermcp_preview.png", resolution=512, margin=1.2):
        """Renderiza miniatura de un objeto en 1 paso: auto-frame + render."""
        obj = bpy.data.objects.get(object_name) if object_name else None
        # Auto-frame
        frame_info = self.auto_frame_camera(camera_name="", target_objects=[object_name] if object_name else None, margin=margin)
        cam_name = frame_info.get("camera")
        # Set render settings for preview
        scene = bpy.context.scene
        prev_res_x, prev_res_y = scene.render.resolution_x, scene.render.resolution_y
        prev_pct = scene.render.resolution_percentage
        prev_filepath = scene.render.filepath
        prev_engine = scene.render.engine
        try:
            scene.render.resolution_x = resolution
            scene.render.resolution_y = resolution
            scene.render.resolution_percentage = 100
            scene.render.filepath = filepath
            scene.render.image_settings.file_format = 'PNG'
            # Use EEVEE for fast preview if available
            if 'BLENDER_EEVEE' in bpy.context.preferences.addons.keys() or True:
                try:
                    scene.render.engine = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (4, 2, 0) else 'BLENDER_EEVEE'
                except:
                    pass
            bpy.ops.render.render(write_still=True)
            exists = os.path.exists(filepath)
            size = os.path.getsize(filepath) if exists else 0
        finally:
            scene.render.resolution_x = prev_res_x
            scene.render.resolution_y = prev_res_y
            scene.render.resolution_percentage = prev_pct
            scene.render.filepath = prev_filepath
            scene.render.engine = prev_engine
        return {
            "object": object_name or "scene",
            "camera": cam_name,
            "filepath": filepath,
            "exists": exists,
            "size_bytes": size,
            "resolution": resolution,
            "frame_info": frame_info,
        }

    def export_godot_glb(self, filepath="/tmp/export_godot.glb", use_selection=False, use_visible=False, auto_cure=True, compression=False):
        """Alias de godot_export_glb con PBR compat + compresión opcional para Godot/Redot."""
        # Reuse godot_export_glb but ensure PBR defaults
        result = self.godot_export_glb(filepath=filepath, export_format="GLB", use_selection=use_selection, use_visible=use_visible, export_apply=True, export_yup=True, export_animations=True, auto_cure=auto_cure)
        # If compression requested, try Draco (if available)
        if compression and result.get("success"):
            # Note: Draco compression via export is handled in io_export; here we just flag
            result["compression_requested"] = True
        return result

# ── Blender Addon registration ──────────────────────────────────────────

_super_server = SuperMCPServer()

class SUPERMCP_OT_start_server(bpy.types.Operator):
    bl_idname = "supermcp.start_server"
    bl_label = "Start SuperMCP Server"
    bl_description = "Start SuperMCP server on port 9877 (Free stays on 9876)"
    def execute(self, context):
        _super_server.start()
        self.report({'INFO'}, f"SuperMCP started on port {_super_server.port}")
        return {'FINISHED'}

class SUPERMCP_OT_stop_server(bpy.types.Operator):
    bl_idname = "supermcp.stop_server"
    bl_label = "Stop SuperMCP Server"
    def execute(self, context):
        _super_server.stop()
        self.report({'INFO'}, "SuperMCP stopped")
        return {'FINISHED'}

class SUPERMCP_PT_panel(bpy.types.Panel):
    bl_label = "SuperMCP"
    bl_idname = "SUPERMCP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SuperMCP"

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        if _super_server.running:
            col.label(text=f"Running on port {_super_server.port}", icon='CHECKMARK')
            col.label(text="Free is on 9876 (separate)")
            col.operator("supermcp.stop_server", icon='CANCEL')
        else:
            col.label(text=f"Stopped (port {_super_server.port})")
            col.label(text="Free stays on 9876")
            col.operator("supermcp.start_server", icon='PLAY')

        layout.separator()
        box = layout.box()
        box.label(text="Godot Pipeline (auto-cure)", icon='EXPORT')
        box.label(text="Cure: Apply Transforms")
        box.label(text=" + Merge by Distance")
        box.label(text=" + Recalc Normals")
        box.label(text="Export: .glb (Godot 4.x)")

classes = (SUPERMCP_OT_start_server, SUPERMCP_OT_stop_server, SUPERMCP_PT_panel)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    print("SuperMCP addon registered — start server from N-panel > SuperMCP")

def unregister():
    _super_server.stop()
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except:
            pass
    print("SuperMCP addon unregistered")

if __name__ == "__main__":
    register()
