"""Operator that creates a planar mesh copy from a seam-bounded UV island."""

import math
from dataclasses import dataclass

import bmesh
import bpy
from mathutils import Vector

from .translations import iface_, iface_format


EPSILON = 1.0e-12
UV_TOLERANCE = 1.0e-7


@dataclass(frozen=True)
class IslandPlan:
    faces: tuple
    edges: tuple
    vertices: tuple
    coordinates: dict
    vertex_a: object
    vertex_b: object
    original_area: float
    scale: float


def _face_islands(bm):
    """Return face components connected only across edges that are not seams."""
    remaining = set(bm.faces)
    islands = []
    while remaining:
        start = min(remaining, key=lambda face: face.index)
        remaining.remove(start)
        island = {start}
        stack = [start]
        while stack:
            face = stack.pop()
            for edge in face.edges:
                if edge.seam:
                    continue
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        island.add(neighbor)
                        stack.append(neighbor)
        islands.append(island)
    return islands


def _ordered_selection(bm):
    selected = [vertex for vertex in bm.verts if vertex.select]
    if len(selected) != 2:
        raise ValueError(
            f"Select exactly two vertices; found {len(selected)} selected vertices."
        )

    vertex_b = bm.select_history.active
    if not isinstance(vertex_b, bmesh.types.BMVert) or vertex_b not in selected:
        raise ValueError(
            "The last selected element must be vertex B. Select A first, then B."
        )
    vertex_a = selected[0] if selected[1] is vertex_b else selected[1]
    return vertex_a, vertex_b


def _unique_island(bm, vertex_a, vertex_b):
    candidates = []
    for faces in _face_islands(bm):
        vertices = {loop.vert for face in faces for loop in face.loops}
        if vertex_a in vertices and vertex_b in vertices:
            candidates.append((faces, vertices))

    if not candidates:
        raise ValueError(
            "A and B do not belong to the same seam-bounded face island."
        )
    if len(candidates) != 1:
        raise ValueError(
            "A and B match more than one seam-bounded face island; choose a "
            "pair that identifies exactly one island."
        )
    return candidates[0]


def _vertex_uvs(faces, vertices, uv_layer):
    uv_by_vertex = {}
    for face in faces:
        for loop in face.loops:
            uv = loop[uv_layer].uv.copy()
            if not (math.isfinite(uv.x) and math.isfinite(uv.y)):
                raise ValueError(
                    f"Vertex {loop.vert.index} has a non-finite UV coordinate."
                )
            previous = uv_by_vertex.get(loop.vert)
            if previous is None:
                uv_by_vertex[loop.vert] = uv
            elif (uv - previous).length > UV_TOLERANCE:
                raise ValueError(
                    f"Vertex {loop.vert.index} has multiple UV coordinates inside "
                    "the island. Split the mesh vertex or make its UV unique first."
                )

    missing = vertices.difference(uv_by_vertex)
    if missing:
        indices = ", ".join(str(vertex.index) for vertex in sorted(
            missing,
            key=lambda vertex: vertex.index,
        ))
        raise ValueError(f"The following island vertices have no UV: {indices}.")
    return uv_by_vertex


def _triangle_data(bm, faces, uv_layer):
    face_set = set(faces)
    triangles = []
    for loops in bm.calc_loop_triangles():
        if loops[0].face not in face_set:
            continue
        uvs = tuple(loop[uv_layer].uv.copy() for loop in loops)
        twice_area = abs(
            (uvs[1].x - uvs[0].x) * (uvs[2].y - uvs[0].y)
            - (uvs[1].y - uvs[0].y) * (uvs[2].x - uvs[0].x)
        )
        triangles.append((uvs, 0.5 * twice_area))
    if not triangles:
        raise ValueError("The identified island cannot be triangulated.")
    return triangles


def _area_centroid(triangles):
    weighted = Vector((0.0, 0.0))
    total_area = 0.0
    for uvs, area in triangles:
        if area <= EPSILON:
            continue
        triangle_centroid = (uvs[0] + uvs[1] + uvs[2]) / 3.0
        weighted += triangle_centroid * area
        total_area += area
    if total_area <= EPSILON:
        raise ValueError("The island has zero UV area and cannot be scaled.")
    return weighted / total_area


