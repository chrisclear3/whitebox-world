# 可编辑街景细节与镜头距离 LOD · v0.3

新增的是 Blender 原生网格，不是贴图烘焙，也没有复制 Rokehan 源码。

新增大型 `.blend` / `.glb` 通过完整交付包提供；GitHub 更新包含源码、插件与预览。以下模型路径是完整交付包/本地生成的路径。

## 打开与控制

安装 `artifacts/whitebox_world_addon.zip`，打开完整交付包中的 `artifacts/shibuya_details.blend`，在 N 面板 → Whitebox → Editable scene layers 控制：

- Facades：窗玻璃、凸起窗框/窗台/中挺、部分阳台与栏杆、临街底商及雨棚
- Trees：独立树木层，不影响草丛和岩石
- Road markings：车行道路中心虚线
- Utility poles：电杆与横担、近景绝缘子
- Traffic lights：信号杆/机箱、近景三色灯片

每层独立控制视口、渲染及 GLB 导出。展开对应 `WW_` 集合，可编辑真实顶点、材质与父子层级。窗户按每栋楼的语义部分合并，避免每个窗格一个对象。重复树木、电杆使用共享网格；若只改一个实例，在 Blender 中 Object → Relations → Make Single User → Object & Data。

## 近细远简

- Camera distance：根据当前场景活动相机到每栋楼世界空间包围盒的距离，控制附加细节。
- All detail：显示所有启用层的细节。
- Coarse only：保留建筑体块与树木/电杆/信号杆轮廓，隐藏立面细节、灯片、绝缘子、道路画线。
- Freeze Current Detail：固定当前选择，不再跟随相机。重新选 Camera distance 恢复实时切换。

Near distance 单位米；默认 85m。移动活动相机、切换帧、渲染前都会刷新。这里使用场景相机，不是自由视口观察位置。距离阈值是硬切换，无渐隐。

细节只改变生成的 LOD 子集合可见性，不重建或删除网格，保留手动顶点编辑、材质、单个对象隐藏及父子变换。建筑本体移动时，附属窗框等一起移动。保存 `.blend` 会保存当前集合状态；没有插件仍可编辑网格、播放已烘焙角色动画，但没有实时相机距离刷新。全量 Generate / Replace 会替换整个 `WW_` 空间，手动编辑前请另存副本。

## 导出

GLB detail 有三种模式：

- Freeze current：在导出帧固定当前细节状态，再烘焙全部角色动画。
- All detail：导出所有已启用层的细节。
- Coarse only：导出简化几何。

关闭的功能层和手动隐藏渲染的对象不会被导出。导出结束恢复场景的 LOD 模式、帧和选择。GLB 不保留 Blender 集合开关或动态相机 LOD；需要这些交互请用 `.blend` 加插件。GLB 的 near/far 是导出时的固定选择，并不是运行时 LOD 扩展。

## 地图准确性和范围

渋谷建筑轮廓、道路与 OSM ID 保留原来的真实数据。立面布局是确定性程序生成，不是实景测绘；缺失用途标签时，住宅/商业细节风格为示意。支持从 GeoJSON Point/MultiPoint 与 OSM node 中读取 natural=tree、power=pole/tower、highway=traffic_signals，并保留 source ID/tags。源点与建筑/道路冲突会跳过并计数，不偷偷改坐标。

当前内置渋谷数据包没有这些设施源点，所以新增街树、电杆和信号灯均为明确标记的程序化摆放。道路边缘、建筑轮廓与设施间距参与碰撞筛选；无法代替道路工程测量。查看 Scene 的 `ww_street_details` 可见来源数量、跳过数量和限制；对象保存 `ww_placement` 及来源道路 ID。

尚未实现：精确建筑材质/招牌、室内、复杂屋顶/DEM、真实街道设施全量复原、电线网络、路口交通相位/车辆遵守信号、完整路口渠化/人行横道、连续渐变 LOD、视锥遮挡剔除、自动动态卸载远处网格。现有行人/车辆仍是独立路径动画，不含人车避障。远景隐藏细节会减少实际绘制，但完整可编辑网格仍保留在内存。

## 配置

配置支持 `show_facades` / `show_trees` / `show_road_markings` / `show_utility_poles` / `show_traffic_lights`（布尔），`lod_mode`（AUTO / ALL / COARSE / FROZEN），`lod_distance`（米），`export_detail`（CURRENT / ALL / COARSE）。

`street_details` 可选设置包括 tree_spacing、pole_spacing、max_trees、max_poles、max_traffic_lights、max_markings、enabled。这些是生成布局的参数；仅调整显示开关无需重生成。

建筑最多每层边 16 个窗单元、最多 18 个分层，保持大型白模可用。适合街区规模；不是无限流式城市。
