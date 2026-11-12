# Island Tool

[简体中文](README.zh-CN.md)

Island Tool is a Blender 5.2 extension for Windows x64 that combines UV-island
reconstruction and planar mesh-island sheet nesting.

## UV Island Copy

In Mesh Edit Mode with Vertex Select enabled, select vertex A and then vertex B.
Run **Duplicate Island from UV** from the **Island Tool** N-sidebar tab, the mesh
context menu, or the **Mesh** menu.

The identified seam-bounded island is duplicated and rebuilt on the local XY
plane from its active UV map. The copy keeps the original island's area and is
oriented so A-to-B points along local `+Y`. On success, only the new vertices are
selected. Invalid selections or UV data leave the mesh unchanged.

## Sheet Nesting

In Object Mode, open **Island Tool > Sheet Nesting** in the N sidebar. Configure
one or more sheet sizes and quantities, then choose bleed, outline output, and
solver quality before running **Nest Mesh Islands**.

The source must be a planar XY mesh with an identity transform, no modifiers or
shape keys, and valid closed face islands. The source object is preserved.
Islands are placed by translation only, and output is created only when a valid
layout is found. Interactive runs show progress and can be cancelled with `Esc`.

## Build

From the repository root, using Blender 5.2 or newer on Windows x64:

```powershell
blender --command extension build `
  --source-dir addon\island_tool `
  --output-dir .

blender --command extension validate island_tool-1.1.0.zip
```

Run the UV tests:

```powershell
blender --background --factory-startup --python tests\test_uv.py
```

The nesting tests require `pyclipper` to be available to the Blender process:

```powershell
$env:PYTHONPATH = ".test_deps"
blender --background --factory-startup --python tests\test_nesting.py
```
