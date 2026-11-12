"""Persistent interactive settings for sheet nesting."""

import math

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
)


class ISLANDTOOL_PG_sheet_spec(bpy.types.PropertyGroup):
    width: FloatProperty(
        name="Width",
        subtype="DISTANCE",
        default=1.0,
        min=0.001,
        soft_max=10.0,
    )
    height: FloatProperty(
        name="Height",
        subtype="DISTANCE",
        default=0.9,
        min=0.001,
        soft_max=10.0,
    )
    count: IntProperty(
        name="Count",
        default=1,
        min=1,
        max=1000,
    )


class ISLANDTOOL_PG_nesting_settings(bpy.types.PropertyGroup):
    sheets: CollectionProperty(type=ISLANDTOOL_PG_sheet_spec)
    active_sheet_index: IntProperty(default=0, min=0)
    bleed: FloatProperty(
        name="Bleed",
        description="Distance each island outline expands in every direction",
        subtype="DISTANCE",
        default=0.005,
        min=0.0,
        soft_max=0.1,
    )
    output_bleed_outlines: BoolProperty(
        name="Output Bleed Outlines",
        description="Create an edge-only bleed contour object for every used sheet",
        default=True,
    )
    bleed_arc_step: FloatProperty(
        name="Bleed Arc Step",
        description="Maximum angle represented by each straight round-corner segment",
        subtype="ANGLE",
        unit="ROTATION",
        default=math.radians(10.0),
        min=math.radians(1.0),
        max=math.radians(45.0),
    )
    quality: EnumProperty(
        name="Quality",
        items=(
            ("FAST", "Fast", "Single-path NFP placement"),
            ("BALANCED", "Balanced", "Beam search across sheet choices"),
            ("HIGH", "High", "Wider search with the DJD nesting heuristic"),
        ),
        default="BALANCED",
    )


PROPERTY_CLASSES = (
    ISLANDTOOL_PG_sheet_spec,
    ISLANDTOOL_PG_nesting_settings,
)
