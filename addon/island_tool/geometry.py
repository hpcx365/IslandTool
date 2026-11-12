"""Read-only extraction and validation of planar mesh face islands."""

import math
from dataclasses import dataclass

import pyclipper
from mathutils import Matrix

EPSILON = 1.0e-7
COORDINATE_SCALE = 1_000_000


@dataclass(frozen=True)
class IslandGeometry:
    island_id: int
    face_indices: tuple[int, ...]
    vertex_indices: tuple[int, ...]
    contour: tuple[tuple[float, float], ...]
    area: float
    bounds: tuple[float, float, float, float]


def _is_identity_matrix(matrix):
    identity = Matrix.Identity(4)
    return all(
        abs(matrix[row][column] - identity[row][column]) <= EPSILON
        for row in range(4)
        for column in range(4)
    )


def validate_object(object_):
    if object_ is None or object_.type != "MESH":
        raise ValueError("Select one active mesh object.")
    if object_.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before nesting.")
    if not _is_identity_matrix(object_.matrix_world):
        raise ValueError(
            "The active object's world transform must have zero location and "
            "rotation and unit scale."
        )
    if object_.data.shape_keys is not None:
        raise ValueError("Meshes with shape keys are not supported.")
    if object_.modifiers:
        raise ValueError("Apply or remove all modifiers before nesting.")
    if not object_.data.polygons:
        raise ValueError("The active mesh has no faces.")
    if any(abs(vertex.co.z) > EPSILON for vertex in object_.data.vertices):
        raise ValueError("Every mesh vertex must lie on the local XY plane (Z = 0).")


def _face_components(mesh):
    edge_faces = [[] for _edge in mesh.edges]
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            edge_faces[mesh.loops[loop_index].edge_index].append(polygon.index)

    if any(not faces for faces in edge_faces):
        raise ValueError("Loose edges are not supported.")
    if any(len(faces) > 2 for faces in edge_faces):
        raise ValueError("Non-manifold edges are not supported.")

    adjacency = [set() for _polygon in mesh.polygons]
    for linked_faces in edge_faces:
        if len(linked_faces) == 2:
            first, second = linked_faces
            adjacency[first].add(second)
            adjacency[second].add(first)

    components = []
    visited = set()
    for polygon in mesh.polygons:
        if polygon.index in visited:
            continue
        component = set()
        stack = [polygon.index]
        visited.add(polygon.index)
        while stack:
            face_index = stack.pop()
            component.add(face_index)
            for neighbor in adjacency[face_index]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components, edge_faces


def _trace_boundary(mesh, component, edge_faces):
    boundary_edges = []
    component_set = set(component)
    for edge in mesh.edges:
        linked_count = sum(
            face_index in component_set for face_index in edge_faces[edge.index]
        )
        if linked_count == 1:
            boundary_edges.append(edge)

    if not boundary_edges:
        raise ValueError("A face island has no outer boundary.")

    vertex_edges = {}
    for edge in boundary_edges:
        for vertex_index in edge.vertices:
            vertex_edges.setdefault(vertex_index, []).append(edge.index)
    if any(len(edges) != 2 for edges in vertex_edges.values()):
        raise ValueError("A face island boundary is branched or open.")

    edge_by_index = {edge.index: edge for edge in boundary_edges}
    start_vertex = min(vertex_edges)
    contour_indices = [start_vertex]
    used_edges = set()
    current_vertex = start_vertex
    previous_edge = None

    while True:
        candidates = [
            edge_index
            for edge_index in vertex_edges[current_vertex]
            if edge_index != previous_edge
        ]
        next_edge_index = min(candidates)
        if next_edge_index in used_edges:
            if current_vertex == start_vertex:
                break
            raise ValueError("A face island boundary self-revisits before closing.")
        used_edges.add(next_edge_index)
        edge = edge_by_index[next_edge_index]
        first, second = edge.vertices
        next_vertex = second if first == current_vertex else first
        if next_vertex == start_vertex:
            break
        contour_indices.append(next_vertex)
        previous_edge = next_edge_index
        current_vertex = next_vertex

    if len(used_edges) != len(boundary_edges):
        raise ValueError(
            "Each face island must have exactly one outer boundary and no holes."
        )
    if len(contour_indices) < 3:
        raise ValueError("A face island boundary must contain at least three vertices.")
    return contour_indices


def _project_face_union(mesh, component, island_number):
    clipper = pyclipper.Pyclipper()
    for face_index in component:
        path = [
            (
                int(round(mesh.vertices[index].co.x * COORDINATE_SCALE)),
                int(round(mesh.vertices[index].co.y * COORDINATE_SCALE)),
            )
            for index in mesh.polygons[face_index].vertices
        ]
        if len(path) < 3 or abs(pyclipper.Area(path)) <= 0.5:
            raise ValueError(
                f"Face island {island_number} contains a degenerate projected face."
            )
        if not pyclipper.Orientation(path):
            path.reverse()
        clipper.AddPath(path, pyclipper.PT_SUBJECT, True)

    try:
        tree = clipper.Execute2(
            pyclipper.CT_UNION,
            pyclipper.PFT_NONZERO,
            pyclipper.PFT_NONZERO,
        )
    except pyclipper.ClipperException as error:
        raise ValueError(
            f"Face island {island_number} projection union failed: {error}"
        ) from error

    outer_nodes = [node for node in tree.Childs if not node.IsHole]
    if len(outer_nodes) != 1:
        raise ValueError(
            f"Face island {island_number} projects to {len(outer_nodes)} separate "
            "outer regions; exactly one is required."
        )
    outer = outer_nodes[0]
    contour = tuple(
        (x / COORDINATE_SCALE, y / COORDINATE_SCALE)
        for x, y in outer.Contour
    )
    if _signed_area(contour) > 0.0:
        contour = tuple(reversed(contour))
    return contour


