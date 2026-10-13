"""Installed-add-on integration test. Never overwrites published scene artifacts.

Run from the project root after scripts/package_addon.py:
  BLENDER_USER_SCRIPTS="$PWD/artifacts/integration/details/user_scripts" \
  BLENDER_USER_CONFIG="$PWD/artifacts/integration/details/user_config" \
  blender -b --factory-startup --python-exit-code 1 --python tests/blender_details.py
"""
import json
import os
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/integration/details'
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'results.json').unlink(missing_ok=True)
ZIP = ROOT / 'artifacts/whitebox_world_addon.zip'
assert ZIP.is_file(), 'Run python scripts/package_addon.py first'
# Do not silently test source imports instead of the distributed ZIP.
sys.path[:] = [p for p in sys.path if p and Path(p).resolve() != ROOT]
assert 'whitebox_world' not in sys.modules
assert bpy.ops.preferences.addon_install(filepath=str(ZIP), overwrite=True) == {'FINISHED'}
assert bpy.ops.preferences.addon_enable(module='whitebox_world') == {'FINISHED'}
import whitebox_world
assert ROOT / 'whitebox_world' not in Path(whitebox_world.__file__).resolve().parents
from whitebox_world.scene import build
from whitebox_world.detail_runtime import FEATURES, update_details, object_render_visible
from whitebox_world.export import export_glb
from whitebox_world.runtime import update_actors


def refresh(scene):
    bpy.context.view_layer.update()
    update_details(scene)
    bpy.context.view_layer.update()


def mesh_names(path):
    raw = Path(path).read_bytes()
    assert raw[:4] == b'glTF'
    size, kind = struct.unpack_from('<II', raw, 12)
    assert kind == 0x4e4f534a
    data = json.loads(raw[20:20 + size])
    return {n['name'] for n in data['nodes'] if 'mesh' in n}, data


def export(scene, name):
    path = OUT / (name + '.glb')
    mode, frame = scene['ww_lod_mode'], scene.frame_current
    export_glb(str(path), scene)
    assert scene['ww_lod_mode'] == mode and scene.frame_current == frame
    return mesh_names(path)


def check_road_heights():
    roads = list(bpy.data.collections['WW_Roads'].objects)
    tops = [max((o.matrix_world @ v.co).z for v in o.data.vertices) for o in roads]
    assert len(tops) >= 2
    assert all(top < .09 for top in tops), 'Road surfaces must remain below paint'
    assert len(set(tops)) == len(tops), 'Coplanar road surfaces cause z-fighting'


def lod_state():
    return {c.name: (c.hide_viewport, c.hide_render) for c in bpy.data.collections if c.get('ww_lod')}


scene = build({'biome': 'city', 'size': 80, 'seed': 42, 'duration': 1, 'fps': 4,
               'lod_mode': 'ALL', 'actors': [
                   {'name': 'DetailTestWalker', 'kind': 'person', 'speed': 2,
                    'loop': False, 'path': [[-30, -8, 0], [30, -8, 0]]}]})
refresh(scene)
check_road_heights()
features = {key: {o.name for o in scene.objects if o.type == 'MESH' and o.get('ww_feature') == key}
            for key in FEATURES}
for key, names in features.items():
    assert names, 'Expected nonempty native geometry: ' + key
    assert all(len(bpy.data.objects[n].data.vertices) > 0 for n in names)
    assert all(object_render_visible(bpy.data.objects[n], scene) for n in names)
all_names, gltf = export(scene, 'all')
for names in features.values():
    assert names <= all_names, names - all_names
assert gltf.get('animations'), 'Actual actor animation must be exported'

