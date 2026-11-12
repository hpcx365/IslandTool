"""Finite-stock polygon nesting using exact pyclipper collision tests."""

import math
from dataclasses import dataclass

import pyclipper

from .geometry import validate_simple_contour

COORDINATE_SCALE = 1_000_000
DEFAULT_BLEED_ARC_STEP = math.radians(10.0)


@dataclass(frozen=True)
class SheetSpec:
    spec_index: int
    width: float
    height: float
    count: int


@dataclass(frozen=True)
class Placement:
    island_id: int
    offset_x: float
    offset_y: float
    bleed_contour: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class SheetLayout:
    spec: SheetSpec
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class _State:
    remaining: tuple[int, ...]
    counts: tuple[int, ...]
    layouts: tuple[SheetLayout, ...]
    used_capacity: float


@dataclass(frozen=True)
class _PreparedIsland:
    island: object
    contour: tuple[tuple[int, int], ...]
    bounds: tuple[int, int, int, int]
    area: float


@dataclass(frozen=True)
class _PlacedPolygon:
    prepared: _PreparedIsland
    dx: int
    dy: int
    contour: tuple[tuple[int, int], ...]
    bounds: tuple[int, int, int, int]


class _SpatialIndex:
    def __init__(self, cell_size):
        self.cell_size = max(1, int(cell_size))
        self.items = []
        self.cells = {}

    def _cell_range(self, bounds):
        min_x, min_y, max_x, max_y = bounds
        first_x = min_x // self.cell_size
        first_y = min_y // self.cell_size
        last_x = max(first_x, (max_x - 1) // self.cell_size)
        last_y = max(first_y, (max_y - 1) // self.cell_size)
        for cell_x in range(first_x, last_x + 1):
            for cell_y in range(first_y, last_y + 1):
                yield cell_x, cell_y

    def add(self, item):
        item_index = len(self.items)
        self.items.append(item)
        for cell in self._cell_range(item.bounds):
            self.cells.setdefault(cell, set()).add(item_index)

    def query(self, bounds):
        indices = set()
        for cell in self._cell_range(bounds):
            indices.update(self.cells.get(cell, ()))
        return tuple(self.items[index] for index in sorted(indices))


QUALITY_CONFIG = {
    "FAST": (1, ("AREA",), 8, 800),
    "BALANCED": (6, ("AREA", "BOUND", "REVERSE"), 18, 4_000),
    "HIGH": (18, ("AREA", "BOUND", "REVERSE"), 40, 20_000),
}


def _coordinate(value):
    return int(round(value * COORDINATE_SCALE))


def _signed_area(contour):
    return 0.5 * sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(contour, contour[1:] + contour[:1], strict=True)
    )


def _bounds(contour):
    xs = [point[0] for point in contour]
    ys = [point[1] for point in contour]
    return min(xs), min(ys), max(xs), max(ys)


def _translate(contour, dx, dy):
    return tuple((x + dx, y + dy) for x, y in contour)


def create_round_bleed_contour(contour, bleed, arc_step):
    """Offset a clockwise contour with round joins approximated by line segments."""
    if bleed < 0.0:
        raise ValueError("Bleed cannot be negative.")
    if not 0.0 < arc_step <= math.pi:
        raise ValueError("Bleed arc step must be between 0 and 180 degrees.")

    integer_contour = [(_coordinate(x), _coordinate(y)) for x, y in contour]
    if bleed == 0.0:
        result = tuple(
            (x / COORDINATE_SCALE, y / COORDINATE_SCALE)
            for x, y in integer_contour
        )
        validate_simple_contour(result, "The quantized bleed contour")
        return result

    distance = _coordinate(bleed)
    arc_tolerance = max(
        0.25,
        distance * (1.0 - math.cos(arc_step * 0.5)),
    )
    offsetter = pyclipper.PyclipperOffset(2.0, arc_tolerance)
    offsetter.AddPath(
        integer_contour,
        pyclipper.JT_ROUND,
        pyclipper.ET_CLOSEDPOLYGON,
    )
    try:
        paths = offsetter.Execute(distance)
    except pyclipper.ClipperException as error:
        raise ValueError(f"Bleed offset failed: {error}") from error
    if len(paths) != 1 or len(paths[0]) < 3:
        raise ValueError(
            "A bleed offset did not produce exactly one valid outer contour."
        )
    result = tuple(
        (x / COORDINATE_SCALE, y / COORDINATE_SCALE) for x, y in paths[0]
    )
    if _signed_area(result) > 0.0:
        result = tuple(reversed(result))
    validate_simple_contour(result, "The generated bleed contour")
    return result


def _prepare_island(island, bleed, arc_step):
    bleed_contour = create_round_bleed_contour(
        island.contour,
        bleed,
        arc_step,
    )
    contour = tuple(
        (_coordinate(x), _coordinate(y)) for x, y in bleed_contour
    )
    return _PreparedIsland(
        island=island,
        contour=contour,
        bounds=_bounds(contour),
        area=abs(pyclipper.Area(contour)) / (COORDINATE_SCALE**2),
    )


def _ordered_islands(islands, mode):
    if mode == "AREA":
        return sorted(
            islands,
            key=lambda prepared: (-prepared.area, prepared.island.island_id),
        )
    if mode == "BOUND":
        return sorted(
            islands,
            key=lambda prepared: (
                -max(
                    prepared.bounds[2] - prepared.bounds[0],
                    prepared.bounds[3] - prepared.bounds[1],
                ),
                prepared.island.island_id,
            ),
        )
    return sorted(
        islands,
        key=lambda prepared: prepared.island.island_id,
        reverse=True,
    )


def _sample_vertices(contour, limit):
    if len(contour) <= limit:
        return contour
    step = len(contour) / limit
    return tuple(contour[int(index * step)] for index in range(limit))


def _bounds_overlap_area(first_bounds, second_bounds):
    if (
        first_bounds[2] <= second_bounds[0]
        or second_bounds[2] <= first_bounds[0]
        or first_bounds[3] <= second_bounds[1]
        or second_bounds[3] <= first_bounds[1]
    ):
        return False
    return True


def _intersection_has_area(first, second):
    clipper = pyclipper.Pyclipper()
    clipper.AddPath(first, pyclipper.PT_SUBJECT, True)
    clipper.AddPath(second, pyclipper.PT_CLIP, True)
    try:
        intersections = clipper.Execute(
            pyclipper.CT_INTERSECTION,
            pyclipper.PFT_NONZERO,
            pyclipper.PFT_NONZERO,
        )
    except pyclipper.ClipperException as error:
        raise ValueError(f"Polygon collision test failed: {error}") from error
    return any(abs(pyclipper.Area(path)) > 0.5 for path in intersections)


def _candidate_positions(prepared, placed, sheet_bounds, sample_limit, candidate_limit):
    min_x, min_y, max_x, max_y = prepared.bounds
    sheet_width, sheet_height = sheet_bounds
    x_values = {-min_x, sheet_width - max_x}
    y_values = {-min_y, sheet_height - max_y}

    for other in placed:
        other_min_x, other_min_y, other_max_x, other_max_y = other.bounds
        x_values.update(
            (
                other_min_x - max_x,
                other_max_x - min_x,
                other_min_x - min_x,
                other_max_x - max_x,
            )
        )
        y_values.update(
            (
                other_min_y - max_y,
                other_max_y - min_y,
                other_min_y - min_y,
                other_max_y - max_y,
            )
        )

    candidates = {(x, y) for x in x_values for y in y_values}
    candidate_vertices = _sample_vertices(prepared.contour, sample_limit)
    for other in placed:
        other_vertices = _sample_vertices(other.contour, sample_limit)
        candidates.update(
            (other_x - x, other_y - y)
            for x, y in candidate_vertices
            for other_x, other_y in other_vertices
        )

    def position_score(position):
        dx, dy = position
        translated_bounds = (
            min_x + dx,
            min_y + dy,
            max_x + dx,
            max_y + dy,
        )
        top = max(
            [translated_bounds[3], *(item.bounds[3] for item in placed)]
        )
        right = max(
            [translated_bounds[2], *(item.bounds[2] for item in placed)]
        )
        return top, right, translated_bounds[1], translated_bounds[0]

    return sorted(candidates, key=position_score)[:candidate_limit]


def _translated_contour_if_placeable(
    prepared,
    dx,
    dy,
    bounds,
    spatial_index,
    sheet_width,
    sheet_height,
):
    min_x, min_y, max_x, max_y = bounds
    if min_x < 0 or min_y < 0 or max_x > sheet_width or max_y > sheet_height:
        return None

    nearby = tuple(
        other
        for other in spatial_index.query(bounds)
        if _bounds_overlap_area(bounds, other.bounds)
    )
    if not nearby:
        return _translate(prepared.contour, dx, dy)

    contour = _translate(prepared.contour, dx, dy)
    if any(
        _intersection_has_area(contour, other.contour) for other in nearby
    ):
        return None
    return contour


def _spatial_cell_size(candidates):
    dimensions = sorted(
        max(
            prepared.bounds[2] - prepared.bounds[0],
            prepared.bounds[3] - prepared.bounds[1],
        )
        for prepared in candidates
    )
    return dimensions[len(dimensions) // 2]


def _shelf_pack(candidates, sheet_width, sheet_height):
    placed = []
    spatial_index = _SpatialIndex(_spatial_cell_size(candidates))
    cursor_x = 0
    cursor_y = 0
    row_height = 0
    for prepared in candidates:
        min_x, min_y, max_x, max_y = prepared.bounds
        width = max_x - min_x
        height = max_y - min_y
        if cursor_x + width > sheet_width:
            cursor_x = 0
            cursor_y += row_height
            row_height = 0
        if cursor_y + height > sheet_height:
            continue

        dx = cursor_x - min_x
        dy = cursor_y - min_y
        bounds = (
            cursor_x,
            cursor_y,
            cursor_x + width,
            cursor_y + height,
        )
        contour = _translated_contour_if_placeable(
            prepared,
            dx,
            dy,
            bounds,
            spatial_index,
            sheet_width,
            sheet_height,
        )
        if contour is not None:
            item = _PlacedPolygon(prepared, dx, dy, contour, bounds)
            placed.append(item)
            spatial_index.add(item)
            cursor_x += width
            row_height = max(row_height, height)
    return placed


def _placed_score(placed):
    if not placed:
        return (0, float("inf"), float("inf"))
    return (
        len(placed),
        -max(item.bounds[3] for item in placed),
        -max(item.bounds[2] for item in placed),
    )


def _to_placements(placed):
    return tuple(
        Placement(
            island_id=item.prepared.island.island_id,
            offset_x=item.dx / COORDINATE_SCALE,
            offset_y=item.dy / COORDINATE_SCALE,
            bleed_contour=tuple(
                (x / COORDINATE_SCALE, y / COORDINATE_SCALE)
                for x, y in item.contour
            ),
        )
        for item in placed
    )


def _pack_one_sheet(
    islands,
    sheet,
    quality,
    order_mode,
    progress_callback,
    stop_callback,
):
    sheet_width = _coordinate(sheet.width)
    sheet_height = _coordinate(sheet.height)
    candidates = [
        prepared
        for prepared in islands
        if prepared.bounds[2] - prepared.bounds[0] <= sheet_width
        and prepared.bounds[3] - prepared.bounds[1] <= sheet_height
    ]
    if not candidates:
        return ()

    _beam_width, _orders, sample_limit, candidate_limit = QUALITY_CONFIG[quality]
    ordered_candidates = _ordered_islands(candidates, order_mode)
    shelf_placed = _shelf_pack(
        ordered_candidates,
        sheet_width,
        sheet_height,
    )
    if len(shelf_placed) == len(ordered_candidates):
        progress_callback(0)
        return _to_placements(shelf_placed)

    placed = []
    spatial_index = _SpatialIndex(_spatial_cell_size(ordered_candidates))
    for prepared in ordered_candidates:
        if stop_callback():
            return ()
        positions = _candidate_positions(
            prepared,
            placed,
            (sheet_width, sheet_height),
            sample_limit,
            candidate_limit,
        )
        for position_index, (dx, dy) in enumerate(positions):
            if position_index % 32 == 0 and stop_callback():
                return ()
            bounds = (
                prepared.bounds[0] + dx,
                prepared.bounds[1] + dy,
                prepared.bounds[2] + dx,
                prepared.bounds[3] + dy,
            )
            contour = _translated_contour_if_placeable(
                prepared,
                dx,
                dy,
                bounds,
                spatial_index,
                sheet_width,
                sheet_height,
            )
            if contour is not None:
                item = _PlacedPolygon(prepared, dx, dy, contour, bounds)
                placed.append(item)
                spatial_index.add(item)
                progress_callback(len(candidates) - len(placed))
                break

    if _placed_score(shelf_placed) > _placed_score(placed):
        placed = shelf_placed
    return _to_placements(placed)


def _state_score(state, island_by_id):
    remaining_area = sum(island_by_id[index].area for index in state.remaining)
    return (
        remaining_area,
        len(state.remaining),
        state.used_capacity,
        len(state.layouts),
    )


def _format_size(width, height):
    return f"{width * 1000.0:.1f} x {height * 1000.0:.1f} mm"


def solve_nesting(
    islands,
    sheet_specs,
    bleed,
    bleed_arc_step=DEFAULT_BLEED_ARC_STEP,
    quality="BALANCED",
    progress_callback=lambda _remaining: None,
    stop_callback=lambda: False,
):
    if quality not in QUALITY_CONFIG:
        raise ValueError(f"Unknown quality level: {quality}")
    if not islands:
        raise ValueError("The mesh has no face islands.")
    if not sheet_specs:
        raise ValueError("No sheet inventory is configured. Add at least one sheet.")
    if bleed < 0.0:
        raise ValueError("Bleed cannot be negative.")
    if not 0.0 < bleed_arc_step <= math.pi:
        raise ValueError("Bleed arc step must be between 0 and 180 degrees.")
    if any(spec.width <= 0.0 or spec.height <= 0.0 for spec in sheet_specs):
        raise ValueError("Every sheet width and height must be positive.")
    if any(spec.count < 1 for spec in sheet_specs):
        raise ValueError("Every sheet inventory count must be at least one.")

    island_by_id = {island.island_id: island for island in islands}
    prepared_by_id = {
        island.island_id: _prepare_island(island, bleed, bleed_arc_step)
        for island in islands
    }

    for island_id, prepared in prepared_by_id.items():
        width = (prepared.bounds[2] - prepared.bounds[0]) / COORDINATE_SCALE
        height = (prepared.bounds[3] - prepared.bounds[1]) / COORDINATE_SCALE
        if not any(
            width <= spec.width and height <= spec.height for spec in sheet_specs
        ):
            available = ", ".join(
                f"{_format_size(spec.width, spec.height)} x {spec.count}"
                for spec in sheet_specs
            )
            raise ValueError(
                f"Island {island_id + 1} needs at least "
                f"{_format_size(width, height)} after bleed, but no configured "
                f"sheet can contain it. Available: {available}."
            )

    required_area = sum(item.area for item in prepared_by_id.values())
    available_area = sum(
        spec.width * spec.height * spec.count for spec in sheet_specs
    )
    if required_area > available_area + 1.0e-12:
        raise ValueError(
            f"Total bleed area is {required_area:.4f} m2, but sheet inventory "
            f"provides only {available_area:.4f} m2."
        )

    counts = tuple(spec.count for spec in sheet_specs)
    frontier = [
        _State(
            remaining=tuple(sorted(island_by_id)),
            counts=counts,
            layouts=(),
            used_capacity=0.0,
        )
    ]
    completed = []
    beam_width, order_modes, _sample_limit, _candidate_limit = QUALITY_CONFIG[quality]
    best_remaining = len(islands)

    while frontier:
        next_states = {}
        for state in frontier:
            if stop_callback():
                raise ValueError("Nesting was cancelled; no objects were created.")
            remaining_islands = [
                prepared_by_id[index] for index in state.remaining
            ]
            for spec_index, spec in enumerate(sheet_specs):
                if state.counts[spec_index] <= 0:
                    continue
                for order_mode in order_modes:
                    placements = _pack_one_sheet(
                        remaining_islands,
                        spec,
                        quality,
                        order_mode,
                        progress_callback,
                        stop_callback,
                    )
                    if not placements:
                        continue
                    placed_ids = {placement.island_id for placement in placements}
                    remaining = tuple(
                        index for index in state.remaining if index not in placed_ids
                    )
                    best_remaining = min(best_remaining, len(remaining))
                    progress_callback(len(remaining))
                    new_counts = list(state.counts)
                    new_counts[spec_index] -= 1
                    new_state = _State(
                        remaining=remaining,
                        counts=tuple(new_counts),
                        layouts=state.layouts
                        + (SheetLayout(spec=spec, placements=placements),),
                        used_capacity=state.used_capacity + spec.width * spec.height,
                    )
                    if not remaining:
                        completed.append(new_state)
                        continue
                    key = (remaining, tuple(new_counts))
                    current = next_states.get(key)
                    if current is None or _state_score(
                        new_state, island_by_id
                    ) < _state_score(current, island_by_id):
                        next_states[key] = new_state

        frontier = sorted(
            next_states.values(),
            key=lambda state: _state_score(state, island_by_id),
        )[:beam_width]

    if not completed:
        placed_count = len(islands) - best_remaining
        raise ValueError(
            f"The {quality.lower()} search placed at most {placed_count} of "
            f"{len(islands)} islands with the current finite inventory. "
            "Try High quality, add sheets, enlarge a sheet, or reduce bleed. "
            "No objects were created."
        )
    return min(
        completed,
        key=lambda state: (state.used_capacity, len(state.layouts)),
    ).layouts
