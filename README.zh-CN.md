# Island Tool

[English](README.md)

Island Tool 是一个适用于 Blender 5.2、Windows x64 的扩展，整合了 UV 岛重建和网格孤岛板材嵌套功能。

## UV 岛复制

在网格编辑模式和顶点选择模式下，依次选择顶点 A、B。可从 **Island Tool** N 侧栏、网格右键菜单或 **Mesh** 菜单执行 **从 UV 复制孤岛**。

插件会复制由缝合边限定的孤岛，并根据活动 UV 将副本重建到局部 XY 平面。副本会保持原孤岛面积，并使 A 到 B 指向局部 `+Y`。成功后只选择新顶点；选择或 UV 数据不符合要求时不会修改网格。

## 板材嵌套

在对象模式下打开 N 侧栏中的 **Island Tool > 板材嵌套**。配置一种或多种板材尺寸和数量，再设置出血、轮廓输出和求解质量，然后执行 **嵌套网格孤岛**。

源对象需要是位于 XY 平面的网格，使用单位变换，不包含修改器或形态键，并具有有效的闭合面孤岛。插件会保留源对象，孤岛只进行平移；只有找到有效布局后才会创建输出。交互运行会显示进度，并支持按 `Esc` 取消。

## 构建

在仓库根目录使用 Windows x64 版 Blender 5.2 或更高版本：

```powershell
blender --command extension build `
  --source-dir addon\island_tool `
  --output-dir .

blender --command extension validate island_tool-1.1.0.zip
```

运行 UV 测试：

```powershell
blender --background --factory-startup --python tests\test_uv.py
```

嵌套测试要求 Blender 进程能够导入 `pyclipper`：

```powershell
$env:PYTHONPATH = ".test_deps"
blender --background --factory-startup --python tests\test_nesting.py
```
