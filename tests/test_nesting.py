"""Blender integration tests for mesh island sheet nesting."""

import importlib
import math
import pathlib
import sys
from types import SimpleNamespace

import bpy
import numpy as np

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(PROJECT_ROOT / ".test_deps"),
    str(PROJECT_ROOT / "addon"),
]

addon = importlib.import_module("island_tool")
geometry = importlib.import_module("island_tool.geometry")
solver = importlib.import_module("island_tool.solver")


def reset_scene():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name.endswith("_Nested_Sheets"):
            bpy.data.collections.remove(collection)


def test_simplified_chinese_translation():
    preferences = bpy.context.preferences.view
    original_language = preferences.language
    original_translate = preferences.use_translate_interface
    try:
        preferences.language = "zh_HANS"
        preferences.use_translate_interface = True
        assert bpy.app.translations.pgettext_iface("Island Tool") == "孤岛工具"
        assert bpy.app.translations.pgettext_iface("Sheet Nesting") == "板材嵌套"
    finally:
        preferences.language = original_language
        preferences.use_translate_interface = original_translate


def create_mesh_object(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    object_ = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(object_)
    bpy.context.view_layer.objects.active = object_
    object_.select_set(True)
    return object_


def create_two_islands():
    return create_mesh_object(
        "TwoIslands",
        [
            (0.0, 0.0, 0.0),
            (0.3, 0.0, 0.0),
            (0.3, 0.2, 0.0),
            (0.0, 0.2, 0.0),
            (1.0, 0.0, 0.0),
            (1.3, 0.0, 0.0),
            (1.3, 0.2, 0.0),
            (1.0, 0.2, 0.0),
        ],
        [(0, 1, 2, 3), (4, 5, 6, 7)],
    )


def configure_single_sheet(width, height, count=1, bleed=0.0, quality="FAST"):
    settings = bpy.context.scene.island_tool_nesting
    settings.sheets.clear()
    sheet = settings.sheets.add()
    sheet.width = width
    sheet.height = height
    sheet.count = count
    settings.bleed = bleed
    settings.quality = quality


def source_coordinates(object_):
    return np.array([tuple(vertex.co) for vertex in object_.data.vertices])


def test_geometry_extracts_actual_boundaries():
    reset_scene()
    object_ = create_two_islands()
    islands = geometry.extract_islands(object_)
    assert len(islands) == 2
    assert all(len(island.contour) == 4 for island in islands)
    assert all(abs(island.area - 0.06) < 1.0e-8 for island in islands)


def test_hole_topology_is_rejected():
    reset_scene()
    object_ = create_mesh_object(
        "Ring",
        [
            (0, 0, 0),
            (2, 0, 0),
            (2, 2, 0),
            (0, 2, 0),
            (0.5, 0.5, 0),
            (1.5, 0.5, 0),
            (1.5, 1.5, 0),
            (0.5, 1.5, 0),
        ],
        [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)],
    )
    try:
        geometry.extract_islands(object_)
    except ValueError as error:
        assert "exactly one outer boundary" in str(error)
    else:
        raise AssertionError("A face island with a hole was accepted")


def test_solver_respects_finite_inventory_and_progress():
    reset_scene()
    islands = geometry.extract_islands(create_two_islands())
    progress = []
    layouts = solver.solve_nesting(
        islands,
        [solver.SheetSpec(0, 0.35, 0.25, 2)],
        bleed=0.01,
        quality="BALANCED",
        progress_callback=progress.append,
    )
    assert layouts is not None
    assert len(layouts) == 2
    assert sum(len(layout.placements) for layout in layouts) == 2
    assert progress


def test_all_quality_levels_find_the_basic_layout():
    reset_scene()
    islands = geometry.extract_islands(create_two_islands())
    for quality in ("FAST", "BALANCED", "HIGH"):
        layouts = solver.solve_nesting(
            islands,
            [solver.SheetSpec(0, 0.7, 0.3, 1)],
            bleed=0.01,
            quality=quality,
        )
        assert layouts is not None, quality
        assert len(layouts) == 1, quality


