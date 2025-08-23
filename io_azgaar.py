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

def create_mesh(settings, context, name):

    # Create a new mesh object
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(mesh.name, mesh)

    # Rescale to user-defined settings
    obj.scale = (settings.scale, settings.scale, settings.scale)

    # Set as active & selected for any subsequent operations
    context.collection.objects.link(obj)
    context.view_layer.objects.active = obj
    context.object.select_set(True)

    return obj


################################################################################
# AZGAAR DATA & OBJECT OPERATIONS
################################################################################

# Extract & reformat raw JSON data ---------------------------------------------

def prepare_data(raw):

    # Extract coords of cell-border vertices and remove duplicates
    vtx_raw = [(v["p"][0], v["p"][1]) for v in raw["grid"]["vertices"]]
    vtx_uniq = list(set(vtx_raw))

    # Map original vertex indices to their new index in the non-duplicate set
    xref = {coord: i for i, coord in enumerate(vtx_uniq)}
    xref = {old: xref[coord] for old, coord in enumerate(vtx_raw)}

    # Represent each cell as an ordered list of unique vertices to form a face
    faces = [[xref[v] for v in c["v"]] for c in raw["grid"]["cells"]]
    faces = [list(dict.fromkeys(f)) for f in faces]

    # Create a mapping between "border" vertices and all their adjacent cells
    vtx_cells = [[] for i in range(len(vtx_uniq))]
    for cell_id, f in enumerate(faces):
        for v in f:
            vtx_cells[v].append(cell_id)

    # Extract the height for the center of each cell
    cell_height = [c["h"] for c in raw["grid"]["cells"]]

    # Default border vertex height is the average height of its adjacent cells
    vtx_height = [
        sum([cell_height[c] for c in cells]) / len(cells) 
        for cells in vtx_cells
    ]

    # Add the elevation to the vertex coordinates, center on (0, 0), and flip y
    vtx_coords = [
        (x - raw["info"]["width"] / 2, -y + raw["info"]["height"] / 2, z)
        for ((x, y), z) in zip(vtx_uniq, vtx_height)
    ]

    # Combine all output into a final nested dataset
    cleaned = {
        "vertices": {
            "coords": vtx_coords,
            "cells": vtx_cells
        },
        "cells": {
            "vertices": faces,
            "height": cell_height,
            "biome_id":   [cell["b"] for cell in raw["grid"]["cells"]],
            "feature_id": [cell["f"] for cell in raw["grid"]["cells"]]
        },
        "canvas": {
            "width":  raw["info"]["width"],
            "height": raw["info"]["height"]
        }
    }

    return cleaned


# Create a mesh for the base heightmap -----------------------------------------

def create_heightmap(settings, context, data):
    obj = create_mesh(settings, context, "Heightmap")

    with bmesh_from_obj(obj) as bm:

        # Add vertices for all cell borders to the mesh
        for v in data["vertices"]["coords"]:
            bm.verts.new(v)

        bm.verts.ensure_lookup_table()

        # Create mesh faces from cell borders
        for f in data["cells"]["vertices"]:
            bm.faces.new([bm.verts[v] for v in f])

        # Generate a new vertex at each cell center & assign it the cell height
        ctr = bmesh.ops.poke(bm, faces = bm.faces)
        for (v, h) in zip(ctr["verts"], data["cells"]["height"]): 
            v.co.z = h

    return obj


# Add an ocean plane based on canvas size --------------------------------------

def create_ocean(settings, context, data):

    # Use canvas size to create 4 corners
    w = data["canvas"]["width"]
    h = data["canvas"]["height"]

    obj = create_mesh(settings, context, "Ocean")

    # Add the corners of the plane as mesh vertices and create its face
    with bmesh_from_obj(obj) as bm:
        bm.verts.new((-w / 2, -h / 2, settings.sea_level))
        bm.verts.new(( w / 2, -h / 2, settings.sea_level))
        bm.verts.new(( w / 2,  h / 2, settings.sea_level))
        bm.verts.new((-w / 2,  h / 2, settings.sea_level))
        bm.faces.new(bm.verts)

    return obj


# Import JSON & manage creation of blender objects -----------------------------

def import_azgaar(settings, context):
    if settings.filepath:
        try:
            with open(settings.filepath, "r") as f:
                raw = json.load(f)

            data = prepare_data(raw)
            heightmap = create_heightmap(settings, context, data)
            ocean = create_ocean(settings, context, data)

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

    scale: bpy.props.FloatProperty(
        name = "Scale", 
        default = 0.01,
        min = 0.001,
        max = 1,
        step = 1
    ) # type: ignore

    sea_level: bpy.props.FloatProperty(
        name = "Sea Level (0-100)", 
        default = 15,
        min = 0,
        max = 100,
        step = 100,
    ) # type: ignore

    def execute(self, context):
        import_azgaar(self, context)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout.column(align = False)
        layout.prop(self, "scale")
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
