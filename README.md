# SuperMCP para Blender

SuperMCP es un servidor MCP separado del Free `blender-mcp` que expone 107 herramientas para modelado de mallas complejas, texturizado PBR y pipeline de exportacion a Godot 4.x y Redot. El addon de Blender opera en el puerto 9877. El Free opera en 9876. Ambos coexisten sin colision.

## Caracteristicas

### Correcciones respecto al Free

* Viewport screenshot corrige el Bug #189 mediante `GPUOffScreen.draw_view3d` con fallback a captura de ventana. Reporta el metodo empleado.
* Material Principled BSDF evita duplicacion de nodos al reutilizar nodos existentes.
* Estabilidad de conexion con reintento automatico de tres intentos con backoff exponencial y delimitador nulo.
* Librerias de assets con sanitizacion de rutas y cache.

### Pipeline de curado pre-export

El exportador a Godot ejecuta de forma automatica, antes de exportar, tres operaciones:

1. Aplicacion de transformaciones. Convierte location, rotacion y escala a datos de malla. La escala resultante es 1,1,1. Corrige skinning y colisiones en Godot.
2. Union de vertices por distancia. Eliminacion de duplicados mediante `bmesh.ops.remove_doubles` con distancia 0.0001 por defecto.
3. Recalculo de normales. Correccion de caras invertidas mediante `bmesh.ops.recalc_face_normals` con orientacion exterior.

### Cobertura funcional

El sistema cubre el Free corregido y 11 categorias ausentes en el Free. El total es 107 herramientas.

* Modificadores: 6 herramientas, 22 tipos (Subsurf, Bevel, Boolean, Array, Mirror, Solidify, Decimate, Remesh, Weld, Triangulate, Shrinkwrap, WeightedNormal, DataTransfer entre otros).
* Malla avanzada y validacion: 2 herramientas. Operaciones bmesh (subdivide, bevel, triangulate, merge_by_distance, recalc_normals) y validacion de ngons, tris, degenerados y UV.
* Geometry Nodes: 5 herramientas. Creacion de modificador Nodes, agregado y conexion de nodos, asignacion de parametros y 8 plantillas (scatter, extrude, boolean, subdivide, triangulate, merge_by_distance, instance_on_points, noise_displace).
* Shader Nodes: 10 herramientas. Creacion, adicion, eliminacion, conexion, parametrizacion, inspeccion, limpieza, duplicacion, ordenamiento y exportacion a codigo Python.
* UV: 6 herramientas. Desempaquetado Smart/Cube/Unwrap, gestion de capas, empaquetado de islas, exportacion de layout y validacion.
* PBR y horneado: 4 herramientas. Creacion y asignacion de material Principled, empaquetado ORM (AO en R, Roughness en G, Metallic en B en espacio Non-Color) y horneado Cycles (AO, Diffuse, Normal, Combined, Roughness, Emit).
* Rigging: 8 herramientas. Creacion de armature, agregado de huesos, parametrizacion, parentesco con pesos automaticos, restriccion IK, preset basic_chain, transferencia de pesos y listado.
* Animacion: 12 herramientas. Insercion y eliminacion de keyframes, control de timeline, creacion y asignacion de acciones, interpolacion, horneado, creacion de pistas NLA con soporte de sufijo -loop para Godot, copia de keyframes, limpieza, consulta y ajuste de manejadores.
* Iluminacion: 5 herramientas. Creacion y parametrizacion de luces Point, Sun, Spot y Area, asignacion de HDRI en World y preset de iluminacion de estudio de tres puntos.
* Camara: 7 herramientas. Creacion y parametrizacion, activacion en viewport, seguimiento Track-To, rig de camara con Empty, render y listado.
* Render: 4 herramientas. Seleccion de motor, configuracion de resolucion y muestras, salida y consulta.
* Batch: 5 herramientas. Ejecucion por objeto, cola de render, importacion y exportacion por lote y procesamiento de directorio.
* Entrada y salida: 4 herramientas. Soporte de 9 formatos (FBX, gLTF, GLB, OBJ, STL, PLY, DAE, ABC, USD, BLEND), deteccion automatica por extension y listado de formatos.
* Diagnostico y escena: 8 herramientas. Verificacion de salud de rig, validacion y correccion de armature, reporte, limpieza de huerfanos, organizacion de colecciones, fusion de archivos blend y estadisticas.
* Presets y pulido Godot: 8 herramientas. Presets de iluminacion, tornamesa y personaje base, generacion de preset desde escena, sugerencias contextuales, generacion de colisiones por sufijo (-col, -convcol, -colonly), niveles de detalle por decimacion y verificacion de compatibilidad de materiales.
* Herramientas de alto nivel: 4 herramientas. Limpieza de escena sin `read_factory_settings` (seguro en sandbox), encuadre automatico de camara por AABB, render de previsualizacion en un paso y alias `export_godot_glb` con PBR y compresion opcional.
* Alto nivel adicional: Gestion de contexto 3D estable mediante `temp_override`, traza estructurada en JSON con excepcion, numero de linea y traceback completo, y envoltura de ejecucion de codigo con override automatico.
* Utilidades de escena: captura de viewport, informacion de escena y objeto, ejecucion de codigo Blender.

