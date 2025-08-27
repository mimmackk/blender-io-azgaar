bl_info = {
    "name": "Import Azgaar Fantasy Map",
    "author": "mimmackk",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "category": "Import-Export",
}

import bpy
import json
import bmesh
from bpy_extras.io_utils import ImportHelper
from contextlib import contextmanager

################################################################################
# BLENDER OBJECT HELPERS
################################################################################

# Context manager for BMesh operations -----------------------------------------
# Thanks to Diego Gangl for this function!
# https://sinestesia.co/blog/tutorials/bmeshing-with-context-managers/

@contextmanager
def bmesh_from_obj(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)

    yield bm

    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()


# Create a new empty mesh object -----------------------------------------------

def create_mesh(self, context, collection, name):

    # Create a new mesh object within collection
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(mesh.name, mesh)
    collection.objects.link(obj)

    # Set as active & selected for any subsequent operations
    context.view_layer.objects.active = obj
    context.object.select_set(True)

    return obj


# Convert vertex color layer into a mesh material ------------------------------

def vtx_color_to_material(self, obj, name):

    # Create a new material and link it to the mesh object
    mat = bpy.data.materials.new(name = name)
    mat.use_nodes = True
    obj.data.materials.append(mat)

    # Get the node for the default material shader
    node_bsdf = mat.node_tree.nodes.get("Principled BSDF")

    # Create a new node to pull data from the designated vertex color layer
    node_vtx_color = mat.node_tree.nodes.new(type = "ShaderNodeVertexColor")
    node_vtx_color.layer_name = name

    # Direct the vertex color node output into the material shader node input
    mat.node_tree.links.new(node_vtx_color.outputs[0], node_bsdf.inputs[0])


# Apply colors to vertices of a mesh object ------------------------------------

def color_vertices(self, obj, vtx_color, name):
    with bmesh_from_obj(obj) as bm:
        layer = bm.loops.layers.color.new(name)
        name = layer.name
        for f in bm.faces:
            for loop in f.loops:
                loop[layer] = vtx_color[loop.vert.index]

    # Set the new vertex color layer as the active layer & link to a material
    obj.data.attributes.active_color = obj.data.color_attributes.get(name)
    vtx_color_to_material(self, obj, name)


# Normalize a mesh object by subdividing and smoothing its vertices ------------

def normalize_mesh(self, obj, n_cuts, smooth_factor, smooth_x, smooth_y, smooth_z):
    with bmesh_from_obj(obj) as bm:
        bmesh.ops.subdivide_edges(
            bm, 
            edges = bm.edges, 
            cuts = n_cuts, 
            use_grid_fill = True
        )
        bmesh.ops.triangulate(bm, faces = bm.faces)
        bmesh.ops.smooth_vert(
            bm, 
            verts = bm.verts, 
            factor = smooth_factor, 
            use_axis_x = smooth_x,
            use_axis_y = smooth_y,
            use_axis_z = smooth_z
        )


# Create a bezier curve --------------------------------------------------------

def create_bezier(self, context, collection, name, coords):

    # Create a new, empty curve and within collection
    curve = bpy.data.curves.new(name, type = 'CURVE')
    obj = bpy.data.objects.new(curve.name, curve)
    collection.objects.link(obj)

    # Set global settings of the curve
    curve.dimensions = '2D'
    curve.resolution_u = 12
    curve.bevel_depth = 0.1  # relates to river width

    # Map coordinates to a spline
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(len(coords) - 1)
    for i, p in enumerate(coords):
        spline.bezier_points[i].co = p
        spline.bezier_points[i].handle_left_type  = 'AUTO'
        spline.bezier_points[i].handle_right_type = 'AUTO'

    # Set as active & selected for any subsequent operations
    context.view_layer.objects.active = obj
    context.object.select_set(True)

    return obj


################################################################################
# AZGAAR DATA & OBJECT OPERATIONS
################################################################################

# Extract cell data from raw JSON ----------------------------------------------

def prepare_data(self, raw):

    w = raw["grid"]["cellsX"]
    h = raw["grid"]["cellsY"]
    x = [ x - (w - 1) / 2 for y in range(h) for x in range(w)]
    y = [-y + (h - 1) / 2 for y in range(h) for x in range(w)]
    z = [c["h"] * self.z_scale for c in raw["grid"]["cells"]]

    vtx = tuple(zip(x, y, z))
    faces = [
        (
            w * (yi + 1) + xi,
            w * (yi + 1) + xi + 1,
            w * yi + xi + 1,
            w * yi + xi,
        )
        for yi in range(h - 1)
        for xi in range(w - 1)
    ]

    # Extract biomes from the pack object & default to zero where not given
    biome_id = [0] * len(raw["grid"]["cells"])
    for c in raw["pack"]["cells"]:
        biome_id[c["g"]] = c["biome"]

    # Convert biome colors from hex to RGBA notation
    biome_rgb = [
        [int((h.lstrip('#') + 'ff')[i:i+2], 16) / 255 for i in (0, 2, 4, 6)]
        for h in raw["biomesData"]["color"]
    ]

    # Assign each vertex a color based on its biome
    color = [biome_rgb[b] for b in biome_id]

    cell_to_grid = [c["g"] for c in raw["pack"]["cells"]]

    river = {
        "cells": [
            list(dict.fromkeys([cell_to_grid[c] for c in river["cells"] if c != -1]))
            for river in raw["pack"]["rivers"]
        ],
        "width": [c["width"] for c in raw["pack"]["rivers"]],
        "width_factor": [c["widthFactor"] for c in raw["pack"]["rivers"]],
        "source_width": [c["sourceWidth"] for c in raw["pack"]["rivers"]]
    }

    return {
        "w": w, 
        "h": h, 
        "x": x, 
        "y": y, 
        "z": z, 
        "vtx": vtx, 
        "faces": faces, 
        "color": color,
        "biome_rgb": biome_rgb,
        "river": river
    }


