"""Blender integration tests for UV Island To Mesh."""

import importlib
import math
import pathlib
import sys

import bmesh
import bpy


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "addon"))
addon = importlib.import_module("island_tool")


def reset_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_mesh(name, vertices, faces, uvs):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon, face_uvs in zip(mesh.polygons, uvs):
        for loop_index, uv in zip(polygon.loop_indices, face_uvs):
            uv_layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    return obj


def select_a_then_b(obj, index_a, index_b):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for vertex in bm.verts:
        vertex.select_set(False)
    for edge in bm.edges:
        edge.select_set(False)
    for face in bm.faces:
        face.select_set(False)
    bm.select_history.clear()
    vertex_a = bm.verts[index_a]
    vertex_b = bm.verts[index_b]
    vertex_a.select_set(True)
    bm.select_history.add(vertex_a)
    vertex_b.select_set(True)
    bm.select_history.add(vertex_b)
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def assert_operator_error(message):
    try:
        bpy.ops.island_tool.duplicate_island_from_uv("EXEC_DEFAULT")
    except RuntimeError as error:
        assert message in str(error), error
    else:
        raise AssertionError("The operator accepted invalid input")


def test_success_preserves_area_and_aligns_ab():
    obj = create_mesh(
        "Success",
        [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0)],
        [(0, 1, 2, 3)],
        [[(0, 0), (1, 0), (1, 1), (0, 1)]],
    )
    select_a_then_b(obj, 0, 1)

    result = bpy.ops.island_tool.duplicate_island_from_uv("EXEC_DEFAULT")
    assert result == {"FINISHED"}, result

    bm = bmesh.from_edit_mesh(obj.data)
    selected = [vertex for vertex in bm.verts if vertex.select]
    selected_faces = [
        face for face in bm.faces if all(vertex.select for vertex in face.verts)
    ]
    assert len(bm.verts) == 8
    assert len(bm.faces) == 2
    assert len(selected) == 4
    assert len(selected_faces) == 1
    assert math.isclose(selected_faces[0].calc_area(), 2.0, rel_tol=1.0e-6)

    duplicate_b = bm.select_history.active
    history = [element for element in bm.select_history]
    duplicate_a = history[-2]
    direction = duplicate_b.co - duplicate_a.co
    assert abs(direction.x) < 1.0e-6
    assert direction.y > 0.0
    assert abs(direction.z) < 1.0e-6
    assert all(abs(vertex.co.z) < 1.0e-7 for vertex in selected)


def test_seam_boundary_ambiguity_changes_nothing():
    obj = create_mesh(
        "Ambiguous",
        [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)],
        [(0, 1, 4, 3), (1, 2, 5, 4)],
        [
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            [(1, 0), (2, 0), (2, 1), (1, 1)],
        ],
    )
    bm = bmesh.from_edit_mesh(obj.data)
    seam = next(
        edge
        for edge in bm.edges
        if {vertex.index for vertex in edge.verts} == {1, 4}
    )
    seam.seam = True
    bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
    select_a_then_b(obj, 1, 4)
    counts = (len(bm.verts), len(bm.edges), len(bm.faces))

    assert_operator_error("match more than one seam-bounded face island")
    bm = bmesh.from_edit_mesh(obj.data)
    assert (len(bm.verts), len(bm.edges), len(bm.faces)) == counts


def test_split_uv_on_one_mesh_vertex_changes_nothing():
    obj = create_mesh(
        "SplitUV",
        [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0), (1, 1, 0), (2, 1, 0)],
        [(0, 1, 4, 3), (1, 2, 5, 4)],
        [
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            [(1.25, 0), (2, 0), (2, 1), (1.25, 1)],
        ],
    )
    select_a_then_b(obj, 0, 2)
    bm = bmesh.from_edit_mesh(obj.data)
    counts = (len(bm.verts), len(bm.edges), len(bm.faces))

    assert_operator_error("has multiple UV coordinates inside the island")
    bm = bmesh.from_edit_mesh(obj.data)
    assert (len(bm.verts), len(bm.edges), len(bm.faces)) == counts


def main():
    addon.register()
    try:
        reset_scene()
        test_success_preserves_area_and_aligns_ab()
        reset_scene()
        test_seam_boundary_ambiguity_changes_nothing()
        reset_scene()
        test_split_uv_on_one_mesh_vertex_changes_nothing()
    finally:
        reset_scene()
        addon.unregister()
    print("All Island Tool UV integration tests passed")


if __name__ == "__main__":
    main()