# Each UI layer is independently hidden in viewport/render AND absent in GLB.
for key, label in FEATURES.items():
    setattr(scene, 'ww_show_' + key + '_ui', False)
    col = bpy.data.collections['WW_' + label]
    assert col.hide_viewport and col.hide_render, 'UI setter must update immediately'
    refresh(scene)
    assert all(not object_render_visible(bpy.data.objects[n], scene) for n in features[key])
    assert all(not bpy.data.objects[n].visible_get() for n in features[key])
    for other in FEATURES:
        if other != key:
            assert not bpy.data.collections['WW_' + FEATURES[other]].hide_render
    visible, _ = export(scene, 'without_' + key)
    assert not (features[key] & visible), (key, features[key] & visible)
    for other in FEATURES:
        if other != key:
            assert features[other] <= visible, (key, other, features[other] - visible)
    setattr(scene, 'ww_show_' + key + '_ui', True)
    assert not col.hide_viewport and not col.hide_render
    refresh(scene)

# Native vertex editing survives every visibility mode. No regeneration allowed.
facade = bpy.data.objects[sorted(features['facades'])[0]]
assert facade.get('ww_detail')
facade.data = facade.data.copy()  # Standard Blender single-user edit, if linked.
facade.data.vertices[0].co.x += .371
edited_name = facade.name
edited_vertex = tuple(facade.data.vertices[0].co)
facade['test_artist_edit'] = 'must survive detail changes and reopen'
artist_hidden = bpy.data.objects[sorted(features['trees'])[0]]
artist_hidden.hide_render = True
artist_hidden.hide_set(True)
hidden_name = artist_hidden.name
actor = bpy.data.objects['DetailTestWalker']
scene.frame_set(3)
actor_pose = actor.matrix_world.copy()
original_camera = scene.camera
original_camera_pose = original_camera.matrix_world.copy()

anchor = facade.parent or bpy.data.objects.get(facade.get('ww_lod_parent', ''))
assert anchor is not None
center = sum((anchor.matrix_world @ Vector(c) for c in anchor.bound_box), Vector()) / 8
near_data = bpy.data.cameras.new('TestNearCamera')
near = bpy.data.objects.new('TestNearCamera', near_data)
scene.collection.objects.link(near)
near.location = center
far_data = bpy.data.cameras.new('TestFarCamera')
far = bpy.data.objects.new('TestFarCamera', far_data)
scene.collection.objects.link(far)
far.location = (10000, 10000, 10000)
scene.camera = near
near.location = center + Vector((100, 100, 100))
bpy.context.view_layer.update()
scene.ww_detail_mode_ui = 'AUTO'
scene.ww_lod_distance_ui = 1
assert not object_render_visible(facade, scene), 'Small distance UI setter must hide immediately'
scene.ww_lod_distance_ui = 1000
assert object_render_visible(facade, scene), 'Large distance UI setter must show immediately'
scene.ww_lod_distance_ui = 30
near.location = center
refresh(scene)
assert object_render_visible(facade, scene), 'Near active camera must enable detail'
near_state = lod_state()
scene.camera = far
refresh(scene)
assert not object_render_visible(facade, scene), 'Far active camera must hide detail'
assert all(v == (True, True) for v in lod_state().values())
assert actor.matrix_world == actor_pose
assert original_camera.matrix_world == original_camera_pose
scene.camera = near
refresh(scene)
assert lod_state() == near_state
bpy.ops.whitebox.detail_freeze()
frozen = lod_state()
scene.camera = far
scene.frame_set(4)
refresh(scene)
assert scene['ww_lod_mode'] == 'FROZEN' and lod_state() == frozen
assert tuple(facade.data.vertices[0].co) == edited_vertex

# Save/open in the same installed-addon process exercises persistent handlers.
blend = OUT / 'edited_frozen.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
assert scene['ww_lod_mode'] == 'FROZEN' and lod_state() == frozen
facade = bpy.data.objects[edited_name]
assert tuple(facade.data.vertices[0].co) == edited_vertex
assert facade['test_artist_edit'].startswith('must survive')
assert bpy.data.objects[hidden_name].hide_render and bpy.data.objects[hidden_name].hide_get()
for handler in ('load_post', 'frame_change_post', 'depsgraph_update_post', 'render_pre'):
    assert any(getattr(f, '__module__', '') == 'whitebox_world.detail_runtime'
               for f in getattr(bpy.app.handlers, handler)), handler