# Create a mesh for the base heightmap -----------------------------------------

def create_heightmap(self, context):

    obj = create_mesh(self, context, self.collection, "Heightmap")

    with bmesh_from_obj(obj) as bm:
        for v in self.data["vtx"]:
            bm.verts.new(v)

        bm.verts.ensure_lookup_table()

        for f in self.data["faces"]:
            bm.faces.new((bm.verts[v] for v in f))

    color_vertices(self, obj, self.data["color"], "Biomes")
    normalize_mesh(self, obj, 1, 1, True, True, True)

    return obj


# Add an ocean plane -----------------------------------------------------------

def create_ocean_plane(self, context):

    # Create a new, empty mesh and set as active & selected
    obj = create_mesh(self, context, self.collection, "Ocean")

    w = self.data["w"]
    h = self.data["h"]

    # Use canvas size to create 4 corners
    with bmesh_from_obj(obj) as bm:
        bm.verts.new((-w / 2, -h / 2, self.sea_level * self.z_scale))
        bm.verts.new(( w / 2, -h / 2, self.sea_level * self.z_scale))
        bm.verts.new(( w / 2,  h / 2, self.sea_level * self.z_scale))
        bm.verts.new((-w / 2,  h / 2, self.sea_level * self.z_scale))
        bm.faces.new(bm.verts)

    color_vertices(self, obj, [self.data["biome_rgb"][0]] * 4, "Ocean")

    return obj


# Create rivers as bezier curves -----------------------------------------------

def create_rivers(self, context, heightmap):

    # Create a new sub-collection for all rivers
    coll = bpy.data.collections.new("Rivers")
    self.collection.children.link(coll)

    # Get the current X-Y coordinates of each cell on the smoothed heightmap
    cell_coords = [(v.co.x, v.co.y, 0) for v in heightmap.data.vertices]
    river_coords = [
        [cell_coords[c] for c in clist] 
        for clist in self.data["river"]["cells"]
    ]

    # Create a blue river material
    mat = bpy.data.materials.new(name = "River")
    mat.diffuse_color = self.data["biome_rgb"][0]

    # Create bezier curve objects for each river
    objs = [
        create_bezier(self, context, coll, f"River {i:03d}", coords)
        for i, coords in enumerate(river_coords)
    ]

    # Mold the river to the heightmap surface & apply blue water material
    for obj in objs:
        modifier = obj.modifiers.new(name = "Shrinkwrap", type = 'SHRINKWRAP')
        modifier.target = heightmap
        modifier.wrap_method = 'PROJECT'
        modifier.wrap_mode = 'ABOVE_SURFACE'
        modifier.use_project_x = False
        modifier.use_project_y = False
        modifier.use_project_z = True
        modifier.offset = 0.01
        obj.data.materials.append(mat)

    return objs


# Import JSON & manage creation of blender objects -----------------------------

def import_azgaar(self, context):
    if self.filepath:
        try:
            with open(self.filepath, "r") as f:
                raw_data = json.load(f)

            # Generate a new collection to store all Azgaar objects
            map_name = raw_data["info"]["mapName"]
            self.collection = bpy.data.collections.new(map_name)
            context.scene.collection.children.link(self.collection)

            # Extract & reformat relevant data from raw JSON export
            self.data = prepare_data(self, raw_data)

            # Convert data into blender objects
            ocean = create_ocean_plane(self, context)
            heightmap = create_heightmap(self, context)
            rivers = create_rivers(self, context, heightmap)

            pass

        except Exception as e:
            print("Failed to import Azgaar JSON: ", e)


################################################################################
# SETUP & UI
################################################################################

class ImportAzgaar(bpy.types.Operator, ImportHelper):
    """Import from Azgaar Fantasy Map Generator (Full JSON)"""
    bl_idname = "import.azgaar"
    bl_label = "Azgaar Fantasy Map (.json)"
    bl_options = {'REGISTER', 'UNDO'}
    filename_ext = ".json"

    filter_glob: bpy.props.StringProperty(
        default = "*.json",
        options = {'HIDDEN'}
    ) # type: ignore

    z_scale: bpy.props.FloatProperty(
        name = "Z Scale", 
        default = 0.1,
        min = 0.001,
        max = 1,
        step = 1
    ) # type: ignore

    sea_level: bpy.props.FloatProperty(
        name = "Sea Level (0-100)", 
        default = 10,
        min = 0,
        max = 100,
        step = 100,
    ) # type: ignore

    def execute(self, context):
        import_azgaar(self, context)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout.column(align = False)
        layout.prop(self, "z_scale")
        layout.prop(self, "sea_level")

def menu_func(self, context):
    self.layout.operator(ImportAzgaar.bl_idname)

def register():
    bpy.utils.register_class(ImportAzgaar)    
    bpy.types.TOPBAR_MT_file_import.append(menu_func)

def unregister():
    bpy.utils.unregister_class(ImportAzgaar)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)

if __name__ == "__main__":
    register()
