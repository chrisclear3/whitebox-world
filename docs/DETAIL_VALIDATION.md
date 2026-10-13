# v0.3 验证记录

环境：Blender 4.3.2 / Python 3。代码和素材独立实现；OSM 数据仍适用 ODbL。

## 自动化检查

- 73 个 Python 单元测试通过：原有配置/运动/地图/数据下载逻辑，新增立面碰撞与高度边界、语义用途标签、设施源点投影与来源保留、道路设施布局、路口角度/去重/桥隧分层过滤。
- `tests/blender_integration.py` 通过：五类环境、独立速度、相机不影响动画时钟、路径编辑、烘焙后改速、四种天气、用户对象保留、插件注册/注销、GLB 真实回读和 poses。
- `tests/blender_street_details.py` 通过：原生街道网格和父子组件。
- `tests/blender_details.py` 使用隔离用户目录安装实际 ZIP，而非直接从源码 import；覆盖即时 UI 开关、五层独立视口/渲染/GLB 排除、近远距离、ALL/COARSE/FROZEN、保存重开后的自定义顶点/隐藏状态、角色/相机独立性、GLB 节点与动画实际回读、渋谷来源。

小型测试场景：全细节导出 45 个 mesh nodes，简化导出 30 个。最终渋谷测试导出 1,298 个 mesh nodes（包括道路、演员和设施）。

## 实际渋谷生成

- 105 栋原有 OSM 建筑体块，来源 ID 保留
- 334 个立面语义对象，674,064 顶点 / 505,548 quad faces；含 34 组阳台、94 组底商
- 112 棵街树、73 个中心虚线单元（按道路合并）、15 个电杆、39 个信号灯
- 这些设施源点数据当前为 0，全部明确标注程序化摆放
- 立面网格独立 smoke 检查：Blender mesh.validate 无错误、面面积为正、顶点高度不超过建筑基底/屋顶，移动建筑时子对象随动

远处细节通过集合隐藏而非删除。因此切换视口/渲染可减少绘制负担，但完整可编辑数据仍在内存。

## 运行

在项目根目录先执行 `python scripts/package_addon.py`，然后：

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
blender -b --python-exit-code 1 --python tests/blender_integration.py
blender -b --python-exit-code 1 --python tests/blender_street_details.py
BLENDER_USER_SCRIPTS="$PWD/artifacts/integration/details/user_scripts" \
BLENDER_USER_CONFIG="$PWD/artifacts/integration/details/user_config" \
blender -b --factory-startup --python-exit-code 1 --python tests/blender_details.py
```

测试产物在 `artifacts/integration/`，不混入正式交付。已验证 4.3.2；没有宣称其他 Blender 版本均经过测试。