def test_large_sheet_fallback_places_many_concave_islands():
    contour = (
        (0.0, 0.0),
        (0.2, 0.0),
        (0.2, -0.1),
        (0.1, -0.1),
        (0.1, -0.2),
        (0.0, -0.2),
    )
    islands = [
        geometry.IslandGeometry(
            island_id=index,
            face_indices=(),
            vertex_indices=(),
            contour=contour,
            area=0.03,
            bounds=(0.0, -0.2, 0.2, 0.0),
        )
        for index in range(12)
    ]
    layouts = solver.solve_nesting(
        islands,
        [solver.SheetSpec(0, 10.0, 10.0, 1)],
        bleed=0.01,
        quality="FAST",
    )
    assert len(layouts) == 1
    assert len(layouts[0].placements) == 12


def test_solver_cancellation_creates_no_result():
    reset_scene()
    islands = geometry.extract_islands(create_two_islands())
    try:
        solver.solve_nesting(
            islands,
            [solver.SheetSpec(0, 1.0, 1.0, 1)],
            bleed=0.01,
            quality="HIGH",
            stop_callback=lambda: True,
        )
    except ValueError as error:
        assert "cancelled" in str(error).lower()
    else:
        raise AssertionError("A cancelled solve returned a layout")


def test_spatial_index_skips_distant_exact_collision_tests():
    prepared = SimpleNamespace(
        contour=((0, 0), (10, 0), (10, -10), (0, -10)),
    )
    placed_prepared = SimpleNamespace()
    placed = solver._PlacedPolygon(
        prepared=placed_prepared,
        dx=0,
        dy=0,
        contour=((0, 0), (10, 0), (10, -10), (0, -10)),
        bounds=(0, 0, 10, 10),
    )
    spatial_index = solver._SpatialIndex(20)
    spatial_index.add(placed)

    original_intersection = solver._intersection_has_area
    calls = []

    def record_intersection(first, second):
        calls.append((first, second))
        return original_intersection(first, second)

    solver._intersection_has_area = record_intersection
    try:
        contour = solver._translated_contour_if_placeable(
            prepared,
            100,
            100,
            (100, 100, 110, 110),
            spatial_index,
            200,
            200,
        )
    finally:
        solver._intersection_has_area = original_intersection

    assert contour is not None
    assert calls == []


def test_spatial_index_still_rejects_nearby_overlap():
    prepared = SimpleNamespace(
        contour=((0, 0), (10, 0), (10, 10), (0, 10)),
    )
    placed = solver._PlacedPolygon(
        prepared=SimpleNamespace(),
        dx=0,
        dy=0,
        contour=((0, 0), (10, 0), (10, 10), (0, 10)),
        bounds=(0, 0, 10, 10),
    )
    spatial_index = solver._SpatialIndex(20)
    spatial_index.add(placed)
    contour = solver._translated_contour_if_placeable(
        prepared,
        5,
        5,
        (5, 5, 15, 15),
        spatial_index,
        200,
        200,
    )
    assert contour is None


def test_different_sheet_sizes_share_finite_inventory():
    reset_scene()
    object_ = create_mesh_object(
        "DifferentSizes",
        [
            (0, 0, 0),
            (0.6, 0, 0),
            (0.6, 0.2, 0),
            (0, 0.2, 0),
            (1, 0, 0),
            (1.3, 0, 0),
            (1.3, 0.2, 0),
            (1, 0.2, 0),
        ],
        [(0, 1, 2, 3), (4, 5, 6, 7)],
    )
    islands = geometry.extract_islands(object_)
    layouts = solver.solve_nesting(
        islands,
        [
            solver.SheetSpec(0, 0.35, 0.25, 1),
            solver.SheetSpec(1, 0.65, 0.25, 1),
        ],
        bleed=0.01,
        quality="BALANCED",
    )
    assert layouts is not None
    assert len(layouts) == 2
    assert {layout.spec.spec_index for layout in layouts} == {0, 1}