## Requisitos

* Blender 3.0 o superior. Probado con 4.x.
* Python 3.11 o superior.
* Dependencias del servidor: `mcp >= 1.29.0`, `httpx`, `pydantic`, `PyYAML`.
* Godot 4.x o Redot para el pipeline GLB. Formato nativo gLTF 2.0 (.glb) con 1 unidad Blender equivalente a 1 metro en Godot.

## Estructura del repositorio

```
super-mcp/
  addon.py                 Addon de Blender. Servidor en puerto 9877.
  server/
    __main__.py            Servidor FastMCP. Transporte stdio y http.
    tools/                 18 modulos, 107 herramientas con registro automatico.
    tools_helpers/
      connection.py        Cliente de socket con reintento y framing nulo.
  data/
    prompts.yml            Instrucciones iniciales para el agente.
    presets/godot/         Perfiles de exportacion por tipo de objeto.
  pyproject.toml           Definicion del proyecto y script super-mcp.
  opencode.json            Configuracion MCP para OpenCode a nivel de proyecto.
  PHASES.md                Historico de fases de implementacion.
  README.md                Este documento.
```

## Instalacion

### Instalacion del addon en Blender

1. Abrir Blender.
2. Seleccionar Edit, Preferences, Add-ons, Install.
3. Seleccionar el archivo `addon.py` del repositorio.
4. Activar Interface: SuperMCP.
5. En la vista 3D, abrir el panel lateral con N, seleccionar la pestana SuperMCP y accionar Start Server. El servidor queda en escucha en 9877. El Free permanece en 9876.

### Instalacion del servidor MCP

#### Opcion A: Instalacion directa desde GitHub

```bash
pip install git+https://github.com/TU_USUARIO/super-mcp.git
super-mcp --transport stdio
# con uv
uv tool install git+https://github.com/TU_USUARIO/super-mcp.git
```

Sustituir `TU_USUARIO` por el propietario del repositorio. Esta variante no requiere clonacion previa y registra el binario `super-mcp` en el PATH.

#### Opcion B: Clonacion e instalacion editable para desarrollo

```bash
git clone https://github.com/TU_USUARIO/super-mcp.git
cd super-mcp
pip install -e .
super-mcp --transport stdio
```

#### Opcion C: Herramienta aislada con uv desde ruta local

```bash
uv tool install --from /ruta/a/super-mcp super-mcp
super-mcp --transport stdio
```

Sustituir `/ruta/a/super-mcp` por la ruta absoluta donde se clono el repositorio.

