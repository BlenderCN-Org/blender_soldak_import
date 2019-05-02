# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# Script copyright (C) Bob Holcomb
# Contributors: Bob Holcomb, Richard L?rk?ng, Damien McGinnes,
# Campbell Barton, Mario Lapin, Dominique Lorre, Andreas Atteneder

import sys
import os
import time
import struct
from collections import namedtuple

#import bpy
#import mathutils

HEADER_FORMAT = '<' + ('i' * 10)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

Header = namedtuple('Header', ['id', 'version', 'numSurfaces',
        'numTris', 'numVerts', 'surfaceOffset', 'trisOffset', 'vertsOffset',
        'weightsOffset', 'collapseMappingsOffset'])

def read_header(file):
    str = file.read(HEADER_SIZE)
    return Header._make(struct.unpack(HEADER_FORMAT, str))

SURFACE_FORMAT = '<' + ('i' * 6)
SURFACE_SIZE = struct.calcsize(SURFACE_FORMAT)
Surface = namedtuple('Surface', ['surfaceNumber', 'numVerts', 'numTris',
        'vertsOffset', 'trisOffset', 'collapseMappingsOffset'])

def read_surface(file):
    str = file.read(SURFACE_SIZE)
    return Surface._make(struct.unpack(SURFACE_FORMAT, str))

TRI_FORMAT = '<' + ('i' * 3)
TRI_SIZE = struct.calcsize(TRI_FORMAT)

def read_tri(file):
    str = file.read(TRI_SIZE)
    return struct.unpack(TRI_FORMAT, str)

VERT_FORMAT = '<' + ('f' * 2) + ('f' * 3) + ('f' * 4) + ('i' * 2)
VERT_SIZE = struct.calcsize(VERT_FORMAT)

Vert = namedtuple('Vert', ['u', 'v', 'normal', 'tangent', 'numBones', 'firstBone'])

def read_vert(file):
    str = file.read(VERT_SIZE)
    data = struct.unpack(VERT_FORMAT, str)
    v = Vert(data[0], data[1], (data[2], data[3], data[4]), (data[5], data[6], data[7], data[8]), data[9], data[10])
    return v

WEIGHT_FORMAT = '<i' + ('f' * 4)
WEIGHT_SIZE = struct.calcsize(WEIGHT_FORMAT)

Weight = namedtuple('Weight', ['boneIndex', 'vertOffset', 'boneWeight'])

def read_weight(file):
    str = file.read(WEIGHT_SIZE)
    data = struct.unpack(WEIGHT_FORMAT, str)
    w = Weight(data[0], (data[1], data[2], data[3]), data[4])
    return w


global scn
scn = None

