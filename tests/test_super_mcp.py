"""
QA Test Suite for SuperMCP in Blender
Execute via: /opt/blender/blender --background --python tests/test_super_mcp.py
"""

import sys
import unittest
import os

# Ensure repo root is in python path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import bpy
import bmesh
import mathutils

# Import addon instance / handlers
import addon


class TestSuperMCP(unittest.TestCase):

    def setUp(self):
        # Clear scene before each test
        bpy.ops.wm.read_homefile(use_empty=True)
        self.server = addon.SuperMCPServer()

    def test_gltf_export_rna_properties(self):
        """Test 1: Check glTF export RNA properties in Blender 5.1+ compatibility."""
        gltf_op = getattr(bpy.ops.export_scene, "gltf", None)
        self.assertIsNotNone(gltf_op, "bpy.ops.export_scene.gltf missing")
        props = {p.identifier for p in gltf_op.get_rna_type().properties}
        
        # In Blender 4.2+ / 5.1+, export_image_format is used instead of export_images
        self.assertIn("export_image_format", props)
        self.assertNotIn("export_images", props, "export_images is deprecated/removed in Blender 4.2+/5.1+")
        self.assertIn("export_morph", props)
        self.assertIn("export_nla_strips", props)

    def test_armature_scale_validation_and_cure(self):
        """Test 2: Armature with scale != (1,1,1) validation warning and curing."""
        arm_data = bpy.data.armatures.new("TestArmature")
        arm_obj = bpy.data.objects.new("TestArmatureObj", arm_data)
        bpy.context.collection.objects.link(arm_obj)
        arm_obj.scale = (2.0, 2.0, 2.0)

        # Validate
        res = self.server.godot_validate_scene()
        self.assertTrue(any("Armature" in w and "non-uniform scale" in w for w in res["warnings"]))

        # Cure
        cure_res = addon._cure_single_object(arm_obj, apply_scale=True)
        self.assertEqual(tuple(round(s, 4) for s in arm_obj.scale), (1.0, 1.0, 1.0))
        self.assertEqual(cure_res["transform"]["after"]["scale"], (1.0, 1.0, 1.0))

    def test_missing_image_texture_check(self):
        """Test 3: Material with TEX_IMAGE node missing image assignment."""
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        mat = bpy.data.materials.new("TestMat")
        mat.use_nodes = True
        obj.data.materials.append(mat)

        # Add TEX_IMAGE node without image assigned
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = None

        compat_res = self.server.godot_check_material_compatibility(object_name=obj.name)
        self.assertFalse(compat_res["compatible"])
        self.assertTrue(any("has no image assigned" in issue for issue in compat_res["issues"]))

        val_res = self.server.godot_validate_scene()
        self.assertTrue(any("has no image assigned" in err for err in val_res["errors"]))

    def test_ngon_cure_triangulate(self):
        """Test 4: Ngon curing actually triangulates polygons with > 4 verts."""
        # Create 5-sided polygon mesh
        mesh = bpy.data.meshes.new("NgonMesh")
        obj = bpy.data.objects.new("NgonObj", mesh)
        bpy.context.collection.objects.link(obj)

        bm = bmesh.new()
        v1 = bm.verts.new((0, 0, 0))
        v2 = bm.verts.new((1, 0, 0))
        v3 = bm.verts.new((1.5, 1, 0))
        v4 = bm.verts.new((0.5, 2, 0))
        v5 = bm.verts.new((-0.5, 1, 0))
        bm.faces.new((v1, v2, v3, v4, v5))
        bm.to_mesh(mesh)
        bm.free()

        val_before = self.server.validate_mesh(object_name=obj.name)
        self.assertEqual(val_before["ngons"], 1)
        self.assertTrue(val_before["needs_cure"])

        # Run cure
        cure_res = addon._cure_single_object(obj)
        self.assertGreater(cure_res.get("triangulated_ngons", 0), 0)

        val_after = self.server.validate_mesh(object_name=obj.name)
        self.assertEqual(val_after["ngons"], 0)

    def test_zero_scale_guard_and_merge_warning(self):
        """Test 5: Zero scale abort guard and merge_distance > 0.01 warning."""
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        obj.scale = (0.0, 1.0, 1.0)

        # Cure zero scale object
        cure_res = addon._cure_single_object(obj)
        self.assertTrue(cure_res.get("skipped"))
        self.assertEqual(cure_res.get("error"), "zero scale cannot be baked")

        # Test high merge distance warning
        obj.scale = (1.0, 1.0, 1.0)
        cure_high_merge = addon._cure_single_object(obj, merge_distance=0.05)
        self.assertIn("high merge distance may collapse small geometry", cure_high_merge.get("warnings", []))

    def test_uv_unwrap_and_pack_fallback(self):
        """Test 6: UV unwrap and pack islands execution and fallback handling."""
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object

        unwrap_res = self.server.uv_unwrap(object_name=obj.name, method="SMART_PROJECT", margin=0.02)
        self.assertEqual(unwrap_res["object"], obj.name)
        self.assertGreaterEqual(unwrap_res["uv_layers"], 1)

        pack_res = self.server.uv_pack_islands(object_name=obj.name, margin=0.02)
        self.assertTrue(pack_res["packed"])

    def test_asset_window_and_cutout(self):
        """Test 7: asset_add_window cuts wall opening and inserts window frame & glass."""
        wall_res = self.server.asset_create_wall(name="TestWall", start=(0,0,0), end=(4,0,0), height=2.5, thickness=0.2)
        self.assertTrue(wall_res["success"])

        win_res = self.server.asset_add_window(wall_name="TestWall", center=(2.0, 0, 1.2), size=(1.0, 0.4, 1.0))
        self.assertTrue(win_res["success"])
        self.assertIsNotNone(bpy.data.objects.get(win_res["window_frame"]))
        self.assertIsNotNone(bpy.data.objects.get(win_res["window_glass"]))


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSuperMCP)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(not result.wasSuccessful())