def test_solver_never_rotates_to_make_an_item_fit():
    reset_scene()
    object_ = create_mesh_object(
        "NoRotation",
        [(0, 0, 0), (0.6, 0, 0), (0.6, 0.3, 0), (0, 0.3, 0)],
        [(0, 1, 2, 3)],
    )
    islands = geometry.extract_islands(object_)
    try:
        solver.solve_nesting(
            islands,
            [solver.SheetSpec(0, 0.4, 0.7, 1)],
            bleed=0.0,
            quality="HIGH",
        )
    except ValueError as error:
        assert "Island 1 needs at least 600.0 x 300.0 mm" in str(error)
    else:
        raise AssertionError("An island was rotated to fit")


def test_bleed_expands_each_island_and_sheet_boundary():
    reset_scene()
    islands = geometry.extract_islands(create_two_islands())
    without_bleed = solver.solve_nesting(
        islands,
        [solver.SheetSpec(0, 0.61, 0.21, 1)],
        bleed=0.0,
        quality="FAST",
    )
    assert without_bleed is not None
    try:
        solver.solve_nesting(
            islands,
            [solver.SheetSpec(0, 0.61, 0.21, 1)],
            bleed=0.01,
            quality="FAST",
        )
    except ValueError as error:
        assert "after bleed" in str(error)
    else:
        raise AssertionError("Bleed outside the sheet was accepted")


def test_round_bleed_contour_uses_configured_arc_step():
    contour = ((0.0, 0.0), (0.3, 0.0), (0.3, -0.2), (0.0, -0.2))
    ten_degrees = solver.create_round_bleed_contour(
        contour,
        0.01,
        math.radians(10.0),
    )
    twenty_degrees = solver.create_round_bleed_contour(
        contour,
        0.01,
        math.radians(20.0),
    )
    assert len(ten_degrees) == 40
    assert len(twenty_degrees) == 20
    assert min(x for x, _y in ten_degrees) == -0.01
    assert max(x for x, _y in ten_degrees) == 0.31
    assert min(y for _x, y in ten_degrees) == -0.21
    assert max(y for _x, y in ten_degrees) == 0.01


def test_concave_bleed_contours_are_simple():
    contours = (
        ((0, 0), (2, 0), (2, -1), (1, -1), (1, -2), (0, -2)),
        (
            (0, 0),
            (3, 0),
            (3, -3),
            (2, -3),
            (2, -0.3),
            (1, -0.3),
            (1, -3),
            (0, -3),
        ),
    )
    for contour in contours:
        for bleed in (0.05, 0.2, 0.6):
            result = solver.create_round_bleed_contour(
                contour,
                bleed,
                math.radians(10.0),
            )
            geometry.validate_simple_contour(
                result,
                "Test bleed contour",
            )


def test_simple_contour_validator_rejects_invalid_rings():
    invalid_contours = (
        ((0, 0), (1, 0), (1, 0), (0, 1)),
        ((0, 0), (2, 2), (0, 2), (2, 0)),
        ((0, 0), (1, 0), (0, 1), (1, 0)),
    )
    for contour in invalid_contours:
        try:
            geometry.validate_simple_contour(contour, "Invalid test contour")
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid contour was accepted: {contour}")


def test_quantization_cannot_create_a_degenerate_solver_contour():
    contour = (
        (0.0, 0.0),
        (0.0000001, 0.0),
        (1.0, 0.0),
        (0.0, -1.0),
    )
    try:
        solver.create_round_bleed_contour(
            contour,
            0.0,
            math.radians(10.0),
        )
    except ValueError as error:
        assert "zero-length edge" in str(error)
    else:
        raise AssertionError("A contour collapsed by quantization was accepted")


