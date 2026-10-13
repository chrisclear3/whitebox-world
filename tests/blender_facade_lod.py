"""Focused paired-shell runtime/export regression test using source imports.

Run: blender -b --factory-startup --python-exit-code 1 --python tests/blender_facade_lod.py
"""
import json
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from whitebox_world.detail_runtime import (group_details, setup, update_details,
    object_render_visible, freeze, install, scene_collections)
from whitebox_world.export import export_glb

OUT = ROOT / 'artifacts/integration/facade_lod'
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'results.json').unlink(missing_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene['ww_config'] = '{}'
scene.frame_start = 1
scene.frame_end = 2
setup(scene, {'lod_mode': 'ALL'})
install()


def root(name):
    col = bpy.data.collections.new('WW_' + name)
    scene.collection.children.link(col)
    return col


buildings, facades = root('Buildings'), root('Facades')


def cube(name, col):
    mesh = bpy.data.meshes.new(name + 'Mesh')
    mesh.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0),
                     (-2, -2, 8), (2, -2, 8), (2, 2, 8), (-2, 2, 8)], [],
                    [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
                     (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    col.objects.link(obj)
    return obj


anchor = cube('WW_TestBuilding', buildings)
anchor['ww_facade_shell_pair'] = True
near = cube('WW_TestNearWalls', facades)
near.parent = anchor
for obj in [near]:
    obj['ww_detail'] = True
    obj['ww_feature'] = 'facades'
    obj['ww_lod_parent'] = anchor.name
artist_hidden = cube('WW_ArtistHidden', facades)
artist_hidden['ww_detail'] = True
artist_hidden['ww_feature'] = 'facades'
artist_hidden['ww_lod_parent'] = anchor.name
artist_hidden.hide_render = True
artist_hidden.hide_viewport = True
artist_hidden.hide_set(True)
group_details(scene)
count = len(list(scene_collections(scene)))
group_details(scene)
assert len(list(scene_collections(scene))) == count, 'Grouping must be idempotent'
assert anchor.name not in buildings.objects
coarse = next(col for col in buildings.children if col.get('ww_lod_coarse'))
detail = next(col for col in facades.children if col.get('ww_lod'))
assert not coarse.get('ww_lod')
assert anchor.name in coarse.objects
assert near.name in detail.objects
original_mesh = anchor.data
near_mesh = near.data
anchor.data.vertices[0].co.x -= .37
near.data.vertices[0].co.x += .21
anchor_edit = tuple(anchor.data.vertices[0].co)
near_edit = tuple(near.data.vertices[0].co)

camera = bpy.data.objects.new('WW_TestCamera', bpy.data.cameras.new('WW_TestCamera'))
scene.collection.objects.link(camera)
scene.camera = camera
camera.location = (0, 0, 4)


def refresh():
    bpy.context.view_layer.update()
    update_details(scene)
    bpy.context.view_layer.update()


def pair(expected_near):
    refresh()
    assert object_render_visible(near, scene) == expected_near
    assert object_render_visible(anchor, scene) == (not expected_near)
    assert near.visible_get() == expected_near
    assert anchor.visible_get() == (not expected_near)
    assert tuple(anchor.data.vertices[0].co) == anchor_edit
    assert tuple(near.data.vertices[0].co) == near_edit
    assert artist_hidden.hide_render and artist_hidden.hide_viewport and artist_hidden.hide_get()


pair(True)
scene['ww_lod_mode'] = 'COARSE'
pair(False)
scene['ww_lod_mode'] = 'AUTO'
scene['ww_lod_distance'] = 10
pair(True)
camera.location = (100, 100, 100)
pair(False)
camera.location = (0, 0, 4)
pair(True)
freeze(scene)
frozen_near = detail.hide_viewport, detail.hide_render
camera.location = (100, 100, 100)
pair(True)
for enabled in [False, True, False, True]:
    scene['ww_show_facades'] = enabled
    pair(enabled)
    assert (detail.hide_viewport, detail.hide_render) == frozen_near
assert anchor.data == original_mesh and near.data == near_mesh


def snapshot():
    return {
        'mode': scene['ww_lod_mode'], 'frame': scene.frame_current,
        'subframe': scene.frame_subframe,
        'collections': {c.name: (c.hide_viewport, c.hide_render) for c in scene_collections(scene)},
        'objects': {o.name: (o.hide_viewport, o.hide_render, o.hide_get(), o.select_get())
                    for o in bpy.context.view_layer.objects},
        'active': bpy.context.view_layer.objects.active,
    }


def export(name, choice, expect_near, expect_coarse):
    scene['ww_export_detail'] = choice
    refresh()
    before = snapshot()
    path = OUT / (name + '.glb')
    export_glb(str(path), scene)
    after = snapshot()
    assert after == before, (name, before, after)
    raw = path.read_bytes()
    size, kind = struct.unpack_from('<II', raw, 12)
    assert kind == 0x4e4f534a
    gltf = json.loads(raw[20:20 + size])
    names = {node['name'] for node in gltf.get('nodes', []) if 'mesh' in node}
    assert (near.name in names) == expect_near, (name, names)
    assert (anchor.name in names) == expect_coarse, (name, names)
    assert artist_hidden.name not in names
    assert tuple(anchor.data.vertices[0].co) == anchor_edit
    assert tuple(near.data.vertices[0].co) == near_edit
    return names


scene.frame_set(1, subframe=.25)
near.select_set(True)
bpy.context.view_layer.objects.active = near
export('frozen_near_current', 'CURRENT', True, False)
export('frozen_near_coarse', 'COARSE', False, True)
export('frozen_near_all', 'ALL', True, False)
pair(True)
scene['ww_show_facades'] = False
pair(False)
export('disabled_all', 'ALL', False, True)
export('disabled_current', 'CURRENT', False, True)
scene['ww_show_facades'] = True
pair(True)

# Artist viewport-only collection flags must not drop a render-visible shell.
buildings.hide_viewport = True
layer_buildings = bpy.context.view_layer.layer_collection.children[buildings.name]
layer_buildings.hide_viewport = True
export('hidden_coarse_collection', 'COARSE', False, True)
assert buildings.hide_viewport and layer_buildings.hide_viewport
buildings.hide_viewport = False
layer_buildings.hide_viewport = False

# Artist object flags stay untouched, including an independently hidden anchor.
anchor.hide_render = True
export('artist_hidden_coarse', 'COARSE', False, False)
anchor.hide_render = False
scene['ww_lod_mode'] = 'COARSE'
pair(False)
freeze(scene)
for enabled in [False, True, False, True]:
    scene['ww_show_facades'] = enabled
    pair(False)
export('frozen_coarse_all', 'ALL', True, False)
export('frozen_coarse_current', 'CURRENT', False, True)
pair(False)

# A current AUTO snapshot must use the camera position at the export frame.
scene['ww_lod_mode'] = 'AUTO'
camera.location = (0, 0, 4)
pair(True)
export('auto_near_current', 'CURRENT', True, False)
camera.location = (100, 100, 100)
pair(False)
export('auto_far_current', 'CURRENT', False, True)

# Viewport and render may have different frozen detail selections. Export uses
# render visibility and must restore both complementary pair states exactly.
scene['ww_lod_mode'] = 'FROZEN'
detail.hide_viewport = True
detail.hide_render = False
refresh()
assert near.visible_get() is False and anchor.visible_get() is True
assert object_render_visible(near, scene) and not object_render_visible(anchor, scene)
export('asymmetric_frozen_current', 'CURRENT', True, False)
assert detail.hide_viewport and not detail.hide_render
assert not coarse.hide_viewport and coarse.hide_render

# Any exception during baking must restore the pair and scene immediately.
import whitebox_world.export as export_module
original_bake = export_module.bake
scene['ww_export_detail'] = 'COARSE'
before = snapshot()
def fail_bake(scene):
    scene.frame_set(scene.frame_end)
    raise RuntimeError('Intentional bake failure')
export_module.bake = fail_bake
try:
    try:
        export_glb(str(OUT / 'failed.glb'), scene)
        raise AssertionError('Expected failure')
    except RuntimeError as error:
        assert 'Intentional bake failure' in str(error)
finally:
    export_module.bake = original_bake
assert snapshot() == before, 'Bake failure must restore original state'

# The same guarantees hold after collections/selection were changed and the
# glTF operator itself fails. Keep Blender real, replace only this module's call.
from types import SimpleNamespace
original_bpy = export_module.bpy
def fail_gltf(**kwargs):
    raise RuntimeError('Intentional export failure')
export_module.bpy = SimpleNamespace(context=bpy.context, ops=SimpleNamespace(
    export_scene=SimpleNamespace(gltf=fail_gltf)))
try:
    try:
        export_glb(str(OUT / 'failed.glb'), scene)
        raise AssertionError('Expected failure')
    except RuntimeError as error:
        assert 'Intentional export failure' in str(error)
finally:
    export_module.bpy = original_bpy
assert snapshot() == before, 'Export failure must restore original state'
scene['ww_lod_mode'] = 'AUTO'

# Save while the feature is off; reopen must retain the frozen underlying near
# selection so re-enabling the feature restores it, without rebuilding anything.
camera.location = (0, 0, 4)
pair(True)
freeze(scene)
scene['ww_show_facades'] = False
pair(False)
blend = OUT / 'frozen_pair.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
bpy.ops.wm.open_mainfile(filepath=str(blend))
scene = bpy.context.scene
anchor = bpy.data.objects['WW_TestBuilding']
near = bpy.data.objects['WW_TestNearWalls']
artist_hidden = bpy.data.objects['WW_ArtistHidden']
detail = next(col for col in scene_collections(scene) if col.get('ww_lod'))
coarse = next(col for col in scene_collections(scene) if col.get('ww_lod_coarse'))
assert scene['ww_lod_mode'] == 'FROZEN'
pair(False)
scene['ww_show_facades'] = True
pair(True)
export('reopened_current', 'CURRENT', True, False)
summary = {'checks': ['paired near/coarse visibility', 'idempotent grouping',
    'AUTO active camera bounds', 'FROZEN feature off/on', 'artist edits and hide flags',
    'ALL/COARSE/CURRENT GLB shell exclusivity', 'viewport-hidden collection export',
    'selection, frame, mode and collection-state restoration',
    'asymmetric frozen viewport/render', 'bake/export-failure restoration', 'frozen save/reopen']}
(OUT / 'results.json').write_text(json.dumps(summary, indent=2))
print('WHITEBOX_FACADE_LOD_OK:', json.dumps(summary))