#### Opcion D: Ejecucion sin instalacion

```bash
PYTHONPATH=/ruta/a/super-mcp python3 -m server.__main__ --transport stdio
```

#### Transporte HTTP

```bash
super-mcp --transport http --host 127.0.0.1 --port 8001
```

El puerto HTTP por defecto para SuperMCP es 8001. El Free utiliza 8000.

### Variables de entorno

* `SUPER_MCP_HOST`. Valor por defecto localhost. `BLENDER_MCP_HOST` se considera como respaldo.
* `SUPER_MCP_PORT`. Valor por defecto 9877.

## Uso

### Verificacion de conexion

```bash
nc -z -w2 localhost 9877 && echo "SuperMCP abierto" || echo "SuperMCP cerrado"
nc -z -w2 localhost 9876 && echo "Free abierto" || echo "Free cerrado"
```

Ambos deben reportar abierto cuando Blender se encuentra en ejecucion con cada servidor iniciado.

### Flujo basico de modelado y exportacion a Godot

```python
# El agente invoca herramientas MCP. Ejemplo conceptual de secuencia:
# 1. Limpiar escena
reset_scene_clean()

# 2. Crear malla y modificadores no destructivos
add_modifier(object_name="Cube", modifier_type="subsurf", params={"levels": 2})
add_modifier(object_name="Cube", modifier_type="bevel", params={"segments": 3})

# 3. Validar malla
validate_mesh(object_name="Cube")

# 4. Crear material PBR
pbr_create_material(material_name="Body", base_color=[0.8,0.2,0.2,1.0], metallic=0.0, roughness=0.5)
pbr_assign_material(object_name="Cube", material_name="Body")

# 5. Desempaquetar UV
uv_unwrap(object_name="Cube", method="SMART_PROJECT", margin=0.02)

# 6. Validar y exportar a Godot con curado automatico
godot_validate_scene(only_selected=False)
godot_export_glb(filepath="/tmp/model.glb", export_format="GLB", auto_cure=True)
# godot_export_glb aplica transforms, merge_by_distance y recalc_normals antes de bpy.ops.export_scene.gltf
```

El archivo `/tmp/model.glb` se importa directamente en Godot 4.x mediante importacion gLTF. La escala, las normales y los duplicados ya se encuentran corregidos.

### Previsualizacion rapida

```python
render_object_preview(object_name="Cube", filepath="/tmp/preview.png", resolution=512)
auto_frame_camera(target_objects=["Cube"], margin=1.2)
get_viewport_screenshot(max_size=800, filepath="/tmp/viewport.png")
```

### Trabajos por lote y multiples formatos

```python
batch_import(directory="/ruta/a/assets", pattern="*.fbx")
batch_export(directory="/tmp/lote", export_format="GLB")
io_import_file(filepath="/ruta/a/modelo.obj", format="AUTO")
io_export_file(filepath="/tmp/salida.fbx", format="FBX", use_selection=False)
io_list_formats()
```

### Rigging y animacion

```python
rig_create_armature(name="Armature", location=[0,0,0])
rig_add_bone(armature_name="Armature", bone_name="Bone", head=[0,0,0], tail=[0,1,0])
rig_parent_to_armature(object_name="Cube", armature_name="Armature", with_weights="ARMATURE_AUTO")
anim_create_action(object_name="Cube", action_name="Bounce")
anim_insert_keyframe(object_name="Cube", data_path="location", frame=1, value=[0,0,0])
anim_insert_keyframe(object_name="Cube", data_path="location", frame=24, value=[0,0,2])
anim_create_nla_strip(object_name="Cube", strip_name="Bounce-loop", frame_start=1)
```

El sufijo `-loop` en la pista NLA activa el bucle automatico en el importador de Godot.

### Colisiones y LOD para Godot