def _build_plan(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        raise ValueError("An active mesh object is required.")
    if obj.mode != "EDIT":
        raise ValueError("Switch the active mesh to Edit Mode first.")
    if tuple(context.tool_settings.mesh_select_mode) != (True, False, False):
        raise ValueError("Switch to Vertex Select mode before running this operator.")

    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    vertex_a, vertex_b = _ordered_selection(bm)
    faces, vertex_set = _unique_island(bm, vertex_a, vertex_b)
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        raise ValueError("The mesh has no active UV map.")

    uv_by_vertex = _vertex_uvs(faces, vertex_set, uv_layer)
    triangles = _triangle_data(bm, faces, uv_layer)
    original_area = sum(face.calc_area() for face in faces)
    if not math.isfinite(original_area) or original_area <= EPSILON:
        raise ValueError("The original island has zero or invalid surface area.")

    uv_area = sum(area for _uvs, area in triangles)
    if not math.isfinite(uv_area) or uv_area <= EPSILON:
        raise ValueError("The island has zero or invalid UV area.")
    scale = math.sqrt(original_area / uv_area)
    if not math.isfinite(scale):
        raise ValueError("The required area-preserving scale is not finite.")

    scaled_a = uv_by_vertex[vertex_a] * scale
    scaled_b = uv_by_vertex[vertex_b] * scale
    direction = scaled_b - scaled_a
    if direction.length <= EPSILON:
        raise ValueError(
            "A and B have the same UV coordinate; their direction is undefined."
        )

    centroid = _area_centroid(triangles) * scale
    angle = math.pi * 0.5 - math.atan2(direction.y, direction.x)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    coordinates = {}
    for vertex, uv in uv_by_vertex.items():
        scaled = uv * scale
        relative = scaled - centroid
        rotated = Vector((
            cosine * relative.x - sine * relative.y,
            sine * relative.x + cosine * relative.y,
        )) + centroid
        if not (math.isfinite(rotated.x) and math.isfinite(rotated.y)):
            raise ValueError("The calculated mesh coordinates are not finite.")
        coordinates[vertex] = Vector((rotated.x, rotated.y, 0.0))

    edges = {edge for face in faces for edge in face.edges}
    vertices = tuple(sorted(vertex_set, key=lambda vertex: vertex.index))
    return bm, IslandPlan(
        faces=tuple(sorted(faces, key=lambda face: face.index)),
        edges=tuple(sorted(edges, key=lambda edge: edge.index)),
        vertices=vertices,
        coordinates=coordinates,
        vertex_a=vertex_a,
        vertex_b=vertex_b,
        original_area=original_area,
        scale=scale,
    )


def _apply_plan(obj, bm, plan):
    source_geometry = [*plan.vertices, *plan.edges, *plan.faces]
    selected_vertices = {vertex for vertex in bm.verts if vertex.select}
    selected_edges = {edge for edge in bm.edges if edge.select}
    selected_faces = {face for face in bm.faces if face.select}
    selection_history = tuple(bm.select_history)
    result = None
    try:
        result = bmesh.ops.duplicate(bm, geom=source_geometry)
        geometry_map = result.get("vert_map") or result.get("geom_map")
        if geometry_map is None:
            raise RuntimeError("Blender did not return a duplicate vertex map.")
        duplicate_by_source = {}
        duplicate_vertices = []
        for source in plan.vertices:
            duplicate = geometry_map.get(source)
            if not isinstance(duplicate, bmesh.types.BMVert):
                duplicate = next(
                    (
                        candidate
                        for candidate, original in geometry_map.items()
                        if original is source
                        and isinstance(candidate, bmesh.types.BMVert)
                    ),
                    None,
                )
            if not isinstance(duplicate, bmesh.types.BMVert):
                raise RuntimeError("Blender did not return a complete vertex copy map.")
            duplicate_by_source[source] = duplicate
            duplicate.co = plan.coordinates[source]
            duplicate_vertices.append(duplicate)

        for vertex in bm.verts:
            vertex.select_set(False)
        for edge in bm.edges:
            edge.select_set(False)
        for face in bm.faces:
            face.select_set(False)
        bm.select_history.clear()
        for vertex in duplicate_vertices:
            vertex.select_set(True)
        bm.select_history.add(duplicate_by_source[plan.vertex_a])
        bm.select_history.add(duplicate_by_source[plan.vertex_b])
        bm.select_flush_mode()
        bm.normal_update()
        bmesh.update_edit_mesh(obj.data, loop_triangles=True, destructive=True)
        return len(duplicate_vertices), len(plan.faces)
    except Exception:
        if result is not None:
            new_vertices = [
                element
                for element in result.get("geom", ())
                if isinstance(element, bmesh.types.BMVert) and element.is_valid
            ]
            if new_vertices:
                bmesh.ops.delete(bm, geom=new_vertices, context="VERTS")
        for vertex in bm.verts:
            vertex.select_set(vertex in selected_vertices)
        for edge in bm.edges:
            edge.select_set(edge in selected_edges)
        for face in bm.faces:
            face.select_set(face in selected_faces)
        bm.select_history.clear()
        for element in selection_history:
            if element.is_valid:
                bm.select_history.add(element)
        bmesh.update_edit_mesh(
            obj.data,
            loop_triangles=False,
            destructive=True,
        )
        raise


class ISLANDTOOL_OT_duplicate_island_from_uv(bpy.types.Operator):
    bl_idname = "island_tool.duplicate_island_from_uv"
    bl_label = "Duplicate Island from UV"
    bl_description = (
        "Duplicate the seam-bounded face island identified by A then B, rebuild "
        "it on XY from UVs, preserve its surface area, and align A to B with +Y"
    )
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode != "EDIT":
            cls.poll_message_set("An active mesh in Edit Mode is required")
            return False
        return True

    def execute(self, context):
        try:
            bm, plan = _build_plan(context)
            vertex_count, face_count = _apply_plan(context.active_object, bm, plan)
        except Exception as error:
            self.report({"ERROR"}, iface_(str(error)))
            return {"CANCELLED"}

        self.report(
            {"INFO"},
            iface_format(
                "Created UV island copy: {faces} faces, {vertices} vertices, area scale {scale:.6g}.",
                faces=face_count,
                vertices=vertex_count,
                scale=plan.scale,
            ),
        )
        return {"FINISHED"}
