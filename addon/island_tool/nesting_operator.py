"""Blender operators for sheet configuration and transactional nesting."""

import queue
import threading

import bmesh
import bpy

from .geometry import extract_islands
from .solver import SheetSpec, solve_nesting
from .translations import iface_, iface_format


class ISLANDTOOL_OT_sheet_add(bpy.types.Operator):
    bl_idname = "island_tool.sheet_add"
    bl_label = "Add Sheet Specification"
    bl_description = "Add a rectangular sheet size to the available inventory"

    def execute(self, context):
        settings = context.scene.island_tool_nesting
        sheet = settings.sheets.add()
        sheet.width = 1.0
        sheet.height = 0.9
        sheet.count = 1
        settings.active_sheet_index = len(settings.sheets) - 1
        return {"FINISHED"}


class ISLANDTOOL_OT_sheet_remove(bpy.types.Operator):
    bl_idname = "island_tool.sheet_remove"
    bl_label = "Remove Sheet Specification"
    bl_description = "Remove the active rectangular sheet size"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.island_tool_nesting.sheets)

    def execute(self, context):
        settings = context.scene.island_tool_nesting
        index = min(settings.active_sheet_index, len(settings.sheets) - 1)
        settings.sheets.remove(index)
        settings.active_sheet_index = max(
            0,
            min(index, len(settings.sheets) - 1),
        )
        return {"FINISHED"}