def process_next_chunk(file, previous_chunk, importedObjects, IMAGE_SEARCH):
    from bpy_extras.image_utils import load_image

    def putContextMesh(myContextMesh_vertls, myContextMesh_facels, myContextMeshMaterials):
        bmesh = bpy.data.meshes.new(contextObName)

        if myContextMesh_facels is None:
            myContextMesh_facels = []

        if myContextMesh_vertls:

            bmesh.vertices.add(len(myContextMesh_vertls) // 3)
            bmesh.vertices.foreach_set("co", myContextMesh_vertls)

            nbr_faces = len(myContextMesh_facels)
            bmesh.polygons.add(nbr_faces)
            bmesh.loops.add(nbr_faces * 3)
            eekadoodle_faces = []
            for v1, v2, v3 in myContextMesh_facels:
                eekadoodle_faces.extend((v3, v1, v2) if v3 == 0 else (v1, v2, v3))
            bmesh.polygons.foreach_set("loop_start", range(0, nbr_faces * 3, 3))
            bmesh.polygons.foreach_set("loop_total", (3,) * nbr_faces)
            bmesh.loops.foreach_set("vertex_index", eekadoodle_faces)

            if bmesh.polygons and contextMeshUV:
                bmesh.uv_textures.new()
                uv_faces = bmesh.uv_textures.active.data[:]
            else:
                uv_faces = None

            for mat_idx, (matName, faces) in enumerate(myContextMeshMaterials):
                if matName is None:
                    bmat = None
                else:
                    bmat = MATDICT.get(matName)
                    # in rare cases no materials defined.
                    if bmat:
                        img = TEXTURE_DICT.get(bmat.name)
                    else:
                        print("    warning: material %r not defined!" % matName)
                        bmat = MATDICT[matName] = bpy.data.materials.new(matName)
                        img = None

                bmesh.materials.append(bmat)  # can be None

                if uv_faces  and img:
                    for fidx in faces:
                        bmesh.polygons[fidx].material_index = mat_idx
                        uv_faces[fidx].image = img
                else:
                    for fidx in faces:
                        bmesh.polygons[fidx].material_index = mat_idx

            if uv_faces:
                uvl = bmesh.uv_layers.active.data[:]
                for fidx, pl in enumerate(bmesh.polygons):
                    face = myContextMesh_facels[fidx]
                    v1, v2, v3 = face

                    # eekadoodle
                    if v3 == 0:
                        v1, v2, v3 = v3, v1, v2

                    uvl[pl.loop_start].uv = contextMeshUV[v1 * 2: (v1 * 2) + 2]
                    uvl[pl.loop_start + 1].uv = contextMeshUV[v2 * 2: (v2 * 2) + 2]
                    uvl[pl.loop_start + 2].uv = contextMeshUV[v3 * 2: (v3 * 2) + 2]
                    # always a tri

        bmesh.validate()
        bmesh.update()

        ob = bpy.data.objects.new(contextObName, bmesh)
        object_dictionary[contextObName] = ob
        SCN.objects.link(ob)
        importedObjects.append(ob)

        if contextMatrix_rot:
            ob.matrix_local = contextMatrix_rot
            object_matrix[ob] = contextMatrix_rot.copy()

def load_mdm(filepath,
             context,
             IMPORT_CONSTRAIN_BOUNDS=10.0,
             IMAGE_SEARCH=True,
             APPLY_MATRIX=True,
             global_matrix=None):
    global SCN

    print("importing MDM: %r..." % (filepath), end="")

    if bpy.ops.object.select_all.poll():
        bpy.ops.object.select_all(action='DESELECT')

    time1 = time.clock()

    with open(filepath, 'rb') as file:

        header = read_header(file)
        if header.id != 0x12121212:
            print('\tFatal Error:  Not a valid mdm file: %r' % filepath)
            file.close()
            return

        ##IMAGE_SEARCH

        # fixme, make unglobal, clear in case
        object_dictionary.clear()
        object_matrix.clear()

        scn = context.scene
    # 	scn = bpy.data.scenes.active
        SCN = scn
    # 	SCN_OBJECTS = scn.objects
    # 	SCN_OBJECTS.selected = [] # de select all

        importedObjects = []  # Fill this list with objects
        process_next_chunk(file, current_chunk, importedObjects, IMAGE_SEARCH)

        # fixme, make unglobal
        object_dictionary.clear()
        object_matrix.clear()

        # Link the objects into this scene.
        # Layers = scn.Layers

        # REMOVE DUMMYVERT, - remove this in the next release when blenders internal are fixed.

        if APPLY_MATRIX:
            for ob in importedObjects:
                if ob.type == 'MESH':
                    me = ob.data
                    me.transform(ob.matrix_local.inverted())

        # print(importedObjects)
        if global_matrix:
            for ob in importedObjects:
                if ob.parent is None:
                    ob.matrix_world = ob.matrix_world * global_matrix

        for ob in importedObjects:
            ob.select = True

        # Done DUMMYVERT
        """
        if IMPORT_AS_INSTANCE:
            name = filepath.split('\\')[-1].split('/')[-1]
            # Create a group for this import.
            group_scn = Scene.New(name)
            for ob in importedObjects:
                group_scn.link(ob) # dont worry about the layers

            grp = Blender.Group.New(name)
            grp.objects = importedObjects

            grp_ob = Object.New('Empty', name)
            grp_ob.enableDupGroup = True
            grp_ob.DupGroup = grp
            scn.link(grp_ob)
            grp_ob.Layers = Layers
            grp_ob.sel = 1
        else:
            # Select all imported objects.
            for ob in importedObjects:
                scn.link(ob)
                ob.Layers = Layers
                ob.sel = 1
        """

        context.scene.update()

        axis_min = [1000000000] * 3
        axis_max = [-1000000000] * 3
        global_clamp_size = IMPORT_CONSTRAIN_BOUNDS
        if global_clamp_size != 0.0:
            # Get all object bounds
            for ob in importedObjects:
                for v in ob.bound_box:
                    for axis, value in enumerate(v):
                        if axis_min[axis] > value:
                            axis_min[axis] = value
                        if axis_max[axis] < value:
                            axis_max[axis] = value

            # Scale objects
            max_axis = max(axis_max[0] - axis_min[0],
                        axis_max[1] - axis_min[1],
                        axis_max[2] - axis_min[2])
            scale = 1.0

            while global_clamp_size < max_axis * scale:
                scale = scale / 10.0

            scale_mat = mathutils.Matrix.Scale(scale, 4)

            for obj in importedObjects:
                if obj.parent is None:
                    obj.matrix_world = scale_mat * obj.matrix_world

        # Select all new objects.
        print(" done in %.4f sec." % (time.clock() - time1))


def load(operator,
         context,
         filepath="",
         constrain_size=0.0,
         use_image_search=True,
         use_apply_transform=True,
         global_matrix=None,
         ):

    load_mdm(filepath,
             context,
             IMPORT_CONSTRAIN_BOUNDS=constrain_size,
             IMAGE_SEARCH=use_image_search,
             APPLY_MATRIX=use_apply_transform,
             global_matrix=global_matrix,
             )

    return {'FINISHED'}

if __name__ == '__main__':
    filename = sys.argv[1]
    with open(filename, 'rb') as f:
        header = read_header(f)
        print("Header: ", header)
        print("vertsOffset: {:x}".format(header.vertsOffset))

        f.seek(header.surfaceOffset)
        for surf_num in range(header.numSurfaces):
            surface = read_surface(f)
            print("Surface ", surf_num, " :", surface)

        f.seek(header.trisOffset)
        for tri_num in range(header.numTris):
            tri = read_tri(f)
            print("Tri ", tri_num, " :", tri)

        # Vertices ---
        f.seek(header.vertsOffset)
        for vert_num in range(header.numVerts):
            vert = read_vert(f)
            print("Vertice ", vert_num, " :", vert)

        f.seek(header.weightsOffset)
        for weight_num in range(header.numVerts):
            weight = read_weight(f)
            print("Weight ", weight_num, " :", weight)
