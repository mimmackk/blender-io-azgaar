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

def create_mesh(self, context, name):

    # Create a new mesh object
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(mesh.name, mesh)

    # Set as active & selected for any subsequent operations
    context.collection.objects.link(obj)
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

    return {"w": w, "h": h, "x": x, "y": y, "z": z, "vtx": vtx, "faces": faces}


# Create a mesh for the base heightmap -----------------------------------------

def create_heightmap(self, context, data):

    obj = create_mesh(self, context, "Heightmap")

    with bmesh_from_obj(obj) as bm:
        for v in data["vtx"]:
            bm.verts.new(v)

        bm.verts.ensure_lookup_table()

        for f in data["faces"]:
            bm.faces.new((bm.verts[v] for v in f))

    return obj


# Smooth the heightmap ---------------------------------------------------------

def smooth_heightmap(self, heightmap):
    with bmesh_from_obj(heightmap) as bm:
        bmesh.ops.subdivide_edges(
            bm, 
            edges = bm.edges, 
            cuts = 1, 
            use_grid_fill = True
        )
        bmesh.ops.triangulate(bm, faces = bm.faces)
        bmesh.ops.smooth_vert(
            bm, 
            verts = bm.verts, 
            factor = 1, 
            use_axis_x = True,
            use_axis_y = True,
            use_axis_z = True
        )


# Add an ocean plane -----------------------------------------------------------

def create_ocean_plane(self, context, data):

    # Create a new, empty mesh and set as active & selected
    obj = create_mesh(self, context, "Ocean")

    w = data["w"]
    h = data["h"]

    # Use canvas size to create 4 corners
    with bmesh_from_obj(obj) as bm:
        bm.verts.new((-w / 2, -h / 2, self.sea_level * self.z_scale))
        bm.verts.new(( w / 2, -h / 2, self.sea_level * self.z_scale))
        bm.verts.new(( w / 2,  h / 2, self.sea_level * self.z_scale))
        bm.verts.new((-w / 2,  h / 2, self.sea_level * self.z_scale))
        bm.faces.new(bm.verts)

    return obj


# Import JSON & manage creation of blender objects -----------------------------

def import_azgaar(self, context):
    if self.filepath:
        try:
            with open(self.filepath, "r") as f:
                raw = json.load(f)

            data = prepare_data(self, raw)
            ocean = create_ocean_plane(self, context, data)
            heightmap = create_heightmap(self, context, data)
            smooth_heightmap(self, heightmap)

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