```python
godot_setup_collision(object_name="Wall", collision_type="-colonly")
godot_setup_lod(object_name="Character", levels=[0.5, 0.25])
godot_check_material_compatibility(object_name="Wall")
```

Godot genera StaticBody3D y CollisionShape3D a partir de los sufijos `-col`, `-convcol`, `-colonly` y `-convcolonly` en el nombre del objeto. Los objetos con sufijo `-colonly` no se renderizan.

## Configuracion en harnesses

### OpenCode

La configuracion versionada en `opencode.json` utiliza el binario instalado y no requiere rutas absolutas. Es portable entre equipos.

Contenido de `opencode.json` incluido en el repositorio:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "super-mcp": {
      "type": "local",
      "command": ["super-mcp"],
      "enabled": true
    }
  }
}
```

Este archivo funciona cuando el paquete se instalo mediante pip o uv (Opcion A o B). OpenCode lo detecta de forma automatica sin configuracion adicional.

Para ejecucion sin instalacion (Opcion D), utilizar la variante con `PYTHONPATH` y sustituir `/ruta/a/super-mcp` por la ruta absoluta del clon. Tras modificar la configuracion global en `~/.config/opencode/opencode.json`, reiniciar OpenCode.

Verificacion:

```bash
opencode mcp list 2>/dev/null | grep super-mcp
# o inspeccionar el registro en los logs de OpenCode
```

### Claude Code

Con el paquete instalado, la configuracion recomendada utiliza el binario:

```json
{
  "mcpServers": {
    "super-mcp": {
      "command": "super-mcp",
      "args": []
    }
  }
}
```

Alternativa con `claude mcp add`:

```bash
claude mcp add super-mcp -- super-mcp
```

Para ejecucion sin instalacion, editar `~/.claude.json` con:

```json
{
  "mcpServers": {
    "super-mcp": {
      "command": "/usr/bin/python3",
      "args": ["-m", "server.__main__"],
      "env": {
        "PYTHONPATH": "/ruta/a/super-mcp"
      }
    }
  }
}
```

Sustituir `/ruta/a/super-mcp` por la ruta absoluta del clon.

### Cursor

Con paquete instalado, editar `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "super-mcp": {
      "command": "super-mcp",
      "args": []
    }
  }
}
```

Sin instalacion, utilizar el formato con `PYTHONPATH` descrito para Claude Code.

### Windsurf

Editar `~/.codeium/windsurf/mcp_config.json` con el mismo formato que Cursor.

### Cline y harnesses genericos

Con paquete instalado, cualquier harness compatible con MCP en transporte stdio utiliza:

* Comando: `super-mcp`
* Argumentos: `[]`

Sin instalacion:

* Comando: `/usr/bin/python3`
* Argumentos: `["-m", "server.__main__"]`
* Variable `PYTHONPATH` apuntando a la raiz del repositorio.

Para transporte HTTP o SSE, iniciar el servidor de forma independiente con `super-mcp --transport http --host 127.0.0.1 --port 8001` y configurar el harness hacia `http://127.0.0.1:8001`.

## Gestion de errores

Todas las herramientas retornan objetos JSON estructurados. En caso de error, la respuesta contiene `exception`, `message`, `line_number` y `traceback` completo. La ejecucion de codigo arbitrario mediante `execute_blender_code` incluye ademas `code_snippet` con la linea que produjo el fallo. El contexto 3D se resuelve mediante `temp_override` para evitar valores nulos en `bpy.context.active_object` y `selected_objects` durante ejecuciones en segundo plano.

## Licencia

GPL-3.0-or-later, compatible con el Free `blender-mcp` de referencia.

## Referencias

* Blender Python API. `bpy`, `bmesh`, `bpy.ops.export_scene.gltf`, `bpy.ops.object.modifier_add`.
* Especificacion gLTF 2.0. Formato de intercambio nativo para Godot 4.x y Redot.
* Protocolo MCP. Transporte stdio y streamable HTTP.

