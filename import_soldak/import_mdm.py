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

if __name__ != '__main__':
    import bpy
    import bmesh
    import mathutils

# Format ----

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

# Loader -----

def load(operator,
         context,
         filepath=""
         ):

    print("importing MDM: %r..." % (filepath), end="")

    time1 = time.clock()

    name = os.path.split(os.path.splitext(filepath)[0])[-1]

    with open(filepath, 'rb') as file:

        header = read_header(file)
        if header.id != 0x12121212:
            print('\tFatal Error:  Not a valid mdm file: %r' % filepath)
            file.close()
            return

        # Create a new mesh (not editable)
        mesh = bpy.data.meshes.new("mesh")
        obj = bpy.data.objects.new("Foo", mesh)

        scene = context.scene
        scene.objects.link(obj)
        scene.objects.active = obj
        obj.select = True

        # Make a bmesh (editable)
        mesh = context.object.data
        bm = bmesh.new()

        # Add the vertices
        file.seek(header.weightsOffset)
        vertices = []
        for _ in range(header.numVerts):
            weight = read_weight(file)
            vertices.append(bm.verts.new(weight.vertOffset))

        # Add the triangles
        file.seek(header.trisOffset)
        for _ in range(header.numTris):
            tri = read_tri(file)
            bm.faces.new([vertices[tri[0]], vertices[tri[1]], vertices[tri[2]]])

        # Convert back to mesh
        bm.to_mesh(mesh)
        bm.free()

        print(" done in %.4f sec." % (time.clock() - time1))

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