def test_success_preserves_source_and_creates_used_sheet_only():
    reset_scene()
    source = create_two_islands()
    before = source_coordinates(source)
    configure_single_sheet(0.7, 0.3, count=3, bleed=0.01)

    result = bpy.ops.island_tool.nest_mesh_islands_to_sheets("EXEC_DEFAULT")
    assert result == {"FINISHED"}, result
    assert np.array_equal(source_coordinates(source), before)

    outputs = [
        object_
        for object_ in bpy.data.objects
        if object_.name.startswith("TwoIslands_Sheet_")
    ]
    assert len(outputs) == 1
    output = outputs[0]
    assert math.isclose(output["sheet_width"], 0.7, abs_tol=1.0e-6)
    assert math.isclose(output["sheet_height"], 0.3, abs_tol=1.0e-6)
    assert output["island_count"] == 2
    assert len(output.data.polygons) == 2
    xs = [vertex.co.x for vertex in output.data.vertices]
    ys = [vertex.co.y for vertex in output.data.vertices]
    assert min(xs) >= 0.01 - 1.0e-6
    assert max(xs) <= 0.69 + 1.0e-6
    assert min(ys) >= 0.01 - 1.0e-6
    assert max(ys) <= 0.29 + 1.0e-6

    outlines = [
        object_
        for object_ in bpy.data.objects
        if object_.name.startswith("TwoIslands_Bleed_Outlines_")
    ]
    assert len(outlines) == 1
    outline = outlines[0]
    assert len(outline.data.polygons) == 0
    assert len(outline.data.vertices) == 80
    assert len(outline.data.edges) == 80
    assert math.isclose(
        outline["bleed_arc_step_radians"],
        math.radians(10.0),
        abs_tol=1.0e-6,
    )
    outline_xs = [vertex.co.x for vertex in outline.data.vertices]
    outline_ys = [vertex.co.y for vertex in outline.data.vertices]
    assert min(outline_xs) >= -1.0e-6
    assert max(outline_xs) <= 0.7 + 1.0e-6
    assert min(outline_ys) >= -1.0e-6
    assert max(outline_ys) <= 0.3 + 1.0e-6


def test_infeasible_layout_creates_nothing():
    reset_scene()
    source = create_two_islands()
    before = source_coordinates(source)
    configure_single_sheet(0.2, 0.1)
    object_count = len(bpy.data.objects)

    try:
        bpy.ops.island_tool.nest_mesh_islands_to_sheets("EXEC_DEFAULT")
    except RuntimeError as error:
        assert "Island 1 needs at least" in str(error)
    else:
        raise AssertionError("An infeasible nesting did not report an error")
    assert len(bpy.data.objects) == object_count
    assert np.array_equal(source_coordinates(source), before)


def test_transformed_object_creates_nothing():
    reset_scene()
    source = create_two_islands()
    source.location.x = 1.0
    configure_single_sheet(1.0, 1.0)
    object_count = len(bpy.data.objects)

    try:
        bpy.ops.island_tool.nest_mesh_islands_to_sheets("EXEC_DEFAULT")
    except RuntimeError as error:
        assert "world transform" in str(error)
    else:
        raise AssertionError("A transformed object was accepted")
    assert len(bpy.data.objects) == object_count


def main():
    addon.register()
    try:
        test_simplified_chinese_translation()
        settings_rna = addon.ISLANDTOOL_PG_nesting_settings.bl_rna.properties
        assert settings_rna["output_bleed_outlines"].default
        assert math.isclose(
            settings_rna["bleed_arc_step"].default,
            math.radians(10.0),
            abs_tol=1.0e-6,
        )
        test_geometry_extracts_actual_boundaries()
        test_hole_topology_is_rejected()
        test_solver_respects_finite_inventory_and_progress()
        test_all_quality_levels_find_the_basic_layout()
        test_large_sheet_fallback_places_many_concave_islands()
        test_solver_cancellation_creates_no_result()
        test_spatial_index_skips_distant_exact_collision_tests()
        test_spatial_index_still_rejects_nearby_overlap()
        test_different_sheet_sizes_share_finite_inventory()
        test_solver_never_rotates_to_make_an_item_fit()
        test_bleed_expands_each_island_and_sheet_boundary()
        test_round_bleed_contour_uses_configured_arc_step()
        test_concave_bleed_contours_are_simple()
        test_simple_contour_validator_rejects_invalid_rings()
        test_quantization_cannot_create_a_degenerate_solver_contour()
        test_success_preserves_source_and_creates_used_sheet_only()
        test_infeasible_layout_creates_nothing()
        test_transformed_object_creates_nothing()
    finally:
        reset_scene()
        addon.unregister()
    print("All Island Tool sheet nesting integration tests passed")


if __name__ == "__main__":
    main()
