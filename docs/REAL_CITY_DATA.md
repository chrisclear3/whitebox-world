# 真实城市：Rokehan 公共 OSM 数据包

默认交付场景是 `artifacts/shibuya.blend`，中心 **139.7005°E, 35.6595°N**，面积 **300 × 300 米**，与 Rokehan 的 Shibuya 初始地点一致。只使用其公开地图数据，不包含/复制其应用实现或资产。

## 离线打开 / 重建

打开 `artifacts/shibuya.blend` 即可编辑真实建筑、道路、行人和车辆。无插件也可播放已烘焙动画。地图数据原文也存放在 Blender Text 数据块 `WW_MapSource.geojson`，场景自定义属性记录来源和限制。

从已附数据重建，无需网络：

```sh
blender -b --python scripts/build_scene.py -- --config configs/shibuya.json --output artifacts/shibuya.blend --render --glb --poses
```

## 新增城市 / 更新数据

```sh
python scripts/fetch_rokehan.py --lat 35.6595 --lon 139.7005 --size 300 --output configs/my_city.geojson
blender -b --python scripts/build_scene.py -- --config configs/my_city.json --output artifacts/my_city.blend --render --glb --poses
```

下载器自动选择覆盖该范围的公开数据包，生成 `.geojson` 和同名 `.json` 配置。尺寸限制 50–600 米；经纬度可替换。临时目录缓存已下载的数据块；要重新拉取最新包，加 `--refresh`。数据包覆盖范围由在线 `packs/index.json` 决定，并不覆盖所有城市。没有覆盖、网络失败、空地图或没有适合的角色道路时会报错，不生成随机城市替代。若某地没有人行道或车行道，需要自行配置合法路径；下载器不会虚构这些道路。已有文件请先备份，成功输出会覆盖同名文件。

没有 Rokehan 数据包时可另用 `python scripts/fetch_osm.py --help`，从 Overpass 下载小范围 OSM XML，再配 `map_file`、`coordinate_system: "wgs84"` 和明确 origin 导入。该路线需要联网，公共服务可能限流。不要给普通 OSM XML 配置启用 `require_real_map`，该严格模式针对带完整来源记录的本适配器 GeoJSON。普通地图 UI 导入缺少可识别道路类型时，不会添加默认合成路径；可以自行添加路径/角色。

Blender UI 导入：Biome 选 City，Size 与下载尺寸一致，Map 选生成的 `.geojson`，Coordinates 选 Auto 或 Local。生成文件已经明确声明局部米制坐标，origin 保存原始经纬度。UI 会从实际映射的人行/车行中心线选择示意路线；CLI 使用配置内已记录的路线。

## 数据来源与授权

- 公共工具及地图数据说明：https://tools.oyasumi-gamedev.com/rokehan/
- 公共索引：https://tools.oyasumi-gamedev.com/rokehan/packs/index.json
- 地图：**© OpenStreetMap contributors**，https://www.openstreetmap.org/copyright
- 数据授权：**Open Database License (ODbL) 1.0**，https://opendatacommons.org/licenses/odbl/1-0/
- Tokyo 包元数据创建日期：2026-10-12。此日期不是所有 OSM 要素的最后编辑日期。

`configs/shibuya.geojson` 是上述 OSM 数据的裁剪/投影派生数据库，按 ODbL 1.0 提供，不在软件 MIT 授权内。分享派生数据库应保留 ODbL 与署名，遵守其相同方式共享条款；分享渲染图/模型等 produced works 应提供可见署名和数据来源。完整下载 URL、字节长度、SHA-256、包元数据和处理方法见 GeoJSON 的 provenance。构建产物保存署名；GLB 的 Ground 节点 extras 保存署名/许可/限制，建筑节点 extras 保存 OSM way ID 和高度来源。单独导出图片时，请同时附上这里的署名；图片本身不覆盖水印文字。

本数据只含地图事实。解码器和 Blender 构建器是此项目独立实现，没有移植 Rokehan JavaScript。

## 验证与准确度边界

- 105 个真实 OSM 建筑 way；243 个道路 way，边界裁剪后 244 条道路折线。
- 74 个建筑使用 OSM height 标签（不代表测绘验证）；17 个按楼层 × 3m 估计；14 个使用 9m 默认高度。
- 建筑仅保留完全落在范围内的闭合 way；跨边界建筑省略，不将切开的多边形伪装成完整建筑。
- 忽略 relation 建筑、内洞、屋顶细节和建筑部分的复杂合并。可能存在外形与部分重复；不是精确建筑复原。
- 道路按中心线条带显示，缺失宽度由 lanes 或 highway 类型估算；不是车道级地图。地下/高架道路省略，十字路口不做拓扑重建。
- **没有导入 DEM。地面完全平坦。** Tokyo 包索引的 DEM 列表为空；不能声称复原渋谷坡度或与网页地形相同。
- 行人沿实际 pedestrian 步行街，汽车沿实际车行 way 中心线示意移动。保留 one-way 方向，但不是日本靠左车道、信号灯、避障或交互交通模拟。起止点和路径均可编辑，默认不循环。
- 仅有局部投影与简化白模，不包含街景照片、建筑立面、原站远景/气氛渲染。

运行测试：

```sh
python -m unittest discover -s tests -v
blender -b --python tests/blender_integration.py
blender -b --python tests/blender_shibuya.py
```

最后一项读取并验证真实地图产物、检查严格模式不接受空地图/合成数据、检查人物运动与 GLB 署名和动画回读，并更新预览。