scene.ww_detail_mode_ui = 'ALL'
assert all(v == (False, False) for v in lod_state().values()), 'ALL UI setter must update immediately'
refresh(scene)
assert bpy.data.objects[hidden_name].hide_render and bpy.data.objects[hidden_name].hide_get()
scene.ww_detail_mode_ui = 'COARSE'
assert all(v == (True, True) for v in lod_state().values()), 'COARSE UI setter must update immediately'
refresh(scene)
coarse, _ = export(scene, 'coarse')
assert not (features['facades'] & coarse)
assert not (features['road_markings'] & coarse)
assert features['trees'] - {hidden_name} <= coarse
assert hidden_name not in coarse
scene['ww_export_detail'] = 'ALL'
forced_all, _ = export(scene, 'forced_all')
assert features['facades'] <= forced_all
assert hidden_name not in forced_all
assert scene['ww_lod_mode'] == 'COARSE'
scene['ww_lod_mode'] = 'ALL'
scene['ww_export_detail'] = 'COARSE'
forced_coarse, _ = export(scene, 'forced_coarse')
assert forced_coarse == coarse
assert scene['ww_lod_mode'] == 'ALL'
assert tuple(facade.data.vertices[0].co) == edited_vertex

# Build the actual mapped district without touching its published artifacts.
config = json.loads((ROOT / 'configs/shibuya.json').read_text())
config.update(map_file=str(ROOT / 'configs/shibuya.geojson'), duration=1, fps=4, lod_mode='ALL')
scene = build(config)
refresh(scene)
check_road_heights()
assert len(bpy.data.collections['WW_Buildings'].objects) == 105
assert all(o.get('osm_id') for o in bpy.data.collections['WW_Buildings'].objects)
assert 'OpenStreetMap' in scene['ww_map_attribution']
assert bpy.data.texts.get('WW_MapSource.geojson')
assert all(any(o.get('ww_feature') == key for o in scene.objects) for key in FEATURES)
assert any(o.get('ww_placement') == 'procedural' for o in scene.objects)
shibuya, mapped_gltf = export(scene, 'shibuya_all')
assert any('OpenStreetMap' in n.get('extras', {}).get('map_attribution', '')
           for n in mapped_gltf['nodes'])
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'shibuya_details.blend'))

# Independent glTF import checks real mesh nodes and actor animation, not file size.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(OUT / 'forced_all.glb'))
assert bpy.data.objects.get(edited_name) and bpy.data.objects[edited_name].type == 'MESH'
assert not bpy.data.objects.get(hidden_name)
assert bpy.data.objects.get('DetailTestWalker')
assert len(bpy.data.actions) > 0
scene = bpy.context.scene
start = min(action.frame_range[0] for action in bpy.data.actions)
end = max(action.frame_range[1] for action in bpy.data.actions)
assert end > start
scene.frame_set(round(start))
before = bpy.data.objects['DetailTestWalker'].matrix_world.translation.copy()
scene.frame_set(round(end))
bpy.context.view_layer.update()
assert (bpy.data.objects['DetailTestWalker'].matrix_world.translation - before).length > .1
summary = {'installed_addon': whitebox_world.__file__,
           'feature_mesh_counts': {k: len(v) for k, v in features.items()},
           'all_export_meshes': len(all_names), 'coarse_export_meshes': len(coarse),
           'shibuya_export_meshes': len(shibuya), 'manual_edit': edited_name,
           'checks': ['ZIP installation', 'immediate RNA UI setters', 'distinct road heights below paint', 'independent viewport/render/export layers',
                      'active camera AUTO', 'ALL/COARSE/FROZEN', 'persistent reopen',
                      'manual edits and artist visibility', 'actor and camera invariance',
                      'actual GLB node filtering and animation round-trip', 'Shibuya provenance']}
(OUT / 'results.json').write_text(json.dumps(summary, indent=2))
print('WHITEBOX_DETAILS_INTEGRATION_OK:', json.dumps(summary))
