"""Island Tool Blender extension."""

import bpy

from .nesting_operator import OPERATOR_CLASSES as NESTING_OPERATOR_CLASSES
from .properties import ISLANDTOOL_PG_nesting_settings, PROPERTY_CLASSES
from .translations import TRANSLATIONS
from .ui import UI_CLASSES
from .uv_operator import ISLANDTOOL_OT_duplicate_island_from_uv


CLASSES = (
    *PROPERTY_CLASSES,
    *NESTING_OPERATOR_CLASSES,
    ISLANDTOOL_OT_duplicate_island_from_uv,
    *UI_CLASSES,
)


def _draw_uv_operator(self, _context):
    self.layout.operator(
        ISLANDTOOL_OT_duplicate_island_from_uv.bl_idname,
        icon="UV",
    )


def register():
    bpy.app.translations.register(__name__, TRANSLATIONS)
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.island_tool_nesting = bpy.props.PointerProperty(
        type=ISLANDTOOL_PG_nesting_settings,
    )
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.append(_draw_uv_operator)
    bpy.types.VIEW3D_MT_edit_mesh.append(_draw_uv_operator)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh.remove(_draw_uv_operator)
    bpy.types.VIEW3D_MT_edit_mesh_context_menu.remove(_draw_uv_operator)
    del bpy.types.Scene.island_tool_nesting
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    bpy.app.translations.unregister(__name__)
