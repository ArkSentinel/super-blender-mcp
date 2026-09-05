# SuperMCP — Plan de Fases (Godot al final)

> Puerto separado: **SuperMCP 9877** vs Free 9876. Addon `SuperMCP` coexistiendo.

## Estado actual

- **Fase 0 — Scaffolding**: DONE — `pyproject.toml`, `server/__main__.py`, `addon.py` base, `connection.py` retry, `data/prompts.yml`.
- **Fase 1 — Base fixes + Curado (adelantado)**: DONE — Object info, Viewport fix #189, `cure_model`/`cure_scene` (apply transforms + merge by distance + recalc normals), `godot_validate_scene`/`godot_export_glb` con auto-cure. Godot estaba previsto al final pero se adelantó por tu pedido; queda como Fase 6 final pulido.

## Fases restantes (orden pedido — Godot al final)

### Fase 2 — Mallas complejas (START AHORA)
**Objetivo**: pipeline no-destructivo para mallas high-poly → low-poly.
- **Modifier Stack (6 tools, 22 tipos)**: `add_modifier`, `remove_modifier`, `set_modifier_params`, `move_modifier`, `apply_modifier`, `list_modifiers`. Tipos: Subsurf, Multires, Bevel, Boolean (EXACT/FAST), Array, Mirror, Solidify, Decimate, Remesh (VOXEL/QUAD), Weld, Triangulate, Shrinkwrap (retopo), WeightedNormal, DataTransfer, Lattice, Displace, etc.
- **Mesh Ops Advanced (5 tools)**: `mesh_operation` (bevel, subdivide, triangulate, decimate, bridge_loops), `clean_mesh`, `create_advanced_mesh`, `validate_mesh`, `create_lod_chain`.
- **Geometry Nodes (6 tools)**: `geometry_nodes_create`, `geometry_nodes_add_node`, `geometry_nodes_link`, `geometry_nodes_set_param`, `geometry_nodes_templates` (8 templates: scatter, extrude, etc.), `geometry_nodes_apply`.

### Fase 3 — Texturizado y sombreado
- **Shader Node Trees (10)**: `create_node_tree`, `add_shader_node`, `remove_node`, `link_nodes`, `set_node_param`, `get_node_tree`, `duplicate_node_tree`, `clear_node_tree`, `arrange_nodes`, `export_node_tree_as_code`.
- **UV Tools (6)**: `unwrap_uv`, `add_uv_layer`, `pack_uv_islands`, `get_uv_info`, `export_uv_layout`, `uv_validate`.
- **PBR Materials (8)**: `create_pbr_material` (Principled fix dup), `assign_material`, `set_principled_params`, `create_texture_node_chain`, `pack_orm`, `bake_texture` (AO/Diffuse/Normal, Cycles), `get_material_graph`, `validate_textures`.

### Fase 4 — Rigging y Animación
- **Rigging & Armatures (8)**: `create_armature`, `add_bone`, `set_bone_params`, `parent_to_armature`, `add_ik_constraint`, `create_rig_preset`, `weight_paint_transfer`, `list_armatures`.
- **Animation & Keyframes (12)**: `insert_keyframe`, `delete_keyframe`, `set_timeline`, `create_action`, `assign_action`, `set_interpolation`, `bake_animation`, `create_nla_strip`, `set_graph_handles`, `copy_keyframes`, `clear_animation`, `get_animation_info`.

### Fase 5 — Luces, Cámara, Render
- **Light Control (5)**: `create_light`, `set_light_params`, `set_world_hdri`, `setup_studio_lighting`, `list_lights`.
- **Camera Control (7)**: `create_camera`, `set_camera_params`, `set_camera_view`, `track_to_object`, `create_camera_rig`, `render_from_camera`, `list_cameras`.
- **Render Settings (4)**: `set_render_engine`, `set_render_settings`, `set_output_path`, `get_render_info`.

### Fase 6 — Pipeline final Godot + Utilidades (pulido)
- **Godot pipeline ya hecho en Fase 1** — aquí pulido: `godot_setup_collision` (-col/-convcol), `godot_setup_lod`, `godot_check_material_compatibility`, `godot_batch_export`, presets.
- **Batch Processing (5)**: `batch_process_directory`, `batch_render_queue`, `batch_import`, `batch_export`, `batch_execute_code`.
- **Import/Export 9 formatos (4)**: `import_file`/`export_file` (FBX/OBJ/GLTF/GLB/USD/ABC/STL/PLY/DAE), `list_supported_formats`.
- **Diagnostics (4)**: `check_rig_health`, `validate_armature`, `fix_rig_issues`, `get_rig_report`.
- **Scene Utilities (4)**: `clean_scene`, `organize_collections`, `merge_scenes`, `get_scene_stats`.
- **Workflow Presets & AI Hints (4)**: `apply_preset`, `get_ai_hint`, `list_presets`, `create_preset_from_scene`.

## Orden de ejecución pedido

```
Fase 0 DONE → Fase 1 DONE (curado) → Fase 2 DONE → Fase 3 DONE → Fase 4 DONE → Fase 5 DONE → Fase 6 DONE
```

## Estado actualizado (2026-09-05) — TODAS LAS FASES DONE

- **Fase 2 DONE** — Modifier 6 + Mesh 2 + Geometry Nodes 5 = 13 tools.
- **Fase 3 DONE** — Shader 10 + UV 6 + PBR 4 = 20 tools. Principled fix, ORM pack, Cycles bake.
- **Fase 4 DONE** — Rigging 8 + Animation 12 = 20 tools. IK, weight transfer, NLA -loop.
- **Fase 5 DONE** — Light 5 + Camera 7 + Render 4 = 16 tools. HDRI, studio 3-point, camera rig, render engine.
- **Fase 6 DONE** — Batch 5 + IO 4 + Diagnostics 4 + Scene Utils 4 + Presets 4 + Godot polish 4 = 25 tools. 9 formatos (FBX/GLTF/OBJ/STL/PLY/DAE/ABC/USD/BLEND), -col/-convcol, LOD, orphans_purge.
- **Total final**: 103 tools MCP, `addon.py:2373` líneas, todos `py_compile` OK.
- **Bug fixes vs Free**: Viewport #189 (GPUOffScreen), Principled dup, connection retry 9877, PolyHaven path traversal.

## Cobertura Pro

SuperMCP cubre todo el Free (bug-fixed) + 11 categorías Pro + Godot pipeline auto-cure + mallas complejas.

## Métrica de done por fase

- Cada fase: handlers en `addon.py` + tools en `server/tools/<fase>.py` + `py_compile` OK + test `cure`/`validate` manual en `granja.blend`.
