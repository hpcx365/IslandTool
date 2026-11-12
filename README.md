# Island Tool

Island Tool combines UV-island mesh reconstruction and planar mesh-island sheet
nesting in one Blender 5.2 extension for Windows x64.

## Install

Install `island_tool-1.1.0.zip` through **Edit > Preferences > Get Extensions >
Install from Disk**. Disable the standalone **UV Island To Mesh** and **Mesh
Island Sheet Nesting** extensions before enabling Island Tool.

## Languages

The extension includes English (`en_US`) and Simplified Chinese (`zh_HANS`). It
follows Blender's language and interface-translation settings automatically.

## UV Island Copy

In Edit Mode with Vertex Select enabled, select vertex A and then vertex B. Run
**Duplicate Island from UV** from the `Island Tool` N-sidebar tab, the mesh
right-click menu, or the 3D View **Mesh** menu.

The seam-bounded face island uniquely identified by A and B is duplicated. Its
active UVs become local XY coordinates, Z is set to zero, its area is scaled to
match the original 3D surface area, and A-to-B is rotated to local `+Y`. Only the
new vertices are selected on success. Validation failures leave the mesh
unchanged.

## Sheet Nesting

In Object Mode, open **Island Tool > Sheet Nesting** in the N sidebar. Configure
sheet sizes, quantities, bleed, outline output, and solver quality, then run
**Nest Mesh Islands**.

The source must be an identity-transformed planar XY mesh without modifiers or
shape keys. Nesting preserves the source and creates output objects only after a
complete layout succeeds. Placement uses translation only. The extension bundles
`pyclipper 1.4.0` and performs no runtime downloads.
