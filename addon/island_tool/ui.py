"""3D View interfaces for Island Tool."""

import bpy


class ISLANDTOOL_UL_sheets(bpy.types.UIList):
    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_property,
        _index,
    ):
        row = layout.row(align=True)
        row.prop(item, "width", text="W")
        row.prop(item, "height", text="H")
        row.prop(item, "count", text="Count")


class VIEW3D_PT_island_tool_nesting(bpy.types.Panel):
    bl_label = "Sheet Nesting"
    bl_idname = "VIEW3D_PT_island_tool_nesting"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Island Tool"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.island_tool_nesting

        row = layout.row()
        row.template_list(
            "ISLANDTOOL_UL_sheets",
            "",
            settings,
            "sheets",
            settings,
            "active_sheet_index",
            rows=max(2, min(6, len(settings.sheets))),
        )
        controls = row.column(align=True)
        controls.operator("island_tool.sheet_add", text="", icon="ADD")
        controls.operator("island_tool.sheet_remove", text="", icon="REMOVE")

        layout.separator()
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(settings, "bleed")
        layout.prop(settings, "output_bleed_outlines")
        arc_row = layout.row()
        arc_row.active = settings.output_bleed_outlines or settings.bleed > 0.0
        arc_row.prop(settings, "bleed_arc_step")
        layout.prop(settings, "quality")

        action = layout.row()
        action.scale_y = 1.4
        action.operator(
            "island_tool.nest_mesh_islands_to_sheets",
            text="Nest Mesh Islands",
            icon="MOD_ARRAY",
        )


class VIEW3D_PT_island_tool_uv(bpy.types.Panel):
    bl_label = "UV Island"
    bl_idname = "VIEW3D_PT_island_tool_uv"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Island Tool"
    bl_context = "mesh_edit"

    def draw(self, _context):
        action = self.layout.row()
        action.scale_y = 1.4
        action.operator(
            "island_tool.duplicate_island_from_uv",
            text="Duplicate Island from UV",
            icon="UV",
        )


UI_CLASSES = (
    ISLANDTOOL_UL_sheets,
    VIEW3D_PT_island_tool_nesting,
    VIEW3D_PT_island_tool_uv,
)