class ISLANDTOOL_OT_nest_mesh_islands(bpy.types.Operator):
    bl_idname = "island_tool.nest_mesh_islands_to_sheets"
    bl_label = "Nest Mesh Islands"
    bl_description = (
        "Pack all planar face islands onto the available rectangular sheets "
        "without rotation, scaling, or deformation"
    )
    bl_options = {"REGISTER", "UNDO"}
    _is_running = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH" or obj.mode != "OBJECT":
            cls.poll_message_set("An active mesh in Object Mode is required")
            return False
        if cls._is_running:
            cls.poll_message_set("A nesting task is already running")
            return False
        return True

    @staticmethod
    def _snapshot_inputs(context):
        settings = context.scene.island_tool_nesting
        source = context.active_object
        islands = extract_islands(source)
        sheet_specs = tuple(
            SheetSpec(
                spec_index=index,
                width=float(sheet.width),
                height=float(sheet.height),
                count=int(sheet.count),
            )
            for index, sheet in enumerate(settings.sheets)
        )
        return {
            "source": source,
            "islands": islands,
            "sheet_specs": sheet_specs,
            "bleed": float(settings.bleed),
            "bleed_arc_step": float(settings.bleed_arc_step),
            "quality": settings.quality,
            "output_bleed_outlines": bool(settings.output_bleed_outlines),
        }

    def execute(self, context):
        created_objects = []
        output_collection = None

        try:
            inputs = self._snapshot_inputs(context)
            layouts = solve_nesting(
                islands=inputs["islands"],
                sheet_specs=inputs["sheet_specs"],
                bleed=inputs["bleed"],
                bleed_arc_step=inputs["bleed_arc_step"],
                quality=inputs["quality"],
            )
            output_collection, created_objects = self._create_outputs(
                context,
                inputs["source"],
                inputs["islands"],
                layouts,
                inputs["bleed"],
                inputs["output_bleed_outlines"],
                inputs["bleed_arc_step"],
            )
        except (ImportError, RuntimeError, ValueError) as error:
            self._rollback(output_collection, created_objects)
            self.report({"ERROR"}, iface_(str(error)))
            return {"CANCELLED"}
        self._select_outputs(context, created_objects)
        self.report({"INFO"}, self._success_message(inputs["islands"], layouts))
        return {"FINISHED"}

    def invoke(self, context, _event):
        try:
            self._inputs = self._snapshot_inputs(context)
        except (ImportError, RuntimeError, ValueError) as error:
            self.report({"ERROR"}, iface_(str(error)))
            return {"CANCELLED"}

        self._messages = queue.SimpleQueue()
        self._cancel_event = threading.Event()
        self._timer = context.window_manager.event_timer_add(
            0.1,
            window=context.window,
        )
        self._best_completed = 0
        self._cancel_requested = False
        self._finished = False
        type(self)._is_running = True
        context.window_manager.progress_begin(0, 100)
        context.workspace.status_text_set(
            text=iface_("Nesting mesh islands... Esc to cancel")
        )

        inputs = self._inputs
        messages = self._messages
        cancel_event = self._cancel_event

        def progress_callback(remaining):
            messages.put(("progress", int(remaining)))

        def worker():
            try:
                layouts = solve_nesting(
                    islands=inputs["islands"],
                    sheet_specs=inputs["sheet_specs"],
                    bleed=inputs["bleed"],
                    bleed_arc_step=inputs["bleed_arc_step"],
                    quality=inputs["quality"],
                    progress_callback=progress_callback,
                    stop_callback=cancel_event.is_set,
                )
                messages.put(("result", layouts))
            except Exception as error:
                messages.put(("error", error))

        self._thread = threading.Thread(
            target=worker,
            name="MeshIslandSheetNesting",
            daemon=True,
        )
        self._thread.start()
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC" and event.value == "PRESS":
            self._cancel_requested = True
            self._cancel_event.set()
            context.workspace.status_text_set(
                text=iface_("Cancelling mesh island nesting...")
            )
            return {"RUNNING_MODAL"}

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        terminal_message = None
        while True:
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break
            if message[0] == "progress":
                self._update_modal_progress(context, message[1])
            else:
                terminal_message = message

        if terminal_message is None:
            return {"RUNNING_MODAL"}

        self._finish_modal(context)
        if terminal_message[0] == "error":
            error = terminal_message[1]
            if self._cancel_requested or "cancelled" in str(error).lower():
                self.report({"WARNING"}, iface_("Nesting cancelled; no objects were created."))
            else:
                self.report({"ERROR"}, iface_(str(error)))
            return {"CANCELLED"}

        if self._cancel_requested:
            self.report({"WARNING"}, iface_("Nesting cancelled; no objects were created."))
            return {"CANCELLED"}

        layouts = terminal_message[1]
        created_objects = []
        output_collection = None
        try:
            if self._inputs["source"].name not in context.scene.objects:
                raise RuntimeError(
                    "The source object was removed while nesting was running."
                )
            output_collection, created_objects = self._create_outputs(
                context,
                self._inputs["source"],
                self._inputs["islands"],
                layouts,
                self._inputs["bleed"],
                self._inputs["output_bleed_outlines"],
                self._inputs["bleed_arc_step"],
            )
        except Exception as error:
            self._rollback(output_collection, created_objects)
            self.report({"ERROR"}, iface_(str(error)))
            return {"CANCELLED"}

        self._select_outputs(context, created_objects)
        self.report(
            {"INFO"},
            self._success_message(self._inputs["islands"], layouts),
        )
        return {"FINISHED"}

    def cancel(self, context):
        if hasattr(self, "_cancel_event"):
            self._cancel_event.set()
        self._finish_modal(context)

    def _update_modal_progress(self, context, remaining):
        total = len(self._inputs["islands"])
        completed = total - min(total, remaining)
        self._best_completed = max(self._best_completed, completed)
        percentage = min(95, int(self._best_completed * 95 / total))
        context.window_manager.progress_update(percentage)
        context.workspace.status_text_set(
            text=(
                f"Nesting mesh islands: best {self._best_completed}/{total} "
                f"({percentage}%) - Esc to cancel"
            )
        )

    def _finish_modal(self, context):
        if getattr(self, "_finished", False):
            return
        self._finished = True
        type(self)._is_running = False
        timer = getattr(self, "_timer", None)
        if timer is not None:
            context.window_manager.event_timer_remove(timer)
            self._timer = None
        context.window_manager.progress_end()
        context.workspace.status_text_set(text=None)

    @staticmethod
    def _select_outputs(context, created_objects):
        for selected in context.selected_objects:
            selected.select_set(False)
        for object_ in created_objects:
            object_.select_set(True)
        if created_objects:
            context.view_layer.objects.active = created_objects[0]

    @staticmethod
    def _success_message(islands, layouts):
        return iface_format(
            "Nested {islands} islands onto {sheets} sheets.",
            islands=len(islands),
            sheets=len(layouts),
        )

    @staticmethod
    def _create_outputs(
        context,
        source,
        islands,
        layouts,
        bleed,
        output_bleed_outlines,
        bleed_arc_step,
    ):
        island_by_id = {island.island_id: island for island in islands}
        collection = bpy.data.collections.new(f"{source.name}_Nested_Sheets")
        context.scene.collection.children.link(collection)
        created = []

        try:
            for sheet_number, layout in enumerate(layouts, start=1):
                mesh = source.data.copy()
                mesh.name = f"{source.data.name}_Sheet_{sheet_number:03d}"
                object_ = bpy.data.objects.new(
                    f"{source.name}_Sheet_{sheet_number:03d}",
                    mesh,
                )
                collection.objects.link(object_)
                created.append(object_)

                bm = bmesh.new()
                try:
                    bm.from_mesh(mesh)
                    bm.verts.ensure_lookup_table()
                    kept_vertices = set()
                    for placement in layout.placements:
                        island = island_by_id[placement.island_id]
                        for vertex_index in island.vertex_indices:
                            vertex = bm.verts[vertex_index]
                            vertex.co.x += placement.offset_x
                            vertex.co.y += placement.offset_y
                            kept_vertices.add(vertex)

                    bmesh.ops.delete(
                        bm,
                        geom=[
                            vertex
                            for vertex in bm.verts
                            if vertex not in kept_vertices
                        ],
                        context="VERTS",
                    )
                    bm.to_mesh(mesh)
                    mesh.update()
                finally:
                    bm.free()

                object_["sheet_width"] = layout.spec.width
                object_["sheet_height"] = layout.spec.height
                object_["sheet_spec_index"] = layout.spec.spec_index
                object_["island_count"] = len(layout.placements)
                object_["bleed"] = bleed

                if output_bleed_outlines:
                    outline_object = (
                        ISLANDTOOL_OT_nest_mesh_islands._create_bleed_outline_object(
                            collection,
                            source,
                            layout,
                            sheet_number,
                            bleed,
                            bleed_arc_step,
                        )
                    )
                    created.append(outline_object)
        except Exception:
            ISLANDTOOL_OT_nest_mesh_islands._rollback(collection, created)
            raise
        return collection, created

    @staticmethod
    def _create_bleed_outline_object(
        collection,
        source,
        layout,
        sheet_number,
        bleed,
        bleed_arc_step,
    ):
        vertices = []
        edges = []
        for placement in layout.placements:
            start = len(vertices)
            vertices.extend(
                (x, y, 0.0) for x, y in placement.bleed_contour
            )
            count = len(placement.bleed_contour)
            edges.extend(
                (start + index, start + (index + 1) % count)
                for index in range(count)
            )

        mesh = bpy.data.meshes.new(
            f"{source.data.name}_Bleed_Outlines_{sheet_number:03d}"
        )
        mesh.from_pydata(vertices, edges, [])
        mesh.update()
        object_ = bpy.data.objects.new(
            f"{source.name}_Bleed_Outlines_{sheet_number:03d}",
            mesh,
        )
        collection.objects.link(object_)
        object_["sheet_width"] = layout.spec.width
        object_["sheet_height"] = layout.spec.height
        object_["sheet_spec_index"] = layout.spec.spec_index
        object_["island_count"] = len(layout.placements)
        object_["bleed"] = bleed
        object_["bleed_arc_step_radians"] = bleed_arc_step
        return object_

    @staticmethod
    def _rollback(collection, objects):
        for object_ in reversed(objects):
            mesh = object_.data
            bpy.data.objects.remove(object_, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        if collection is not None:
            bpy.data.collections.remove(collection)


OPERATOR_CLASSES = (
    ISLANDTOOL_OT_sheet_add,
    ISLANDTOOL_OT_sheet_remove,
    ISLANDTOOL_OT_nest_mesh_islands,
)
