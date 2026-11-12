"""English and Simplified Chinese translations for Island Tool."""

import bpy


ZH_HANS = {
    "Island Tool": "孤岛工具",
    "Sheet Nesting": "板材嵌套",
    "UV Island": "UV 岛",
    "W": "宽",
    "H": "高",
    "Count": "数量",
    "Width": "宽度",
    "Height": "高度",
    "Bleed": "出血",
    "Output Bleed Outlines": "输出出血轮廓",
    "Bleed Arc Step": "出血圆弧步长",
    "Quality": "质量",
    "Fast": "快速",
    "Balanced": "平衡",
    "High": "高质量",
    "Add Sheet Specification": "添加板材规格",
    "Remove Sheet Specification": "移除板材规格",
    "Nest Mesh Islands": "嵌套网格孤岛",
    "Duplicate Island from UV": "从 UV 复制孤岛",
    "Add a rectangular sheet size to the available inventory": "向可用库存添加一种矩形板材尺寸",
    "Remove the active rectangular sheet size": "移除当前矩形板材尺寸",
    "Pack all planar face islands onto the available rectangular sheets without rotation, scaling, or deformation": "将所有平面面孤岛排入可用矩形板材，不旋转、不缩放、不变形",
    "Duplicate the seam-bounded face island identified by A then B, rebuild it on XY from UVs, preserve its surface area, and align A to B with +Y": "复制由 A、B 确定且以缝合边为边界的面孤岛，用 UV 在 XY 平面重建、保持面积，并使 A 到 B 朝向 +Y",
    "Distance each island outline expands in every direction": "每个孤岛轮廓向各方向扩展的距离",
    "Create an edge-only bleed contour object for every used sheet": "为每张已使用板材创建仅含边的出血轮廓对象",
    "Maximum angle represented by each straight round-corner segment": "圆角中每条直线段所表示的最大角度",
    "Single-path NFP placement": "单路径 NFP 放置",
    "Beam search across sheet choices": "跨板材选择的束搜索",
    "Wider search with the DJD nesting heuristic": "使用 DJD 嵌套启发式进行更宽搜索",
    "An active mesh in Edit Mode is required": "需要一个处于编辑模式的活动网格",
    "An active mesh object is required.": "需要一个活动网格对象。",
    "Switch the active mesh to Edit Mode first.": "请先将活动网格切换到编辑模式。",
    "Switch to Vertex Select mode before running this operator.": "运行此操作前请切换到顶点选择模式。",
    "The mesh has no active UV map.": "网格没有活动 UV 贴图。",
    "The identified island cannot be triangulated.": "无法对确定的孤岛进行三角化。",
    "The island has zero UV area and cannot be scaled.": "孤岛的 UV 面积为零，无法缩放。",
    "The original island has zero or invalid surface area.": "原孤岛的表面积为零或无效。",
    "The island has zero or invalid UV area.": "孤岛的 UV 面积为零或无效。",
    "The required area-preserving scale is not finite.": "保持面积所需的缩放值不是有限数。",
    "The calculated mesh coordinates are not finite.": "计算得到的网格坐标不是有限数。",
    "Select one active mesh object.": "请选择一个活动网格对象。",
    "Switch to Object Mode before nesting.": "嵌套前请切换到对象模式。",
    "Meshes with shape keys are not supported.": "不支持带形态键的网格。",
    "Apply or remove all modifiers before nesting.": "嵌套前请应用或移除所有修改器。",
    "The active mesh has no faces.": "活动网格没有面。",
    "Every mesh vertex must lie on the local XY plane (Z = 0).": "所有网格顶点必须位于局部 XY 平面上（Z = 0）。",
    "Loose edges are not supported.": "不支持游离边。",
    "Loose vertices or edges are not supported.": "不支持游离顶点或边。",
    "Non-manifold edges are not supported.": "不支持非流形边。",
    "A face island has no outer boundary.": "面孤岛没有外边界。",
    "A face island boundary is branched or open.": "面孤岛边界存在分支或开口。",
    "A face island boundary must contain at least three vertices.": "面孤岛边界必须至少包含三个顶点。",
    "Bleed cannot be negative.": "出血值不能为负。",
    "Bleed arc step must be between 0 and 180 degrees.": "出血圆弧步长必须在 0 到 180 度之间。",
    "The mesh has no face islands.": "网格没有面孤岛。",
    "No sheet inventory is configured. Add at least one sheet.": "尚未配置板材库存，请至少添加一张板材。",
    "Every sheet width and height must be positive.": "每张板材的宽度和高度必须为正数。",
    "Every sheet inventory count must be at least one.": "每种板材的库存数量必须至少为一。",
    "Nesting was cancelled; no objects were created.": "嵌套已取消，未创建任何对象。",
    "Nesting cancelled; no objects were created.": "嵌套已取消，未创建任何对象。",
    "Nesting mesh islands... Esc to cancel": "正在嵌套网格孤岛…按 Esc 取消",
    "Cancelling mesh island nesting...": "正在取消网格孤岛嵌套…",
    "Nested {islands} islands onto {sheets} sheets.": "已将 {islands} 个孤岛嵌套到 {sheets} 张板材。",
    "Created UV island copy: {faces} faces, {vertices} vertices, area scale {scale:.6g}.": "已创建 UV 岛副本：{faces} 个面、{vertices} 个顶点，面积缩放 {scale:.6g}。",
}


def _catalog(entries):
    contexts = ("*", "Operator")
    return {
        (context, source): translated
        for source, translated in entries.items()
        for context in contexts
    }


TRANSLATIONS = {
    "en_US": _catalog({source: source for source in ZH_HANS}),
    "zh_HANS": _catalog(ZH_HANS),
}


def iface_(message):
    return bpy.app.translations.pgettext_iface(message)


def iface_format(message, **values):
    return iface_(message).format(**values)
