"""
Procedural 3D Cabin Generator script for Blender / SuperMCP.
Generates a stylized wooden cabin with porch, roof, chimney, door, windows, and materials.
Renders a preview screenshot and exports cabin.glb.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import bmesh
import mathutils
import math

# Import SuperMCP addon functions
import addon

def create_cabin():
    # 1. Clean scene
    bpy.ops.wm.read_homefile(use_empty=True)

    # 2. Materials Setup
    def make_material(name, color, roughness=0.6, metallic=0.0, alpha=1.0):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            # Blender 4.x/5.x Principled BSDF input names
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = color
            if "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = roughness
            if "Metallic" in bsdf.inputs:
                bsdf.inputs["Metallic"].default_value = metallic
            if alpha < 1.0 and "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = alpha
                mat.blend_method = 'BLEND' if hasattr(mat, 'blend_method') else 'OPAQUE'
        return mat

    mat_deck = make_material("Mat_Deck", (0.35, 0.22, 0.12, 1.0), roughness=0.7)
    mat_walls = make_material("Mat_Logs", (0.28, 0.16, 0.08, 1.0), roughness=0.8)
    mat_roof = make_material("Mat_Roof", (0.15, 0.12, 0.10, 1.0), roughness=0.5)
    mat_door = make_material("Mat_Door", (0.20, 0.08, 0.04, 1.0), roughness=0.6)
    mat_chimney = make_material("Mat_Stone", (0.35, 0.35, 0.35, 1.0), roughness=0.9)
    mat_glass = make_material("Mat_Glass", (0.6, 0.85, 0.9, 0.5), roughness=0.1, alpha=0.5)
    mat_frame = make_material("Mat_Frame", (0.18, 0.10, 0.05, 1.0), roughness=0.6)
    mat_metal = make_material("Mat_Metal", (0.8, 0.7, 0.3, 1.0), roughness=0.3, metallic=0.9)

    # Helper function to create box mesh
    def create_box(name, size, location, material=None):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = size
        if material:
            obj.data.materials.append(material)
        return obj

    # 3. Foundation & Deck (Porch)
    deck = create_box("Deck", (6.0, 5.0, 0.4), (0, 0, 0.2), mat_deck)

    # Deck support posts
    for x in [-2.8, 2.8]:
        for y in [-2.3, 2.3]:
            create_box("DeckPost", (0.3, 0.3, 0.4), (x, y, -0.2), mat_deck)

    # 4. Main House Walls
    house_body = create_box("HouseWalls", (4.4, 3.6, 2.6), (0, 0.4, 1.7), mat_walls)

    # Add log beam details (horizontal ridges along walls)
    for z_off in [0.7, 1.1, 1.5, 1.9, 2.3, 2.7]:
        create_box("LogRidge_Front", (4.5, 0.1, 0.15), (0, -1.41, z_off), mat_walls)
        create_box("LogRidge_Back", (4.5, 0.1, 0.15), (0, 2.21, z_off), mat_walls)
        create_box("LogRidge_Left", (0.1, 3.7, 0.15), (-2.21, 0.4, z_off), mat_walls)
        create_box("LogRidge_Right", (0.1, 3.7, 0.15), (2.21, 0.4, z_off), mat_walls)

    # 5. Roof Structure (Gable Roof)
    # Triangular Gables (Front & Back)
    def create_gable(name, location, y_rot=0):
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = location
        bm = bmesh.new()
        v1 = bm.verts.new((-2.2, 0, 0))
        v2 = bm.verts.new((2.2, 0, 0))
        v3 = bm.verts.new((0, 0, 1.6))
        bm.faces.new((v1, v2, v3))
        bm.to_mesh(mesh)
        bm.free()
        obj.data.materials.append(mat_walls)
        return obj

    create_gable("Gable_Front", (0, -1.4, 3.0))
    create_gable("Gable_Back", (0, 2.2, 3.0))

    # Roof Slabs (Left & Right sloped roofs overhanging)
    roof_left = create_box("Roof_Left", (2.8, 4.4, 0.2), (-1.3, 0.4, 3.8), mat_roof)
    roof_left.rotation_euler = (0, math.radians(35), 0)

    roof_right = create_box("Roof_Right", (2.8, 4.4, 0.2), (1.3, 0.4, 3.8), mat_roof)
    roof_right.rotation_euler = (0, math.radians(-35), 0)

    # Roof Ridge beam
    create_box("Roof_Ridge", (0.2, 4.5, 0.2), (0, 0.4, 4.6), mat_roof)

    # Porch Roof Overhang
    porch_roof = create_box("Porch_Roof", (4.8, 1.6, 0.15), (0, -1.9, 2.8), mat_roof)
    porch_roof.rotation_euler = (math.radians(10), 0, 0)

    # Porch Pillars
    create_box("Porch_Pillar_L", (0.2, 0.2, 2.4), (-2.0, -2.4, 1.6), mat_frame)
    create_box("Porch_Pillar_R", (0.2, 0.2, 2.4), (2.0, -2.4, 1.6), mat_frame)

    # 6. Door & Frame
    create_box("DoorFrame", (1.2, 0.15, 2.0), (-0.8, -1.42, 1.4), mat_frame)
    create_box("DoorPanel", (1.0, 0.1, 1.85), (-0.8, -1.43, 1.35), mat_door)
    create_box("DoorKnob", (0.08, 0.15, 0.08), (-0.45, -1.48, 1.35), mat_metal)

    # 7. Windows
    # Front Window
    create_box("WinFrame_Front", (1.0, 0.15, 1.0), (1.0, -1.42, 1.7), mat_frame)
    create_box("WinGlass_Front", (0.8, 0.05, 0.8), (1.0, -1.42, 1.7), mat_glass)

    # Side Windows
    create_box("WinFrame_SideL", (0.15, 1.0, 1.0), (-2.22, 0.4, 1.7), mat_frame)
    create_box("WinGlass_SideL", (0.05, 0.8, 0.8), (-2.22, 0.4, 1.7), mat_glass)

    create_box("WinFrame_SideR", (0.15, 1.0, 1.0), (2.22, 0.4, 1.7), mat_frame)
    create_box("WinGlass_SideR", (0.05, 0.8, 0.8), (2.22, 0.4, 1.7), mat_glass)

    # 8. Stone Chimney
    create_box("ChimneyBase", (0.9, 0.9, 4.2), (2.1, 1.2, 2.1), mat_chimney)
    create_box("ChimneyCap", (1.1, 1.1, 0.2), (2.1, 1.2, 4.3), mat_chimney)
    create_box("ChimneyPipe", (0.5, 0.5, 0.4), (2.1, 1.2, 4.6), mat_chimney)

    # 9. Ensure UV unwrap for all meshes
    server = addon.SuperMCPServer()
    for obj in bpy.data.objects:
        if obj.type == 'MESH':
            try:
                server.uv_unwrap(obj.name)
            except Exception as e:
                pass

    # 10. SuperMCP Scene Curing
    cure_report = server.cure_scene(merge_distance=0.001, recalc_outside=True)
    val_report = server.godot_validate_scene()
    print("Cabin generation curing report:", cure_report["cured_count"], "objects cured")
    print("Validation status: can_export =", val_report["can_export"], "Errors:", val_report["errors"])

    # 10. Studio Lighting Setup
    bpy.ops.object.light_add(type='SUN', location=(5, -8, 10))
    sun = bpy.context.active_object
    sun.data.energy = 4.0
    sun.data.color = (1.0, 0.95, 0.85)  # Warm sunlight
    sun.rotation_euler = (math.radians(45), math.radians(15), math.radians(-30))

    bpy.ops.object.light_add(type='POINT', location=(-4, -4, 4))
    fill = bpy.context.active_object
    fill.data.energy = 100.0
    fill.data.color = (0.7, 0.85, 1.0)  # Cool sky fill light

    # Warm light inside window/door
    bpy.ops.object.light_add(type='POINT', location=(-0.8, -0.5, 1.5))
    interior_light = bpy.context.active_object
    interior_light.data.energy = 50.0
    interior_light.data.color = (1.0, 0.6, 0.2)  # Cozy warm glow inside

    # 11. Camera & Render Setup
    server.auto_frame_camera(margin=1.35, angle=(math.radians(65), 0, math.radians(35)))
    cam = bpy.context.scene.camera
    if cam:
        cam.data.lens = 50

    output_img = "/tmp/cabin_preview.png"
    server.render_object_preview(filepath=output_img, resolution=768, margin=1.35)
    print("Rendered preview to:", output_img)

    # Export GLB model for Godot / 3D viewer
    export_glb = "/tmp/cabin.glb"
    server.godot_export_glb(filepath=export_glb, auto_cure=True)
    print("Exported cabin GLB to:", export_glb)

if __name__ == "__main__":
    create_cabin()
