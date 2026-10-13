"""Non-destructive detail visibility: collection LOD never edits artist meshes.

AUTO uses the active scene camera, not the editor view. FROZEN persists the
current per-group selection in the .blend and works without add-on handlers.
"""
import math
from contextlib import contextmanager
import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

FEATURES = {'facades':'Facades', 'trees':'Trees', 'road_markings':'RoadMarkings',
            'utility_poles':'UtilityPoles', 'traffic_lights':'TrafficLights'}
_BUSY = False


def setup(scene, config):
    for key in FEATURES:
        scene['ww_show_'+key] = bool(config.get('show_'+key, True))
    scene['ww_lod_mode'] = config.get('lod_mode', 'AUTO')
    scene['ww_lod_distance'] = float(config.get('lod_distance', 85))
    scene['ww_export_detail'] = config.get('export_detail', 'CURRENT')


def scene_collections(scene):
    """Visit only this scene's collection tree, once per linked collection."""
    seen = set()
    def visit(col):
        if col.as_pointer() in seen: return
        seen.add(col.as_pointer())
        yield col
        for child in col.children:
            yield from visit(child)
    yield from visit(scene.collection)


@contextmanager
def suspend_updates():
    """Keep an export snapshot fixed while Blender changes frame/visibility."""
    global _BUSY
    previous = _BUSY
    _BUSY = True
    try:
        yield
    finally:
        _BUSY = previous


def group_details(scene):
    """Group editable detail meshes and their complementary coarse shells.

    A facade shell pair keeps the original object/mesh as its coarse anchor.
    Only collection links change; object visibility and artist edits are intact.
    """
    collections = list(scene_collections(scene))
    by_name = {col.name: col for col in collections}
    groups = {(col.get('ww_feature', 'facades'), col.get('ww_lod_anchor', '')): col
              for col in collections if col.get('ww_lod')}
    for obj in list(scene.objects):
        if not obj.get('ww_detail'): continue
        feature = obj.get('ww_feature', 'facades')
        root = by_name.get('WW_'+FEATURES.get(feature, 'Facades'))
        if root is None: continue
        anchor = obj.get('ww_lod_parent', '') or (obj.parent.name if obj.parent else obj.name)
        key = (feature, anchor)
        if key not in groups:
            col = bpy.data.collections.new('WW_LOD_'+anchor)
            root.children.link(col)
            col['ww_lod'] = True; col['ww_lod_anchor'] = anchor
            col['ww_feature'] = feature
            groups[key] = col
        for col in list(obj.users_collection):
            if col != groups[key]: col.objects.unlink(obj)
        if obj.name not in groups[key].objects: groups[key].objects.link(obj)

    buildings = by_name.get('WW_Buildings')
    if buildings is None: return
    coarse_groups = {col.get('ww_lod_anchor', ''): col for col in collections
                     if col.get('ww_lod_coarse')}
    for obj in list(scene.objects):
        if not obj.get('ww_facade_shell_pair'): continue
        detail = groups.get(('facades', obj.name))
        if detail is None: continue  # Never hide a shell with no replacement.
        coarse = coarse_groups.get(obj.name)
        if coarse is None:
            coarse = bpy.data.collections.new('WW_LOD_Coarse_'+obj.name)
            buildings.children.link(coarse)
            coarse['ww_lod_coarse'] = True
            coarse['ww_lod_anchor'] = obj.name
            coarse['ww_feature'] = 'facades'
        coarse['ww_lod_detail'] = detail.name
        for col in list(obj.users_collection):
            if col != coarse: col.objects.unlink(obj)
        if obj.name not in coarse.objects: coarse.objects.link(obj)


def _distance_to_bounds(camera, obj):
    if obj is None: return 0.0
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box] if obj.type == 'MESH' else [obj.matrix_world.translation]
    return math.sqrt(sum(max(min(p[i] for p in corners)-camera[i], 0, camera[i]-max(p[i] for p in corners))**2 for i in range(3)))


def update_details(scene, force=False):
    global _BUSY
    if _BUSY or not scene.get('ww_config'): return
    _BUSY = True
    try:
        collections = list(scene_collections(scene))
        by_name = {col.name: col for col in collections}
        for key, name in FEATURES.items():
            col = by_name.get('WW_'+name)
            if col:
                hidden = not bool(scene.get('ww_show_'+key, True))
                if col.hide_viewport != hidden: col.hide_viewport = hidden
                if col.hide_render != hidden: col.hide_render = hidden
        mode = scene.get('ww_lod_mode', 'AUTO')
        camera = scene.camera.matrix_world.translation if scene.camera else None
        radius = float(scene.get('ww_lod_distance',85))
        if mode != 'FROZEN':
            for col in collections:
                if not col.get('ww_lod'): continue
                hidden = mode == 'COARSE'
                if mode == 'AUTO' and camera is not None:
                    hidden = _distance_to_bounds(camera, scene.objects.get(col.get('ww_lod_anchor',''))) > radius
                if col.hide_viewport != hidden: col.hide_viewport = hidden
                if col.hide_render != hidden: col.hide_render = hidden
        # FROZEN preserves the detail-group selection, independently of feature
        # toggles. Switching facades off must reveal a complete coarse shell;
        # switching back on restores each frozen group's former near/far state.
        for coarse in collections:
            if not coarse.get('ww_lod_coarse'): continue
            detail = by_name.get(coarse.get('ww_lod_detail', ''))
            enabled = bool(scene.get('ww_show_'+coarse.get('ww_feature', 'facades'), True))
            viewport = enabled and detail is not None and not detail.hide_viewport
            render = enabled and detail is not None and not detail.hide_render
            if coarse.hide_viewport != viewport: coarse.hide_viewport = viewport
            if coarse.hide_render != render: coarse.hide_render = render
    finally:
        _BUSY = False


def freeze(scene):
    update_details(scene)
    scene['ww_lod_mode'] = 'FROZEN'


def object_render_visible(obj, scene):
    if obj.hide_render: return False
    def visit(col, hidden=False):
        hidden = hidden or col.hide_render
        if obj.name in col.objects and not hidden: return True
        return any(visit(child, hidden) for child in col.children)
    return visit(scene.collection)


@persistent
def details_depsgraph(scene, *args):
    update_details(scene)


@persistent
def details_frame(scene, *args):
    update_details(scene)


@persistent
def details_load(*args):
    update_details(bpy.context.scene)


@persistent
def details_render(scene, *args):
    update_details(scene)


def install():
    for name, fn in [('depsgraph_update_post',details_depsgraph),('frame_change_post',details_frame),('load_post',details_load),('render_pre',details_render)]:
        handlers = getattr(bpy.app.handlers,name)
        for old in list(handlers):
            if old.__module__ == __name__ and old.__name__ == fn.__name__: handlers.remove(old)
        handlers.append(fn)


def uninstall():
    for name in ('depsgraph_update_post','frame_change_post','load_post','render_pre'):
        handlers = getattr(bpy.app.handlers,name)
        for fn in list(handlers):
            if getattr(fn,'__module__','') == __name__: handlers.remove(fn)