def _signed_area(contour):
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(contour, contour[1:] + contour[:1], strict=True)
    )


def _orientation(first, second, third):
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _on_segment(first, point, second):
    return (
        min(first[0], second[0]) <= point[0] <= max(first[0], second[0])
        and min(first[1], second[1]) <= point[1] <= max(first[1], second[1])
    )


def _segments_intersect(first_a, first_b, second_a, second_b):
    orientations = (
        _orientation(first_a, first_b, second_a),
        _orientation(first_a, first_b, second_b),
        _orientation(second_a, second_b, first_a),
        _orientation(second_a, second_b, first_b),
    )
    if (
        orientations[0] * orientations[1] < 0.0
        and orientations[2] * orientations[3] < 0.0
    ):
        return True
    return any(
        orientation == 0 and _on_segment(start, point, end)
        for orientation, start, point, end in (
            (orientations[0], first_a, second_a, first_b),
            (orientations[1], first_a, second_b, first_b),
            (orientations[2], second_a, first_a, second_b),
            (orientations[3], second_a, first_b, second_b),
        )
    )


def _has_self_intersection(contour):
    count = len(contour)
    for first_index in range(count):
        first_next = (first_index + 1) % count
        for second_index in range(first_index + 1, count):
            second_next = (second_index + 1) % count
            if (
                first_index == second_index
                or first_next == second_index
                or second_next == first_index
            ):
                continue
            if _segments_intersect(
                contour[first_index],
                contour[first_next],
                contour[second_index],
                contour[second_next],
            ):
                return True
    return False


def validate_simple_contour(contour, description="Contour"):
    """Require one finite, non-degenerate, non-self-intersecting closed ring."""
    if len(contour) < 3:
        raise ValueError(f"{description} must contain at least three vertices.")
    if any(not math.isfinite(value) for point in contour for value in point):
        raise ValueError(f"{description} contains a non-finite coordinate.")

    integer_contour = tuple(
        (
            int(round(point[0] * COORDINATE_SCALE)),
            int(round(point[1] * COORDINATE_SCALE)),
        )
        for point in contour
    )
    for index, point in enumerate(integer_contour):
        next_point = integer_contour[(index + 1) % len(integer_contour)]
        if point == next_point:
            raise ValueError(f"{description} contains a zero-length edge.")

    for first_index, first in enumerate(integer_contour):
        for second_index in range(first_index + 1, len(integer_contour)):
            second = integer_contour[second_index]
            if first == second:
                raise ValueError(f"{description} contains a repeated vertex.")

    if _has_self_intersection(integer_contour):
        raise ValueError(f"{description} intersects itself.")
    if _signed_area(integer_contour) == 0.0:
        raise ValueError(f"{description} has zero signed area.")


def extract_islands(object_):
    validate_object(object_)
    mesh = object_.data
    components, edge_faces = _face_components(mesh)

    vertex_owner = {}
    islands = []
    for island_id, component in enumerate(components):
        face_indices = tuple(sorted(component))
        vertex_indices = tuple(
            sorted(
                {
                    vertex_index
                    for face_index in component
                    for vertex_index in mesh.polygons[face_index].vertices
                }
            )
        )
        for vertex_index in vertex_indices:
            if vertex_index in vertex_owner:
                raise ValueError(
                    "Face islands that touch only at a shared vertex are abnormal "
                    "topology and are not supported."
                )
            vertex_owner[vertex_index] = island_id

        try:
            _trace_boundary(mesh, component, edge_faces)
        except ValueError as error:
            raise ValueError(f"Face island {island_id + 1}: {error}") from error
        contour = _project_face_union(
            mesh,
            component,
            island_id + 1,
        )
        validate_simple_contour(
            contour,
            f"Face island {island_id + 1} outer boundary",
        )
        signed_area = _signed_area(contour)
        if signed_area > 0.0:
            contour = tuple(reversed(contour))
            signed_area = -signed_area

        xs = [point[0] for point in contour]
        ys = [point[1] for point in contour]
        islands.append(
            IslandGeometry(
                island_id=island_id,
                face_indices=face_indices,
                vertex_indices=vertex_indices,
                contour=contour,
                area=abs(signed_area),
                bounds=(min(xs), min(ys), max(xs), max(ys)),
            )
        )

    referenced_vertices = set(vertex_owner)
    if len(referenced_vertices) != len(mesh.vertices):
        raise ValueError("Loose vertices or edges are not supported.")
    return islands
